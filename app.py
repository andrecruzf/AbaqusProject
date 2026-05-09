import base64
import math
import os
import re
import subprocess
import time
import anthropic
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit_autorefresh import st_autorefresh

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Abaqus Pipeline",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

EULER_USER  = "acruzfaria"
EULER_HOST  = "euler.ethz.ch"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

WIDTH_OPTIONS = [20, 50, 80, 90, 100, 120, 200]
MS_OPTIONS = [1e-4, 1e-5,1e-6,1e-7]
PIP_OPTIONS   = ["PUNCH_2", "PUNCH_21", "PUNCH_23", "PUNCH_24", "PUNCH_25"]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _synced_videos_html(movie_path, cut_path):
    """Return an HTML string with two autoplay/loop/muted videos side by side,
    synchronized so the cut view always matches the full-view frame.
    Videos are embedded as base64 data URIs so no extra file serving is needed.
    v1 (full view) is the master; a requestAnimationFrame loop keeps v2 in sync."""
    def _b64(path):
        with open(path, 'rb') as fh:
            return base64.b64encode(fh.read()).decode()

    b64_movie = _b64(movie_path)
    b64_cut   = _b64(cut_path)

    # object-fit:cover inside a cropped-aspect-ratio wrapper removes the black
    # margins Abaqus leaves around the simulation content in a 16:9 frame.
    # aspect-ratio:7/6 crops ~17% from each side (vs 12.5% for 4/3).
    video_style = (
        "position:absolute;top:0;left:0;"
        "width:100%;height:100%;"
        "object-fit:cover;object-position:center center;"
    )
    wrap_style = (
        "position:relative;overflow:hidden;"
        "aspect-ratio:9/7;width:100%;background:#000;"
    )

    return """
<style>
.vid-caption {
  text-align: center;
  font-family: Helvetica, Arial, sans-serif;
  font-size: 13px;
  margin: 0 0 4px 0;
  color: #000000;
}
@media (prefers-color-scheme: dark) {
  .vid-caption { color: #ffffff; }
}
</style>
<div style="display:flex;gap:8px;width:100%%;">
  <div style="flex:1;min-width:0;">
    <p class="vid-caption">Full view</p>
    <div style="%(wrap)s">
      <video id="v_movie" style="%(vid)s" autoplay loop muted playsinline>
        <source src="data:video/webm;base64,%(b64_movie)s" type="video/webm">
      </video>
    </div>
  </div>
  <div style="flex:1;min-width:0;">
    <p class="vid-caption">Cut view (Y=0 symmetry plane)</p>
    <div style="%(wrap)s">
      <video id="v_cut" style="%(vid)s" autoplay loop muted playsinline>
        <source src="data:video/webm;base64,%(b64_cut)s" type="video/webm">
      </video>
    </div>
  </div>
</div>
<script>
(function() {
  var master = document.getElementById('v_movie');
  var slave  = document.getElementById('v_cut');
  function sync() {
    if (master.readyState >= 2 && slave.readyState >= 2) {
      var diff = Math.abs(slave.currentTime - master.currentTime);
      if (diff > 0.067) { slave.currentTime = master.currentTime; }
    }
    requestAnimationFrame(sync);
  }
  master.addEventListener('play',   function(){ if (slave.paused)  slave.play(); });
  master.addEventListener('pause',  function(){ if (!slave.paused) slave.pause(); });
  master.addEventListener('seeked', function(){ slave.currentTime = master.currentTime; });
  requestAnimationFrame(sync);
})();
</script>
""" % {'b64_movie': b64_movie, 'b64_cut': b64_cut,
       'wrap': wrap_style, 'vid': video_style}


def make_job_name(test_type, specimen_width, blank_thickness, angle,
                  punch_diameter, mesh_factor, mass_scaling_dt, pip_punch2_id):

    _t   = str(blank_thickness).replace(".", "p")
    _ang = str(int(angle))

    _pip = f"_p2{pip_punch2_id.replace('PUNCH_', '')}" if pip_punch2_id else ""

    _ms_exp  = int(math.floor(math.log10(mass_scaling_dt)))
    _ms_mant = int(round(mass_scaling_dt / 10 ** _ms_exp))
    _ms      = f"_ms{_ms_mant}e{abs(_ms_exp)}"

    _mr = ""
    if abs(mesh_factor - 1.0) > 1e-6:
        _mr = "_mr" + f"{mesh_factor:.4g}".replace(".", "p")

    if test_type == "nakazima":
        prefix = f"Naka{int(round(punch_diameter))}"
    elif test_type == "marciniak":
        prefix = f"Marc{int(round(punch_diameter))}"
    else:
        prefix = "Pip"

    return f"{prefix}_W{specimen_width}_t{_t}_ang{_ang}{_pip}{_ms}{_mr}"


def build_env(cfg, include_width=True):
    env = {
        **os.environ,
        "TEST_TYPE": cfg["test_type"],
        "BLANK_THICKNESS": str(cfg["thickness"]),
        "MATERIAL_ORIENTATION_ANGLE": str(cfg["angle"]),
        "MESH_REFINEMENT_FACTOR": str(cfg["mesh_factor"]),
        "MASS_SCALING_DT": f"{cfg['mass_scaling']:.2e}",
    }

    if include_width:
        env["SPECIMEN_WIDTH"] = str(cfg["width"])

    if cfg["test_type"] == "pip":
        env["PIP_PUNCH2_ID"] = cfg["pip_id"]
    else:
        env["PUNCH_RADIUS"] = str(cfg["punch_diam"] / 2.0)

    return env


# ─────────────────────────────────────────────────────────────────────────────
# Job-progress helpers
# ─────────────────────────────────────────────────────────────────────────────
_TEST_MAP = {'Naka': 'nakazima', 'Marc': 'marciniak', 'Pip': 'pip'}
_JOB_RE   = re.compile(r'^(Naka|Marc|Pip)\d*_W\d+_t([\dp]+)_ang(\d+)')


def _load_step_times() -> dict:
    """Read STEP_TIME, PIP_STEP1_TIME, PIP_STEP2_TIME from config.py."""
    import importlib.util as _ilu
    try:
        spec = _ilu.spec_from_file_location("_cfg_tmp", os.path.join(PROJECT_DIR, "config.py"))
        cfg  = _ilu.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        s  = float(getattr(cfg, 'STEP_TIME',     10.0))
        p1 = float(getattr(cfg, 'PIP_STEP1_TIME', 10.0))
        p2 = float(getattr(cfg, 'PIP_STEP2_TIME', 10.0))
        return {'nakazima': [s], 'marciniak': [s], 'pip': [p1, p2]}
    except Exception:
        return {'nakazima': [10.0], 'marciniak': [10.0], 'pip': [10.0, 10.0]}


_STEP_TIMES = _load_step_times()



def _parse_sta_line(line: str) -> tuple[float | None, float | None]:
    """Return (ati, total_time) from an Abaqus/Explicit .sta data line.

    FORMAT (Abaqus 2023):
      INCREMENT  STEP_TIME  TOTAL_TIME  WALLCLOCK  INC_SIZE  CRIT_EL  ...
    Example:
      671044  6.710E-01 6.710E-01  04:36:17 1.000E-06  4882 ...
    """
    line = line.strip()
    if not line:
        return None, None
    parts = line.split()
    if len(parts) < 3:
        return None, None
    try:
        int(parts[0])              # must start with integer increment number
        ati        = float(parts[1])   # elapsed time in current step
        total_time = float(parts[2])   # total elapsed simulation time
        return ati, total_time
    except ValueError:
        return None, None


def _progress_pct(total_time: float, total_sim_time: float) -> float:
    """Simulation progress as 0-100 %."""
    return min(total_time / total_sim_time * 100.0, 100.0)


def _parse_slurm_elapsed(s: str) -> float:
    """Convert SLURM TIME string to seconds.  Formats: M:SS, H:MM:SS, D-HH:MM:SS."""
    s = s.strip()
    days = 0
    if '-' in s:
        d, s = s.split('-', 1)
        days = int(d)
    parts = s.split(':')
    try:
        if len(parts) == 2:
            return days * 86400 + int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return days * 86400 + int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0.0


def _fmt_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    seconds = int(seconds)
    h, rem  = divmod(seconds, 3600)
    m, _    = divmod(rem, 60)
    if h > 0:
        return f"≈ {h} h {m} min left"
    return f"≈ {m} min left"


def _fetch_progress(user: str, host: str, job_rows: list[tuple[str, str]]) -> dict:
    """
    SSH once to Euler and read .sta progress for each running job.

    Strategy: run_cluster.sh prints "  SCRATCH  : <path>" early in the SLURM
    stdout log.  We find the log on HOME (fast, bounded filesystem) using the
    known filename pattern {JOB_NAME}_{JOB_ID}.out, extract the scratch path,
    then tail the .sta file in that directory.  Works for all submission modes
    (submit_one flat, submit_all FLC, submit_study) without any path inference.
    """
    home       = f"/cluster/home/{user}/AbaqusProject"
    job_names  = [jn for _, jn in job_rows]

    # Build one compound command per job: find log → grep SCRATCH → tail .sta
    parts = []
    for jid, jn in job_rows:
        parts.append(
            f'jn={jn}; '
            f'log=$(find {home} -maxdepth 4 -name "{jn}_{jid}.out" 2>/dev/null | head -1); '
            f'if [ -n "$log" ]; then '
            f'  scratch=$(grep "SCRATCH  :" "$log" 2>/dev/null | head -1 | sed "s/.*SCRATCH  *: *//"); '
            f'  sta="$scratch/{jn}.sta"; '
            f'  echo "MATCH:$jn"; '
            f'  echo "PATH:$sta"; '
            f'  grep -E "^[[:space:]]+[0-9]" "$sta" 2>/dev/null | tail -1; '
            f'fi'
        )
    batch = "; ".join(parts)

    try:
        res = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=4",
             f"{user}@{host}", batch],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {jn: None for jn in job_names}

    # Parse output into per-job dicts
    result      = {jn: {"ati": None, "total_time": None, "path": "", "raw": ""} for jn in job_names}
    current_jn  = None
    for line in res.stdout.splitlines():
        if line.startswith("MATCH:"):
            current_jn = line[6:].strip()
        elif line.startswith("PATH:") and current_jn in result:
            result[current_jn]["path"] = line[5:].strip()
        elif current_jn in result:
            result[current_jn]["raw"] = line.strip()
            ati, total_time = _parse_sta_line(line)
            result[current_jn]["ati"]        = ati
            result[current_jn]["total_time"] = total_time

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────────────
defaults = {
    "test_type": "nakazima",
    "width": 100,
    "thickness": 1.5,
    "angle": 0,
    "punch_diam": 100.0,
    "mesh_factor": 3.0,
    "mass_scaling": 1e-5,
    "pip_id": "PUNCH_21",
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# UI Header
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚙️ Abaqus Pipeline")

page = st.radio(
    "Page",
    ["Submit Job", "Job Status", "Results", "AI Assistant"],
    horizontal=True,
    label_visibility="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
# Submit Job
# ══════════════════════════════════════════════════════════════════════════════
if page == "Submit Job":

    st.subheader("Submit Job")

    mode = st.segmented_control("Mode", ["Single", "All widths"], default="Single")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        test_type = st.selectbox("Test Type", ["nakazima", "marciniak", "pip"])

    with c2:
        if mode == "All widths":
            st.text_input("Width", value="—", disabled=True)
            width = WIDTH_OPTIONS[0]
        else:
            width = st.selectbox("Width", WIDTH_OPTIONS)

    with c3:
        thickness = st.number_input("Thickness", value=1.5)

    with c4:
        angle = st.number_input("Angle", value=0)

    c5, c6, c7 = st.columns(3)
    with c5:
        if test_type == "pip":
            pip_id = st.selectbox("PiP Punch", PIP_OPTIONS)
            punch_diam = None
        else:
            punch_diam = st.number_input("Punch Diameter", value=100.0)
            pip_id = None
    with c6:
        mesh_factor = st.number_input("Mesh Factor", value=3.0)
    with c7:
        mass_scaling = st.selectbox(
            "Mass Scaling Δt (s)",
            MS_OPTIONS,
            index=1,
            format_func=lambda x: f"{x:.1e}",
            key="cfg_mass_scaling",
        )

    # ── PiP 3-D punch preview ─────────────────────────────────────────────────
    _STL_VIEWER = (
        '<!DOCTYPE html><html><head>'
        '<style>*{margin:0;padding:0}body{overflow:hidden}'
        'canvas{display:block;width:100%;height:420px}</style></head><body>'
        '<canvas id="c"></canvas>'
        '<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.161.0/examples/jsm/"}}</script>'
        '<script type="module">'
        "import * as THREE from 'three';"
        "import {STLLoader} from 'three/addons/loaders/STLLoader.js';"
        "import {OrbitControls} from 'three/addons/controls/OrbitControls.js';"
        "import {mergeVertices} from 'three/addons/utils/BufferGeometryUtils.js';"
        "var canvas=document.getElementById('c'),W=canvas.parentElement.clientWidth||600,H=420;"
        'canvas.width=W;canvas.height=H;'
        'var renderer=new THREE.WebGLRenderer({canvas,antialias:true});'
        'renderer.setPixelRatio(window.devicePixelRatio);renderer.setSize(W,H);'
        'function _syncBg(){var c="#0e1117";try{c=window.getComputedStyle(window.parent.document.body).backgroundColor;}catch(e){}renderer.setClearColor(c);document.body.style.background=c;}'
        '_syncBg();setInterval(_syncBg,200);'
        'var scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(45,W/H,0.01,5000);'
        'var controls=new OrbitControls(camera,canvas);'
        'controls.enableDamping=true;controls.dampingFactor=0.08;'
        'scene.add(new THREE.AmbientLight(0xffffff,0.55));'
        'var d1=new THREE.DirectionalLight(0xffffff,0.9);d1.position.set(1,2,2);scene.add(d1);'
        'var d2=new THREE.DirectionalLight(0x88aaff,0.3);d2.position.set(-1,-1,-1);scene.add(d2);'
        "var bin=atob('__B64__'),buf=new Uint8Array(bin.length);"
        'for(var i=0;i<bin.length;i++)buf[i]=bin.charCodeAt(i);'
        # Merge coincident vertices (weld seams that float32 STL may leave slightly apart),
        # then compute smooth per-vertex normals.  No subdivision needed — Abaqus viewport
        # STL already has 7 K–50 K triangles; subdivision before merging actually caused
        # disconnected-edge artefacts because midpoints of unmerged verts differed in float.
        'var geo=mergeVertices(new STLLoader().parse(buf.buffer),1e-2);'
        'geo.computeVertexNormals();geo.center();geo.computeBoundingBox();'
        'var sz=geo.boundingBox.getSize(new THREE.Vector3()),r=Math.max(sz.x,sz.y,sz.z);'
        'camera.position.set(r*.8,r*.8,r*1.4);camera.lookAt(0,0,0);controls.update();'
        'var mat=new THREE.MeshPhongMaterial({color:0x8A8A8A,side:THREE.DoubleSide,shininess:45});'
        'scene.add(new THREE.Mesh(geo,mat));'
        '(function animate(){requestAnimationFrame(animate);controls.update();renderer.render(scene,camera)})();'
        '</script></body></html>'
    )

    if test_type == "pip":
        import base64 as _b64
        _punch_dir  = os.path.join(PROJECT_DIR, "PiP_Punches")
        _step_path  = os.path.join(_punch_dir, pip_id + ".step")
        _stl_path   = os.path.join(_punch_dir, pip_id + ".stl")
        _png_path   = os.path.join(_punch_dir, pip_id + ".png")

        if os.path.exists(_stl_path):
            with open(_stl_path, "rb") as _f:
                _b64_data = _b64.b64encode(_f.read()).decode()
            st.caption(f"Inner punch — {pip_id}  ·  drag to orbit, scroll to zoom")
            st.components.v1.html(_STL_VIEWER.replace("__B64__", _b64_data), height=430, scrolling=False)
        elif os.path.exists(_png_path):
            st.image(_png_path, use_container_width=True)

        if os.path.exists(_step_path):
            with open(_step_path, "rb") as _f:
                st.download_button(
                    f"Download {pip_id}.step (CAD)",
                    _f, file_name=f"{pip_id}.step",
                    mime="application/step", key=f"step_{pip_id}",
                )

    cfg = dict(
        test_type=test_type,
        width=width,
        thickness=thickness,
        angle=angle,
        punch_diam=punch_diam,
        mesh_factor=mesh_factor,
        mass_scaling=mass_scaling,
        pip_id=pip_id,
    )

    st.markdown("---")

    # ── Job preview ──────────────────────────────────────────────────────────
    if mode == "Single":

        job_name = make_job_name(
            test_type=cfg["test_type"],
            specimen_width=cfg["width"],
            blank_thickness=cfg["thickness"],
            angle=cfg["angle"],
            punch_diameter=cfg["punch_diam"],
            mesh_factor=cfg["mesh_factor"],
            mass_scaling_dt=cfg["mass_scaling"],
            pip_punch2_id=cfg["pip_id"],
        )

        st.code(job_name)

        env = build_env(cfg, include_width=True)
        cmd = ["bash", "deploy.sh"]

    else:
        names = [
            make_job_name(
                test_type=test_type,
                specimen_width=w,
                blank_thickness=thickness,
                angle=angle,
                punch_diameter=punch_diam,
                mesh_factor=mesh_factor,
                mass_scaling_dt=mass_scaling,
                pip_punch2_id=pip_id,
            )
            for w in WIDTH_OPTIONS
        ]

        st.caption(f"{len(names)} jobs will be submitted")

        with st.expander("Preview job names"):
            for n in names:
                st.code(n)

        env = build_env(cfg, include_width=False)
        cmd = ["bash", "deploy_all.sh"]

    # ── Submit ───────────────────────────────────────────────────────────────
    if st.button("Submit", type="primary"):
        with st.spinner("Submitting..."):
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode == 0:
            st.success("Submitted")
            st.code(result.stdout)
        else:
            st.error(result.stderr)


# ══════════════════════════════════════════════════════════════════════════════
# Job Status
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Job Status":

    st.subheader("Euler Queue")

    user = st.text_input("Username", value=EULER_USER)

    auto_refresh = st.checkbox("Auto-refresh (30s)", value=True)
    if auto_refresh:
        st_autorefresh(interval=30000, key="squeue_refresh")


    if user:
        with st.spinner("Fetching queue..."):
            result = subprocess.run(
                [
                    "ssh",
                    f"{user}@{EULER_HOST}",
                    'squeue --me --format="%.18i %.10P %.60j %.8u %.2t %.10M %.10l %.6D %R" --noheader'
                ],
                capture_output=True,
                text=True,
            )

        if result.returncode == 0:
            output = result.stdout.strip()

            st.markdown("#### Queue Output")

            if not output:
                st.info("No jobs in queue")
            else:
                import pandas as pd

                lines = output.splitlines()
                rows = [line.split(None, 8) for line in lines]

                df = pd.DataFrame(
                    rows,
                    columns=[
                        "JOBID",
                        "PARTITION",
                        "NAME",
                        "USER",
                        "ST",
                        "TIME",
                        "TIME_LIMIT",
                        "NODES",
                        "NODELIST(REASON)",
                    ],
                )

                df = df.astype(str)

                # ---------- COLORING ----------
                def color_status(val):
                    if val == "R":
                        return "background-color: #14532d; color: white"
                    elif val == "PD":
                        return "background-color: #7c2d12; color: white"
                    elif val in ["CD", "CG"]:
                        return "background-color: #1e3a8a; color: white"
                    elif val == "F":
                        return "background-color: #7f1d1d; color: white"
                    return ""

                styled_df = df.style.applymap(color_status, subset=["ST"])

                st.dataframe(styled_df, use_container_width=True, hide_index=True)

                # ── Simulation progress (all running jobs) ────────────────
                running_rows = [
                    row for row in rows
                    if len(row) >= 6 and row[4].strip() == "R"
                ]

                if running_rows:
                    st.markdown("#### Simulation Progress")

                    # (job_id, job_name) pairs for Abaqus solver jobs only
                    sta_rows = [
                        (r[0].strip(), r[2].strip()) for r in running_rows
                        if _JOB_RE.match(r[2].strip())
                    ]

                    cache     = st.session_state.get("sta_cache", {})
                    cache_age = time.time() - cache.get("ts", 0)
                    if sta_rows and (not cache.get("data") or cache_age > 60):
                        try:
                            data = _fetch_progress(user, EULER_HOST, sta_rows)
                        except Exception:
                            data = {}
                        st.session_state["sta_cache"] = {"data": data, "ts": time.time()}

                    progress_data = st.session_state.get("sta_cache", {}).get("data", {})
                    age           = int(time.time() - st.session_state.get("sta_cache", {}).get("ts", time.time()))

                    c_age, c_refresh = st.columns([4, 1])
                    with c_age:
                        st.caption(f"last fetched {age}s ago — auto-refreshes every 60 s")
                    with c_refresh:
                        if st.button("🔄", key="refresh_sta", help="Force refresh .sta now"):
                            st.session_state.pop("sta_cache", None)
                            st.rerun()

                    for row in running_rows:
                        jn         = row[2].strip()
                        slurm_time = row[5].strip()
                        m          = _JOB_RE.match(jn)
                        if not m:
                            continue

                        entry = progress_data.get(jn)
                        if entry is None or entry.get("total_time") is None:
                            continue

                        step_times   = _STEP_TIMES.get(_TEST_MAP.get(m.group(1), 'nakazima'), [10.0])
                        total_time   = sum(step_times)
                        sim_elapsed  = entry["total_time"]
                        pct          = _progress_pct(sim_elapsed, total_time)
                        wall_elapsed = _parse_slurm_elapsed(slurm_time)
                        if pct > 0.1 and wall_elapsed > 0:
                            remaining_wall = wall_elapsed * (100.0 - pct) / pct
                            eta = _fmt_duration(remaining_wall)
                        else:
                            eta = "estimating…"

                        st.write(f"**{jn}**  `{slurm_time}` elapsed")
                        cols = st.columns([4, 1])
                        with cols[0]:
                            st.progress(pct / 100.0)
                        with cols[1]:
                            st.caption(f"{pct:.1f}%  {eta}")

        else:
            st.error(result.stderr)
# ══════════════════════════════════════════════════════════════════════════════
# Results
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Results":
    import pandas as pd

    st.subheader("Results Viewer")

    c_dir, c_src = st.columns([2, 3])
    with c_dir:
        results_dir = st.text_input(
            "Local results directory", value=os.path.join(PROJECT_DIR, "FLC_output")
        )
    with c_src:
        euler_src = st.text_input(
            "Euler source path",
            value=f"{EULER_USER}@{EULER_HOST}:/cluster/home/{EULER_USER}/AbaqusProject/",
        )

    col_sync, col_del = st.columns([1, 4])
    with col_sync:
        do_sync = st.button("Sync from Euler", type="primary")
    with col_del:
        delete_stale = st.checkbox("Delete local files removed on Euler", value=False)

    if do_sync:
        os.makedirs(results_dir, exist_ok=True)
        sync_cmd = [
            "rsync", "-avz", "--prune-empty-dirs",
            "--include=*/",
            "--include=*.csv",
            "--include=*.pdf",
            "--include=*.png",
            "--include=*.webm",
            "--exclude=*",
        ]
        if delete_stale:
            sync_cmd.append("--delete")
        sync_cmd += [euler_src, results_dir + "/"]

        with st.spinner("Syncing from Euler…"):
            result = subprocess.run(sync_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            st.success("Sync complete")
            preview = result.stdout.strip()
            if preview:
                with st.expander("rsync output"):
                    st.code(preview[-3000:] if len(preview) > 3000 else preview)
            st.rerun()
        else:
            st.error(result.stderr or "rsync failed")

    if not os.path.isdir(results_dir):
        st.info("No local results yet — click **Sync from Euler** to pull them.")
        st.stop()

    # ── Discovery helpers ─────────────────────────────────────────────────────
    _JOB_MARKERS = ("global.csv", "forming_limits.csv", "postproc_plots.pdf")
    _FLC_MARKERS = ("flc_diagram.png", "flc_points.csv")

    def _is_flc_dir(d):
        try:
            files = os.listdir(d)
        except PermissionError:
            return False
        return any(os.path.exists(os.path.join(d, m)) for m in _FLC_MARKERS) or \
               any(f.startswith("FLC_") and f.endswith(".pdf") for f in files)

    def _is_job_dir(d):
        return any(os.path.exists(os.path.join(d, m)) for m in _JOB_MARKERS)

    def _scan(base):
        """Return (flc_dirs, job_dirs) as label→path dicts."""
        flc, jobs = {}, {}
        try:
            for e in sorted(os.scandir(base), key=lambda x: x.name):
                if not e.is_dir():
                    continue
                if _is_flc_dir(e.path):
                    flc[e.name] = e.path
                if _is_job_dir(e.path):
                    jobs[e.name] = e.path
                else:
                    try:
                        for sub in sorted(os.scandir(e.path), key=lambda x: x.name):
                            if sub.is_dir() and _is_job_dir(sub.path):
                                jobs[os.path.relpath(sub.path, base)] = sub.path
                    except PermissionError:
                        pass
        except PermissionError:
            pass
        return flc, jobs

    flc_dirs, job_dirs = _scan(results_dir)

    if not flc_dirs and not job_dirs:
        st.info("No postprocessed results found — sync from Euler or check the directory.")
        st.stop()

    # ── Mode selector (only show modes that have data) ────────────────────────
    modes = []
    if job_dirs:
        modes.append("Single Job")
    if flc_dirs:
        modes.append("Full FLC")
        modes.append("Compare FLC")

    view_mode = st.segmented_control("View", modes, default=modes[0])

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # Single Job view
    # ══════════════════════════════════════════════════════════════════════════
    if view_mode == "Single Job":

        sel = st.selectbox("Job", list(job_dirs.keys()))
        job_dir = job_dirs[sel]

        pngs = sorted(f for f in os.listdir(job_dir) if f.endswith(".png"))
        if pngs:
            img_cols = st.columns(min(len(pngs), 3))
            for i, png in enumerate(pngs):
                img_cols[i % 3].image(os.path.join(job_dir, png), use_container_width=True)

        webms = sorted(f for f in os.listdir(job_dir) if f.endswith(".webm"))
        if webms:
            movie_file = next((f for f in webms if f.endswith("_movie.webm")), None)
            cut_file   = next((f for f in webms if f.endswith("_cut.webm")), None)
            other_files = [f for f in webms
                           if not f.endswith("_movie.webm") and not f.endswith("_cut.webm")]

            _vkw = dict(autoplay=True, loop=True, muted=True)

            if movie_file and cut_file:
                html = _synced_videos_html(
                    os.path.join(job_dir, movie_file),
                    os.path.join(job_dir, cut_file),
                )
                st_components.html(html, height=500)
            elif movie_file:
                st.caption("Full view")
                st.video(os.path.join(job_dir, movie_file), **_vkw)
            elif cut_file:
                st.caption("Cut view (Y=0 symmetry plane)")
                st.video(os.path.join(job_dir, cut_file), **_vkw)

            for f in other_files:
                st.video(os.path.join(job_dir, f), **_vkw)

        tab_fd, tab_sp, tab_en, tab_fl = st.tabs(
            ["Force-Disp.", "Strain Path", "Energy", "Forming Limits"]
        )

        with tab_fd:
            for fname in ("global.csv", "punch_fd.csv"):
                fp = os.path.join(job_dir, fname)
                if os.path.exists(fp):
                    df = pd.read_csv(fp)
                    if "U3_mm" in df.columns and "RF3_N" in df.columns:
                        fig = px.line(df, x="U3_mm", y="RF3_N",
                                      labels={"U3_mm": "Displacement [mm]", "RF3_N": "Force [N]"},
                                      title="Punch Force–Displacement")
                        st.plotly_chart(fig, use_container_width=True)
                    break

        with tab_sp:
            fp = os.path.join(job_dir, "strain_path.csv")
            if os.path.exists(fp):
                df = pd.read_csv(fp)
                if "eps2_minor" in df.columns and "eps1_major" in df.columns:
                    fig = px.line(df, x="eps2_minor", y="eps1_major",
                                  labels={"eps2_minor": "ε₂ minor", "eps1_major": "ε₁ major"},
                                  title="Strain Path")
                    st.plotly_chart(fig, use_container_width=True)

        with tab_en:
            for fname in ("global.csv", "energy_data.csv"):
                fp = os.path.join(job_dir, fname)
                if os.path.exists(fp):
                    df = pd.read_csv(fp)
                    if "ALLKE" in df.columns and "ALLIE" in df.columns:
                        df = df[df["ALLIE"] > 0].copy()
                        df["ratio"] = df["ALLKE"] / df["ALLIE"]
                        x_col = "U3_mm" if "U3_mm" in df.columns else "total_time_s"
                        x_label = "Displacement [mm]" if x_col == "U3_mm" else "Time [s]"
                        fig = px.line(df, x=x_col, y="ratio",
                                      labels={x_col: x_label, "ratio": "KE / IE"},
                                      title="Kinetic / Internal Energy Ratio")
                        fig.add_hline(y=0.05, line_dash="dash", line_color="red",
                                      annotation_text="5% limit",
                                      annotation_position="bottom right")
                        st.plotly_chart(fig, use_container_width=True)
                    break

        with tab_fl:
            fp = os.path.join(job_dir, "forming_limits.csv")
            if os.path.exists(fp):
                df = pd.read_csv(fp)
                st.dataframe(df, use_container_width=True, hide_index=True)

        pdfs = sorted(f for f in os.listdir(job_dir) if f.endswith(".pdf"))
        if pdfs:
            st.markdown("---")
            dl_cols = st.columns(len(pdfs))
            for i, pdf in enumerate(pdfs):
                with open(os.path.join(job_dir, pdf), "rb") as fh:
                    dl_cols[i].download_button(
                        f"Download {pdf}", fh, file_name=pdf,
                        mime="application/pdf", key=f"dl_{pdf}_{sel}",
                    )

    # ══════════════════════════════════════════════════════════════════════════
    # Full FLC view
    # ══════════════════════════════════════════════════════════════════════════
    elif view_mode == "Full FLC":

        sel_flc = st.selectbox("FLC set", list(flc_dirs.keys()))
        flc_dir = flc_dirs[sel_flc]

        flc_png  = os.path.join(flc_dir, "flc_diagram.png")
        flc_csv  = os.path.join(flc_dir, "flc_points.csv")
        flc_pdfs = sorted(f for f in os.listdir(flc_dir) if f.startswith("FLC_") and f.endswith(".pdf"))

        has_png = os.path.exists(flc_png)
        has_pdf = bool(flc_pdfs)

        # One sub-dir per width — used both for the FLC chart and the job inspector
        sub_jobs = {
            e.name: e.path
            for e in sorted(os.scandir(flc_dir), key=lambda x: x.name)
            if e.is_dir() and _is_job_dir(e.path)
        }

        _FLC_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
                       '#9467bd', '#8c564b', '#e377c2']

        def _flc_w(s):
            m = re.search(r'W(\d+)', str(s))
            return int(m.group(1)) if m else 0

        # ── Collect fracture points ───────────────────────────────────────────
        # Priority 1: aggregated flc_points.csv (produced by flc_plot.py)
        # Priority 2: individual sub-job forming_limits.csv (method='fracture')
        _pts = []   # list of {name, e2, e1, dir}

        if os.path.exists(flc_csv):
            _df_agg = pd.read_csv(flc_csv)
            if 'eps2_fracture' in _df_agg.columns and 'eps1_fracture' in _df_agg.columns:
                for _, _r in _df_agg.iterrows():
                    _nm = str(_r.get('subdir', ''))
                    _pts.append({
                        'name': _nm,
                        'e2': float(_r['eps2_fracture']),
                        'e1': float(_r['eps1_fracture']),
                        'dir': sub_jobs.get(_nm, ''),
                        'valid': str(_r.get('fracture_type', 'dome')) == 'dome',
                    })

        if not _pts:
            for _nm, _jd in sub_jobs.items():
                _flim = os.path.join(_jd, 'forming_limits.csv')
                if not os.path.exists(_flim):
                    continue
                _dfl = pd.read_csv(_flim)
                _fr = _dfl[_dfl['method'] == 'fracture']
                if not _fr.empty:
                    _pts.append({
                        'name': _nm,
                        'e2': float(_fr.iloc[0]['eps2_minor']),
                        'e1': float(_fr.iloc[0]['eps1_major']),
                        'dir': _jd,
                        'valid': True,
                    })

        _pts.sort(key=lambda p: _flc_w(p['name']))
        _cmap_flc = {p['name']: _FLC_COLORS[i % len(_FLC_COLORS)] for i, p in enumerate(_pts)}

        # ── Draw FLC chart ────────────────────────────────────────────────────
        if _pts:
            flc_fig = go.Figure()

            # Faint strain paths per specimen
            for _p in _pts:
                if not _p['dir'] or not os.path.isdir(_p['dir']):
                    continue
                _e1p, _e2p = None, None
                for _fn, _c1, _c2 in [('elout.csv',      'eps1_le',    'eps2_le'),
                                       ('strain_path.csv', 'eps1_major', 'eps2_minor')]:
                    _fp2 = os.path.join(_p['dir'], _fn)
                    if os.path.exists(_fp2):
                        _dfsp = pd.read_csv(_fp2)
                        if _c1 in _dfsp.columns and _c2 in _dfsp.columns:
                            _e1p = _dfsp[_c1].tolist()
                            _e2p = _dfsp[_c2].tolist()
                            break
                if _e1p:
                    flc_fig.add_trace(go.Scatter(
                        x=_e2p, y=_e1p, mode='lines',
                        legendgroup=_p['name'], showlegend=False, hoverinfo='skip',
                        line=dict(color=_cmap_flc[_p['name']], width=1.2), opacity=0.35,
                    ))

            # Red fracture curve (sorted left → right, dome points only)
            _dome_pts = sorted([p for p in _pts if p['valid']], key=lambda p: p['e2'])
            if _dome_pts:
                flc_fig.add_trace(go.Scatter(
                    x=[p['e2'] for p in _dome_pts],
                    y=[p['e1'] for p in _dome_pts],
                    mode='lines', name='Fracture curve',
                    line=dict(color='red', width=2), hoverinfo='skip',
                ))

            # Per-specimen markers
            for _p in _pts:
                _col = _cmap_flc[_p['name']]
                _m = re.search(r'W\d+', _p['name'])
                _lbl = _m.group(0) if _m else _p['name']
                flc_fig.add_trace(go.Scatter(
                    x=[_p['e2']], y=[_p['e1']],
                    mode='markers', name=_lbl, legendgroup=_p['name'],
                    marker=dict(size=9, color=_col,
                                symbol='circle' if _p['valid'] else 'x',
                                line=dict(width=2, color=_col)),
                    hovertemplate=(_lbl + '<br>ε₂=%{x:.3f}<br>ε₁=%{y:.3f}<extra></extra>'),
                ))

            # Reference lines
            _L = max(max(p['e1'] for p in _pts), 0.8) * 1.3
            flc_fig.add_trace(go.Scatter(
                x=[-_L / 2, 0], y=[_L, 0], mode='lines', name='Uniaxial tension',
                line=dict(color='lightgray', width=1.2, dash='dashdot'), hoverinfo='skip',
            ))
            flc_fig.add_trace(go.Scatter(
                x=[0, _L], y=[0, _L], mode='lines', name='Equibiaxial',
                line=dict(color='lightgray', width=1.2, dash='dash'), hoverinfo='skip',
            ))

            _e2v = [p['e2'] for p in _pts]
            _e1v = [p['e1'] for p in _pts]
            _pad = 0.2
            _xr  = max(abs(min(_e2v)), abs(max(_e2v))) + 1e-6
            _x0, _x1 = -(1 + _pad) * _xr, (1 + _pad) * _xr
            _y0 = min(0.0, min(_e1v)) - _pad * (max(_e1v) - min(_e1v) + 1e-6)
            _y1 = max(_e1v) + _pad * (max(_e1v) - min(_e1v) + 1e-6)

            flc_fig.update_layout(
                xaxis=dict(title='ε₂  minor strain  (–)', range=[_x0, _x1]),
                yaxis=dict(title='ε₁  major strain  (–)', range=[_y0, _y1]),
                title='Forming Limit Curve',
                legend_title='Specimen',
                hovermode='closest',
                template='plotly_white',
                height=550,
            )
            flc_fig.add_vline(x=0, line_width=0.6, line_dash='dot', line_color='gray')
            flc_fig.add_hline(y=0, line_width=0.6, line_dash='dot', line_color='gray')
            st.plotly_chart(flc_fig, use_container_width=True)

        elif has_png:
            st.image(flc_png, use_container_width=True)
        else:
            st.info("No FLC data found — sync from Euler or run the post-processing scripts first.")

        if has_pdf:
            dl_cols = st.columns(len(flc_pdfs))
            for i, pdf in enumerate(flc_pdfs):
                with open(os.path.join(flc_dir, pdf), "rb") as fh:
                    dl_cols[i].download_button(
                        f"Download {pdf}", fh, file_name=pdf,
                        mime="application/pdf", key=f"flcdl_{pdf}_{sel_flc}",
                    )

        # ── Individual job results — identical layout to Single Job view ──────
        if sub_jobs:
            st.markdown("---")
            st.subheader("Individual Jobs")
            sel_sub = st.selectbox("Width", list(sub_jobs.keys()))
            job_dir = sub_jobs[sel_sub]

            pngs = sorted(f for f in os.listdir(job_dir) if f.endswith(".png"))
            if pngs:
                img_cols = st.columns(min(len(pngs), 3))
                for i, png in enumerate(pngs):
                    img_cols[i % 3].image(os.path.join(job_dir, png), use_container_width=True)

            webms2 = sorted(f for f in os.listdir(job_dir) if f.endswith(".webm"))
            if webms2:
                movie_file2 = next((f for f in webms2 if f.endswith("_movie.webm")), None)
                cut_file2   = next((f for f in webms2 if f.endswith("_cut.webm")), None)
                other2      = [f for f in webms2
                               if not f.endswith("_movie.webm") and not f.endswith("_cut.webm")]
                _vkw2 = dict(autoplay=True, loop=True, muted=True)
                if movie_file2 and cut_file2:
                    st_components.html(
                        _synced_videos_html(
                            os.path.join(job_dir, movie_file2),
                            os.path.join(job_dir, cut_file2),
                        ),
                        height=500,
                    )
                elif movie_file2:
                    st.caption("Full view")
                    st.video(os.path.join(job_dir, movie_file2), **_vkw2)
                elif cut_file2:
                    st.caption("Cut view (Y=0 symmetry plane)")
                    st.video(os.path.join(job_dir, cut_file2), **_vkw2)
                for f2 in other2:
                    st.video(os.path.join(job_dir, f2), **_vkw2)

            tab_fd2, tab_sp2, tab_en2, tab_fl2 = st.tabs(
                ["Force-Disp.", "Strain Path", "Energy", "Forming Limits"]
            )

            with tab_fd2:
                for fname in ("global.csv", "punch_fd.csv"):
                    fp = os.path.join(job_dir, fname)
                    if os.path.exists(fp):
                        df = pd.read_csv(fp)
                        if "U3_mm" in df.columns and "RF3_N" in df.columns:
                            fig = px.line(df, x="U3_mm", y="RF3_N",
                                          labels={"U3_mm": "Displacement [mm]", "RF3_N": "Force [N]"},
                                          title="Punch Force–Displacement")
                            st.plotly_chart(fig, use_container_width=True)
                        break

            with tab_sp2:
                fp = os.path.join(job_dir, "strain_path.csv")
                if os.path.exists(fp):
                    df = pd.read_csv(fp)
                    if "eps2_minor" in df.columns and "eps1_major" in df.columns:
                        fig = px.line(df, x="eps2_minor", y="eps1_major",
                                      labels={"eps2_minor": "ε₂ minor", "eps1_major": "ε₁ major"},
                                      title="Strain Path")
                        st.plotly_chart(fig, use_container_width=True)

            with tab_en2:
                for fname in ("global.csv", "energy_data.csv"):
                    fp = os.path.join(job_dir, fname)
                    if os.path.exists(fp):
                        df = pd.read_csv(fp)
                        if "ALLKE" in df.columns and "ALLIE" in df.columns:
                            df = df[df["ALLIE"] > 0].copy()
                            df["ratio"] = df["ALLKE"] / df["ALLIE"]
                            x_col = "U3_mm" if "U3_mm" in df.columns else "total_time_s"
                            x_label = "Displacement [mm]" if x_col == "U3_mm" else "Time [s]"
                            fig = px.line(df, x=x_col, y="ratio",
                                          labels={x_col: x_label, "ratio": "KE / IE"},
                                          title="Kinetic / Internal Energy Ratio")
                            fig.add_hline(y=0.05, line_dash="dash", line_color="red",
                                          annotation_text="5% limit",
                                          annotation_position="bottom right")
                            st.plotly_chart(fig, use_container_width=True)
                        break

            with tab_fl2:
                fp = os.path.join(job_dir, "forming_limits.csv")
                if os.path.exists(fp):
                    df = pd.read_csv(fp)
                    st.dataframe(df, use_container_width=True, hide_index=True)

            pdfs = sorted(f for f in os.listdir(job_dir) if f.endswith(".pdf"))
            if pdfs:
                st.markdown("---")
                dl_cols = st.columns(len(pdfs))
                for i, pdf in enumerate(pdfs):
                    with open(os.path.join(job_dir, pdf), "rb") as fh:
                        dl_cols[i].download_button(
                            f"Download {pdf}", fh, file_name=pdf,
                            mime="application/pdf", key=f"subdl_{pdf}_{sel_sub}",
                        )

    # ══════════════════════════════════════════════════════════════════════════
    # Compare FLC view
    # ══════════════════════════════════════════════════════════════════════════
    elif view_mode == "Compare FLC":

        def _parse_label(dirname):
            m = re.match(r'(?:FLC_)?(\w+?)_t([\dp]+)_ang(\d+)', dirname)
            if m:
                test      = m.group(1).capitalize()
                thickness = m.group(2).replace('p', '.')
                angle     = m.group(3)
                label = f"{test}  t = {thickness} mm"
                if angle != '0':
                    label += f"  {angle}°"
                return label
            return dirname

        def _fracture_points(flc_dir):
            pts = []
            try:
                for entry in sorted(os.scandir(flc_dir), key=lambda e: e.name):
                    if not entry.is_dir():
                        continue
                    fp = os.path.join(entry.path, 'forming_limits.csv')
                    if not os.path.exists(fp):
                        continue
                    df_lim = pd.read_csv(fp)
                    row = df_lim[df_lim['method'] == 'fracture']
                    if not row.empty:
                        pts.append({
                            'e2':  float(row.iloc[0]['eps2_minor']),
                            'e1':  float(row.iloc[0]['eps1_major']),
                            'job': entry.name,
                            'dir': entry.path,
                        })
            except PermissionError:
                pass
            pts.sort(key=lambda p: p['e2'])
            return pts

        def _read_strain_path(job_dir):
            for fname, c1, c2 in [('elout.csv',      'eps1_le',    'eps2_le'),
                                   ('strain_path.csv', 'eps1_major', 'eps2_minor')]:
                fp = os.path.join(job_dir, fname)
                if not os.path.exists(fp):
                    continue
                df_sp = pd.read_csv(fp)
                if c1 in df_sp.columns and c2 in df_sp.columns:
                    return df_sp[c1].tolist(), df_sp[c2].tolist()
            return None, None

        def _has_csv_data(flc_dir):
            try:
                return any(
                    os.path.exists(os.path.join(e.path, 'forming_limits.csv'))
                    for e in os.scandir(flc_dir) if e.is_dir()
                )
            except PermissionError:
                return False

        flc_options = {
            _parse_label(k): v
            for k, v in flc_dirs.items()
            if _has_csv_data(v)
        }

        if not flc_options:
            st.info("No FLC sets with CSV data found — sync from Euler first.")
            st.stop()

        selected = st.multiselect(
            "FLC sets to compare",
            list(flc_options.keys()),
            default=list(flc_options.keys())[:min(4, len(flc_options))],
        )

        if not selected:
            st.info("Select at least one FLC set above.")
            st.stop()

        show_paths = st.checkbox("Show strain paths", value=False)

        # Paper-friendly palette: distinct hues + varying luminance → readable in B&W
        # Colors from ColorBrewer Dark2 (perceptually distinct, print-safe)
        _PALETTE = [
            '#1b7837',  # dark green
            '#762a83',  # purple
            '#d6604d',  # brick red
            '#4393c3',  # steel blue
            '#e08214',  # amber
            '#2d004b',  # very dark purple
            '#543005',  # dark brown
            '#01665e',  # teal
        ]
        _DASHES   = ['solid', 'dash', 'dashdot', 'dot', 'longdash', 'longdashdot']
        _MARKERS  = ['circle', 'square', 'diamond', 'triangle-up', 'cross', 'star', 'pentagon', 'hexagram']

        fig = go.Figure()
        no_data = []
        all_e1, all_e2 = [], []

        for i, label in enumerate(selected):
            color   = _PALETTE[i % len(_PALETTE)]
            dash    = _DASHES[i % len(_DASHES)]
            marker  = _MARKERS[i % len(_MARKERS)]

            pts = _fracture_points(flc_options[label])
            if not pts:
                no_data.append(label)
                continue

            all_e2.extend(p['e2'] for p in pts)
            all_e1.extend(p['e1'] for p in pts)

            # Strain paths first so FLC curve renders on top
            if show_paths:
                for pt in pts:
                    e1_path, e2_path = _read_strain_path(pt['dir'])
                    if e1_path:
                        all_e1.extend(e1_path)
                        all_e2.extend(e2_path)
                        fig.add_trace(go.Scatter(
                            x=e2_path, y=e1_path,
                            mode='lines',
                            name=label,
                            legendgroup=label,
                            showlegend=False,
                            hoverinfo='skip',
                            line=dict(color=color, width=1, dash='dot'),
                            opacity=0.4,
                        ))

            fig.add_trace(go.Scatter(
                x=[p['e2'] for p in pts],
                y=[p['e1'] for p in pts],
                mode='lines+markers',
                name=label,
                legendgroup=label,
                text=[p['job'] for p in pts],
                hovertemplate='%{text}<br>ε₂ = %{x:.3f}<br>ε₁ = %{y:.3f}<extra></extra>',
                marker=dict(size=8, symbol=marker, color=color),
                line=dict(color=color, width=2, dash=dash),
            ))

        # Compute axis range from data with padding
        pad = 0.15
        if all_e1 and all_e2:
            x0 = min(all_e2) - pad * (max(all_e2) - min(all_e2) + 1e-6)
            x1 = max(all_e2) + pad * (max(all_e2) - min(all_e2) + 1e-6)
            y0 = min(0.0, min(all_e1)) - pad * (max(all_e1) - min(all_e1) + 1e-6)
            y1 = max(all_e1) + pad * (max(all_e1) - min(all_e1) + 1e-6)
        else:
            x0, x1, y0, y1 = -0.5, 0.5, 0.0, 1.0

        # Reference guidelines clipped to data range
        fig.add_trace(go.Scatter(
            x=[x0, 0], y=[-2 * x0, 0],
            mode='lines', name='Uniaxial tension',
            legendgroup='_guides', legendgrouptitle_text='Reference',
            line=dict(color='lightgray', width=1.2, dash='dashdot'),
            hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=[0, x1], y=[0, x1],
            mode='lines', name='Equibiaxial',
            legendgroup='_guides',
            line=dict(color='lightgray', width=1.2, dash='dash'),
            hoverinfo='skip',
        ))

        fig.update_layout(
            xaxis=dict(title='ε₂  minor strain  (–)', range=[x0, x1]),
            yaxis=dict(title='ε₁  major strain  (–)', range=[y0, y1]),
            title='Forming Limit Curve Comparison',
            legend_title='FLC set',
            hovermode='closest',
            template='plotly_white',
            width=1200, height=500,
        )
        fig.add_vline(x=0, line_width=0.6, line_dash='dot', line_color='gray')
        fig.add_hline(y=0, line_width=0.6, line_dash='dot', line_color='gray')

        st.plotly_chart(fig, use_container_width=True)

        if no_data:
            st.caption(f"No fracture CSV data found for: {', '.join(no_data)}")

        # ── Export ────────────────────────────────────────────────────────────
        with st.expander("Export plot"):
            import plotly.io as _pio
            c_name, c_scale, c_fmt = st.columns([3, 1, 1])
            with c_name:
                fname = st.text_input("Filename", value="FLC_comparison")
            with c_scale:
                scale = st.selectbox("Resolution", [1, 2, 3, 4],
                                     index=1, format_func=lambda s: f"{s}× ({s*1200}×{s*500}px)")
            with c_fmt:
                fmt = st.selectbox("Format", ["png", "pdf", "svg"])

            if st.button("Render & download", type="primary"):
                with st.spinner("Rendering…"):
                    img_bytes = _pio.to_image(
                        fig, format=fmt,
                        width=1200, height=500, scale=scale,
                    )
                st.download_button(
                    label=f"Download {fname}.{fmt}",
                    data=img_bytes,
                    file_name=f"{fname}.{fmt}",
                    mime=f"image/{fmt}" if fmt != "pdf" else "application/pdf",
                )


# ══════════════════════════════════════════════════════════════════════════════
# AI Assistant
# ══════════════════════════════════════════════════════════════════════════════
elif page == "AI Assistant":

    st.subheader("AI Assistant")

    api_key = st.text_input("Anthropic API key", type="password")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.write(m["content"])

    prompt = st.chat_input("Ask...")

    if prompt and api_key:

        st.session_state.messages.append({"role": "user", "content": prompt})

        client = anthropic.Anthropic(api_key=api_key)

        mode_desc = "batch (all widths)" if mode == "All widths" else "single job"

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=f"""
You are an Abaqus expert.

Current setup:
- Mode: {mode_desc}
- Test: {test_type}
- Thickness: {thickness}
- Mesh: {mesh_factor}
- Mass scaling: {mass_scaling}
""",
            messages=st.session_state.messages,
        )

        reply = response.content[0].text

        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()