# -*- coding: utf-8 -*-
import base64
import math
import os
import re
import subprocess
import time
import anthropic
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
MS_OPTIONS = [1e-3, 1e-4, 1e-5, 1e-6, 1e-7]
PIP_OPTIONS   = ["PUNCH_2", "PUNCH_21", "PUNCH_23", "PUNCH_24", "PUNCH_25"]
VH_ALPHA = 0.55
VH_FRACTURE_HOPS = 2

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _install_scroll_keeper():
    st_components.html(
        """
<script>
(function () {
  const key = "abaqus_streamlit_scroll:" + window.parent.location.pathname;

  function scrollTarget() {
    const doc = window.parent.document;
    const candidates = [
      doc.querySelector('[data-testid="stAppViewContainer"]'),
      doc.querySelector('section.main'),
      doc.scrollingElement,
      doc.documentElement
    ].filter(Boolean);
    for (const el of candidates) {
      if (el.scrollHeight > el.clientHeight + 20) return el;
    }
    return window.parent;
  }

  function getY(target) {
    if (target === window.parent) return window.parent.scrollY || 0;
    return target.scrollTop || 0;
  }

  function setY(target, y) {
    if (target === window.parent) window.parent.scrollTo(0, y);
    else target.scrollTop = y;
  }

  const target = scrollTarget();
  let last = Number(window.parent.sessionStorage.getItem(key) || "0");

  function save() {
    last = getY(target);
    window.parent.sessionStorage.setItem(key, String(last));
  }

  function restore() {
    const y = Number(window.parent.sessionStorage.getItem(key) || "0");
    if (!Number.isFinite(y) || y <= 0) return;
    setY(target, y);
  }

  target.addEventListener ? target.addEventListener("scroll", save, {passive: true}) :
    window.parent.addEventListener("scroll", save, {passive: true});
  window.parent.addEventListener("beforeunload", save);
  window.parent.addEventListener("pagehide", save);
  window.parent.document.addEventListener("visibilitychange", save);
  window.parent.addEventListener("focus", restore);
  window.parent.addEventListener("pageshow", restore);

  [50, 150, 350, 700, 1200].forEach((delay) => {
    window.setTimeout(restore, delay);
  });
})();
</script>
        """,
        height=0,
    )


_install_scroll_keeper()


# ── Results page: shared constants & cached filesystem/CSV helpers ────────────
_JOB_MARKERS = ("global.csv", "forming_limits.csv", "postproc_plots.pdf")
_FLC_MARKERS = ("flc_diagram.png", "flc_points.csv")


def _is_flc_dir(d):
    try:
        files = os.listdir(d)
    except PermissionError:
        return False
    files_set = set(files)
    return bool(files_set & set(_FLC_MARKERS)) or \
           any(f.startswith("FLC_") and f.endswith(".pdf") for f in files)


def _is_job_dir(d):
    try:
        files = set(os.listdir(d))
    except PermissionError:
        return False
    return bool(files & set(_JOB_MARKERS))


def _has_flc_children(d):
    try:
        for entry in os.scandir(d):
            if entry.is_dir() and _is_job_dir(entry.path):
                return True
    except PermissionError:
        return False
    return False


@st.cache_data(ttl=30)
def _scan(base):
    """Return (flc_dirs, job_dirs) as label→path dicts. Cached for 30 s."""
    flc, jobs = {}, {}
    try:
        for e in sorted(os.scandir(base), key=lambda x: x.name):
            if not e.is_dir():
                continue
            if _is_flc_dir(e.path):
                flc[e.name] = e.path
            elif _has_flc_children(e.path):
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


@st.cache_data(ttl=120)
def _load_csv(path):
    """Read a postproc CSV and cache the result for 120 s."""
    return pd.read_csv(path)


def _resolve_job_file(job_dir, filename):
    """Find a postproc file even when the selected job dir is a stale mirror."""
    direct = os.path.join(job_dir, filename)
    if os.path.exists(direct):
        return direct

    job_name = os.path.basename(os.path.abspath(job_dir))
    parent_name = os.path.basename(os.path.dirname(os.path.abspath(job_dir)))
    candidates = [
        os.path.join(PROJECT_DIR, parent_name, job_name, filename),
        os.path.join(PROJECT_DIR, "FLC_output", parent_name, job_name, filename),
        os.path.join(PROJECT_DIR, "study_nakazima_ms1e6_mr4_ps2", job_name, filename),
        os.path.join(PROJECT_DIR, "FLC_output", "study_nakazima_ms1e6_mr4_ps2", job_name, filename),
    ]
    for fp in candidates:
        if os.path.exists(fp):
            return fp
    return direct


def _display_job_videos(job_dir):
    all_webms = sorted(f for f in os.listdir(job_dir) if f.endswith(".webm"))
    webms = sorted(
        f for f in all_webms
        if os.path.getsize(os.path.join(job_dir, f)) > 0
    )
    if not all_webms:
        return
    if not webms:
        st.info("Movie files are present but empty. Re-run movie post-processing.")
        return

    movie_file = next((f for f in webms if f.endswith("_movie.webm")), None)
    cut_file = next((f for f in webms if f.endswith("_cut.webm")), None)
    other_files = [
        f for f in webms
        if not f.endswith("_movie.webm") and not f.endswith("_cut.webm")
    ]
    video_kwargs = dict(autoplay=True, loop=True, muted=True)

    st.markdown("#### Movies")
    if movie_file and cut_file:
        def _b64(path):
            mtime = os.path.getmtime(path)
            key = f"_vid_b64_{path}"
            cached = st.session_state.get(key)
            if cached and cached[0] == mtime:
                return cached[1]
            with open(path, "rb") as fh:
                data = base64.b64encode(fh.read()).decode("ascii")
            st.session_state[key] = (mtime, data)
            return data

        movie_b64 = _b64(os.path.join(job_dir, movie_file))
        cut_b64 = _b64(os.path.join(job_dir, cut_file))
        html = """
<style>
  body { margin: 0; padding: 0; overflow: hidden; background: transparent !important; }
  .video-container { display:flex; gap:8px; width:100%; margin-bottom:12px; }
  .video-box { flex:1; min-width:0; }
  .video-label { font-size:13px; margin:0 0 4px 0; color: #fafafa; font-family: sans-serif; }
  video { width:100%; height:auto; border-radius: 4px; background: #000; }
  
  .controls-bar {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 0;
    font-family: sans-serif;
  }
  
  .slider-container {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  
  input[type=range] {
    flex: 1;
    cursor: pointer;
    accent-color: #ff4b4b;
  }
  
  .time-display {
    font-size: 12px;
    color: #bbb;
    min-width: 80px;
    text-align: right;
  }
  
  .buttons-row {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 15px;
  }
  
  .btn {
    background: #262730;
    color: white;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 6px 12px;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    min-width: 40px;
  }
  
  .btn:hover {
    border-color: #ff4b4b;
    background: #333;
  }
  
  .btn:active {
    background: #444;
  }
  
  .btn-play {
    background: #ff4b4b;
    border-color: #ff4b4b;
    font-weight: bold;
  }
  .btn-play:hover {
    background: #ff6b6b;
  }
</style>

<div class="video-container">
  <div class="video-box">
    <div class="video-label">Full view</div>
    <video id="movie_v" autoplay loop muted playsinline preload="auto" tabindex="-1">
      <source src="data:video/webm;base64,@@MOVIE_B64@@" type="video/webm">
    </video>
  </div>
  <div class="video-box">
    <div class="video-label">Cut view</div>
    <video id="cut_v" autoplay loop muted playsinline preload="auto" tabindex="-1">
      <source src="data:video/webm;base64,@@CUT_B64@@" type="video/webm">
    </video>
  </div>
</div>

<div class="controls-bar">
  <div class="slider-container">
    <input type="range" id="seek_bar" value="0" min="0" step="0.001" tabindex="-1" onfocus="this.blur()">
    <div class="time-display" id="time_txt">0:00 / 0:00</div>
  </div>
  <div class="buttons-row">
    <button class="btn" id="btn_start" title="Go to start" tabindex="-1" onfocus="this.blur()" onmousedown="event.preventDefault()">⏮</button>
    <button class="btn" id="btn_prev" title="Frame back" tabindex="-1" onfocus="this.blur()" onmousedown="event.preventDefault()">⏴</button>
    <button class="btn btn-play" id="btn_play" title="Play/Pause" tabindex="-1" onfocus="this.blur()" onmousedown="event.preventDefault()">▶</button>
    <button class="btn" id="btn_next" title="Frame forward" tabindex="-1" onfocus="this.blur()" onmousedown="event.preventDefault()">⏵</button>
    <button class="btn" id="btn_end" title="Go to end" tabindex="-1" onfocus="this.blur()" onmousedown="event.preventDefault()">⏭</button>
  </div>
</div>
<a href="#" style="position:absolute; bottom:0; opacity:0;" autofocus tabindex="-1">.</a>

<script>
(function() {
  const a = document.getElementById('movie_v');
  const b = document.getElementById('cut_v');
  const seekBar = document.getElementById('seek_bar');
  const timeTxt = document.getElementById('time_txt');
  const btnPlay = document.getElementById('btn_play');
  const btnStart = document.getElementById('btn_start');
  const btnEnd = document.getElementById('btn_end');
  const btnPrev = document.getElementById('btn_prev');
  const btnNext = document.getElementById('btn_next');
  
  if (!a || !b) return;
  
  let raf = null;
  let isSeeking = false;
  const frameTime = 0.07; // Slightly larger step to ensure frame change on single click

  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  function updateUI() {
    if (!isSeeking) {
      seekBar.value = a.currentTime;
    }
    timeTxt.textContent = formatTime(a.currentTime) + " / " + formatTime(a.duration || 0);
  }

  function stopLoop() {
    if (raf !== null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
  }

  function setPlayIcon(isPlaying) {
    btnPlay.textContent = isPlaying ? "⏸" : "▶";
  }

  function pauseBoth() {
    a.pause();
    b.pause();
    stopLoop();
    setPlayIcon(false);
    updateUI();
  }

  function playBoth() {
    if (b.readyState >= 2 && Math.abs(b.currentTime - a.currentTime) > 0.05) {
      b.currentTime = a.currentTime;
    }
    setPlayIcon(true);
    a.play().catch(() => setPlayIcon(false));
    b.play().catch(() => {});
    startLoop();
  }

  function bindPress(el, handler) {
    let handledPointer = false;
    el.addEventListener('pointerdown', (e) => {
      handledPointer = true;
      e.preventDefault();
      handler(e);
    });
    el.addEventListener('click', (e) => {
      e.preventDefault();
      if (handledPointer) {
        handledPointer = false;
        return;
      }
      handler(e);
    });
  }

  function syncCut() {
    if (b.readyState >= 2 && Math.abs(b.currentTime - a.currentTime) > 0.05) {
      b.currentTime = a.currentTime;
    }
    if (b.playbackRate !== a.playbackRate) {
      b.playbackRate = a.playbackRate;
    }
    if (a.paused) {
      if (!b.paused) b.pause();
      setPlayIcon(false);
    } else {
      if (b.paused) b.play().catch(()=>{});
      setPlayIcon(true);
    }
  }

  function startLoop() {
    if (raf !== null) return;
    const tick = () => {
      updateUI();
      syncCut();
      if (!a.paused) {
        raf = requestAnimationFrame(tick);
      } else {
        raf = null;
      }
    };
    raf = requestAnimationFrame(tick);
  }

  a.addEventListener('loadedmetadata', () => {
    seekBar.max = a.duration;
    updateUI();
  });
  
  a.addEventListener('play', startLoop);
  a.addEventListener('pause', () => {
    syncCut();
    updateUI();
  });
  a.addEventListener('seeked', () => {
    syncCut();
    updateUI();
  });

  bindPress(btnPlay, () => {
    if (a.paused) playBoth();
    else pauseBoth();
  });

  bindPress(btnStart, () => {
    a.currentTime = 0;
    pauseBoth();
    syncCut();
    updateUI();
  });

  bindPress(btnEnd, () => {
    a.currentTime = a.duration;
    pauseBoth();
    syncCut();
    updateUI();
  });

  bindPress(btnPrev, () => {
    pauseBoth();
    a.currentTime = Math.max(0, a.currentTime - frameTime);
    syncCut();
    updateUI();
  });

  bindPress(btnNext, () => {
    pauseBoth();
    a.currentTime = Math.min(a.duration, a.currentTime + frameTime);
    syncCut();
    updateUI();
  });

  seekBar.addEventListener('input', () => {
    isSeeking = true;
    a.currentTime = seekBar.value;
    updateUI();
  });

  seekBar.addEventListener('change', () => {
    isSeeking = false;
    syncCut();
  });
  
  // Initial sync
  if (a.readyState >= 1) {
    seekBar.max = a.duration;
    updateUI();
  }
  
  // Auto-start loop if playing
  if (!a.paused) startLoop();

})();
</script>
"""
        html = html.replace("@@MOVIE_B64@@", movie_b64).replace("@@CUT_B64@@", cut_b64)
        # Wrap in a container with a key to help Streamlit manage lifecycle
        with st.container(key=f"v_sync_{job_dir.replace('/', '_')}"):
            st_components.html(html, height=650)
    elif movie_file:
        st.caption("Full view")
        st.video(os.path.join(job_dir, movie_file), **video_kwargs)
    elif cut_file:
        st.caption("Cut view")
        st.video(os.path.join(job_dir, cut_file), **video_kwargs)

    for i, fname in enumerate(other_files):
        st.caption(fname)
        st.video(os.path.join(job_dir, fname), **video_kwargs)


def make_job_name(test_type, specimen_width, blank_thickness, angle,
                  punch_diameter, mesh_factor, mass_scaling_dt, pip_punch2_id,
                  punch_speed):

    _t   = str(blank_thickness).replace(".", "p")
    _ang = str(int(angle))

    _pip = f"_p2{pip_punch2_id.replace('PUNCH_', '')}" if pip_punch2_id else ""

    _ms_exp  = int(math.floor(math.log10(mass_scaling_dt)))
    _ms_mant = int(round(mass_scaling_dt / 10 ** _ms_exp))
    _ms      = f"_ms{_ms_mant}e{abs(_ms_exp)}"

    _mr = ""
    if abs(mesh_factor - 1.0) > 1e-6:
        _mr = "_mr" + f"{mesh_factor:.4g}".replace(".", "p")

    _ps = ""
    if test_type != "pip" and abs(punch_speed - 5.0) > 1e-6:
        _ps = "_ps" + f"{punch_speed:.4g}".replace(".", "p")

    if test_type == "nakazima":
        prefix = f"Naka{int(round(punch_diameter))}"
    elif test_type == "marciniak":
        prefix = f"Marc{int(round(punch_diameter))}"
    else:
        prefix = "Pip"

    return f"{prefix}_W{specimen_width}_t{_t}_ang{_ang}{_pip}{_ms}{_mr}{_ps}"


def make_study_root_name(test_type, blank_thickness, angle, punch_diameter,
                         mesh_factor, mass_scaling_dt, pip_punch2_id,
                         punch_speed):
    job_name = make_job_name(
        test_type=test_type,
        specimen_width=0,
        blank_thickness=blank_thickness,
        angle=angle,
        punch_diameter=punch_diameter,
        mesh_factor=mesh_factor,
        mass_scaling_dt=mass_scaling_dt,
        pip_punch2_id=pip_punch2_id,
        punch_speed=punch_speed,
    )
    return "FLC_" + re.sub(r"_W\d+(?=_t)", "", job_name, count=1)


def build_env(cfg, include_width=True):
    env = {
        **os.environ,
        "TEST_TYPE": cfg["test_type"],
        "BLANK_THICKNESS": str(cfg["thickness"]),
        "MATERIAL_ORIENTATION_ANGLE": str(cfg["angle"]),
        "MESH_REFINEMENT_FACTOR": str(cfg["mesh_factor"]),
        "MASS_SCALING_DT": f"{cfg['mass_scaling']:.2e}",
        "PUNCH_SPEED": f"{cfg['punch_speed']:.6g}",
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


# config.py: STEP_TIME = 50 mm / 5 mm/s = 10 s; PiP both steps = 10 s.
# Speed overrides are captured in the _ps suffix and handled by _job_step_times.
_STEP_TIMES = {'nakazima': [10.0], 'marciniak': [10.0], 'pip': [10.0, 10.0], '_punch_disp': 50.0}


def _parse_float_token(token: str) -> float | None:
    try:
        return float(str(token).replace("p", "."))
    except Exception:
        return None


def _job_step_times(job_name: str, test_type: str) -> list[float]:
    """Return expected simulation step time(s), honoring job-name speed suffix."""
    if test_type != "pip":
        m_ps = re.search(r'_ps([\dp]+)(?:_|$)', job_name)
        if m_ps:
            speed = _parse_float_token(m_ps.group(1))
            punch_disp = float(_STEP_TIMES.get('_punch_disp', 50.0))
            if speed and speed > 0:
                return [punch_disp / speed]
    return _STEP_TIMES.get(test_type, [10.0])



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
    "punch_speed": 5.0,
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

    c5, c6, c7, c8 = st.columns(4)
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
    with c8:
        punch_speed = st.number_input(
            "Punch Speed (mm/s)",
            min_value=0.1,
            value=5.0,
            step=0.5,
            disabled=(test_type == "pip"),
            help="Standard Nakazima/Marciniak punch speed. PiP uses its two configured step times.",
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
        punch_speed=punch_speed,
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
            punch_speed=cfg["punch_speed"],
        )

        study_root = make_study_root_name(
            test_type=cfg["test_type"],
            blank_thickness=cfg["thickness"],
            angle=cfg["angle"],
            punch_diameter=cfg["punch_diam"],
            mesh_factor=cfg["mesh_factor"],
            mass_scaling_dt=cfg["mass_scaling"],
            pip_punch2_id=cfg["pip_id"],
            punch_speed=cfg["punch_speed"],
        )

        st.code(job_name)
        st.caption(f"Study root: {study_root}")

        cmd = [
            "bash", "deploy.sh",
            cfg["test_type"],
            str(cfg["thickness"]),
            str(cfg["angle"]),
            str(cfg["width"]),
            cfg["pip_id"] or "none",
            f"{cfg['mesh_factor']:.6g}",
            f"{cfg['mass_scaling']:.2e}",
            f"{cfg['punch_speed']:.6g}",
        ]
        if cfg["punch_diam"] is not None:
            cmd.append(f"{(cfg['punch_diam'] / 2.0):.6g}")
        else:
            cmd.append("none")
        cmd.append(study_root)

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
                punch_speed=punch_speed,
            )
            for w in WIDTH_OPTIONS
        ]

        st.caption(f"{len(names)} jobs will be submitted")

        with st.expander("Preview job names"):
            for n in names:
                st.code(n)

        cmd = [
            "bash", "deploy_all.sh",
            cfg["test_type"],
            str(cfg["thickness"]),
            str(cfg["angle"]),
            cfg["pip_id"] or "none",
            f"{cfg['mesh_factor']:.6g}",
            f"{cfg['mass_scaling']:.2e}",
            f"{cfg['punch_speed']:.6g}",
        ]
        if cfg["punch_diam"] is not None:
            cmd.append(f"{(cfg['punch_diam'] / 2.0):.6g}")

    # ── Submit ───────────────────────────────────────────────────────────────
    if st.button("Submit", type="primary"):
        with st.spinner("Submitting..."):
            result = subprocess.run(cmd, capture_output=True, text=True)

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

                styled_df = df.style.map(color_status, subset=["ST"])

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

                        test_key     = _TEST_MAP.get(m.group(1), 'nakazima')
                        step_times   = _job_step_times(jn, test_key)
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

    def _line_fit(x, y):
        n = len(x)
        if n < 2:
            return None
        sx = sum(x)
        sy = sum(y)
        sxx = sum(v * v for v in x)
        sxy = sum(a * b for a, b in zip(x, y))
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-18:
            return None
        slope = (n * sxy - sx * sy) / denom
        intercept = (sy - slope * sx) / n
        mse = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y)) / n
        return slope, intercept, mse

    def _moving_average(values, window):
        window = max(1, int(window))
        if window <= 1 or len(values) < 3:
            return list(values)
        if window % 2 == 0:
            window += 1
        half = window // 2
        out = []
        for i in range(len(values)):
            lo = max(0, i - half)
            hi = min(len(values), i + half + 1)
            out.append(sum(values[lo:hi]) / (hi - lo))
        return out

    def _volk_hora_fit(t, rate):
        t_start = t[0]
        t_end = t[-1]
        t_min_fit = t_start + 0.6 * (t_end - t_start)
        valid_indices = [i for i in range(1, len(t) - 1) if t[i] >= t_min_fit]
        if len(valid_indices) < 8:
            return None

        x = [t[i] for i in valid_indices]
        y = [rate[i] for i in valid_indices]
        n = len(x)
        min_stable = 4
        min_unstable = 3
        if n < min_stable + min_unstable + 1:
            return None

        best_stable = None
        for count in range(min_stable, n - min_unstable + 1):
            fit = _line_fit(x[:count], y[:count])
            if fit is not None and (best_stable is None or fit[2] < best_stable["mse"]):
                best_stable = {
                    "count": count,
                    "slope": fit[0],
                    "intercept": fit[1],
                    "mse": fit[2],
                }

        best_unstable = None
        for count in range(min_unstable, n - min_stable + 1):
            fit = _line_fit(x[n - count:], y[n - count:])
            if fit is not None and (best_unstable is None or fit[2] < best_unstable["mse"]):
                best_unstable = {
                    "count": count,
                    "slope": fit[0],
                    "intercept": fit[1],
                    "mse": fit[2],
                }

        if best_stable is None or best_unstable is None:
            return None

        denom = best_stable["slope"] - best_unstable["slope"]
        # Physically, the unstable-phase slope must exceed the stable-phase slope
        # (thinning rate accelerates at localisation onset).  denom < 0 is required.
        # denom >= 0 means the roles are inverted (or the signal is flat/noisy) — reject.
        if denom >= 0:
            return None

        t_cross = (best_unstable["intercept"] - best_stable["intercept"]) / denom
        if t_cross < x[0] or t_cross > x[-1]:
            return None

        kcrit_pos = next((i for i, tv in enumerate(t) if tv >= t_cross), None)
        if kcrit_pos is None or kcrit_pos <= 0:
            return None
        k_stable = kcrit_pos - 1

        return {
            "t_fit_start": x[0],
            "t_fit_end": x[-1],
            "t_cross": t_cross,
            "y_cross": best_stable["slope"] * t_cross + best_stable["intercept"],
            "kcrit": kcrit_pos,
            "kstable": k_stable,
            "stable": best_stable,
            "unstable": best_unstable,
        }

    def _strip_plot_descriptions(fig):
        fig.update_layout(annotations=[])
        return fig

    def _plotly_chart(fig, *args, **kwargs):
        st.plotly_chart(_strip_plot_descriptions(fig), *args, **kwargs)

    def _volk_hora_rate_fig(job_dir, smoothing_window=20):
        fp = os.path.join(job_dir, "strain_path.csv")
        if not os.path.exists(fp):
            return None, "strain_path.csv not found"

        df = _load_csv(fp)
        required = {"time_s", "eps1_major", "eps2_minor"}
        if not required <= set(df.columns):
            return None, "strain_path.csv is missing time_s / eps1_major / eps2_minor"

        if "fracture_type" in df.columns:
            fracture_types = {
                str(v).strip().lower()
                for v in df["fracture_type"].dropna().unique()
                if str(v).strip()
            }
            if fracture_types and "dome" not in fracture_types:
                return None, "Volk-Hora rate is only shown for dome-zone fracture runs"

        data = df[["time_s", "eps1_major", "eps2_minor"]].apply(pd.to_numeric, errors="coerce")
        data = data.dropna().drop_duplicates(subset=["time_s"]).sort_values("time_s")
        if len(data) < 3:
            return None, "not enough pre-fracture frames"

        t = data["time_s"].tolist()
        strain_sum = (data["eps1_major"] + data["eps2_minor"]).tolist()
        rate = [0.0] * len(t)
        for i in range(len(t)):
            if i == 0:
                dt = t[1] - t[0]
                rate[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
            elif i == len(t) - 1:
                dt = t[i] - t[i - 1]
                rate[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
            else:
                dt = t[i + 1] - t[i - 1]
                rate[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0

        rate_for_fit = _moving_average(rate, smoothing_window)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t,
            y=rate_for_fit,
            mode="lines",
            name=f"smoothed signal ({smoothing_window} pts)",
            line=dict(width=2.5, color="steelblue"),
            hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
        ))

        fit = _volk_hora_fit(t, rate_for_fit)
        if fit is not None:
            stable = fit["stable"]
            unstable = fit["unstable"]
            ts = [fit["t_fit_start"], fit["t_cross"]]
            ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
            tu = [fit["t_cross"], fit["t_fit_end"]]
            yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
            fig.add_trace(go.Scatter(
                x=ts,
                y=ys,
                mode="lines",
                name="stable fit",
                line=dict(width=2.5, color="seagreen"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>stable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=tu,
                y=yu,
                mode="lines",
                name="unstable fit",
                line=dict(width=2.5, color="firebrick"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>unstable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=[fit["t_cross"]],
                y=[fit["y_cross"]],
                mode="markers",
                name="intersection",
                marker=dict(size=11, color="#facc15", symbol="x"),
                hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra>intersection</extra>",
            ))
        else:
            fig.add_annotation(
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.98,
                text="Fit unavailable for this signal/window",
                showarrow=False,
                font=dict(color="firebrick"),
            )

        fig.update_layout(
            title="Volk-Hora Time Signal",
            xaxis_title="Time [s]",
            yaxis_title="Thinning strain rate d(ε₁+ε₂)/dt [1/s]",
            template="plotly_white",
            height=450,
        )
        return _strip_plot_descriptions(fig), None

    def _cluster_median_df(job_dir):
        fp = _resolve_job_file(job_dir, "strain_cluster.csv")
        if not os.path.exists(fp):
            return None, "strain_cluster.csv not found"
        df = _load_csv(fp)
        required = {"time_s", "eps1_major", "eps2_minor"}
        if not required <= set(df.columns):
            return None, "strain_cluster.csv is missing time_s / eps1_major / eps2_minor"
        data = df[["time_s", "eps1_major", "eps2_minor"]].apply(pd.to_numeric, errors="coerce")
        data = data.dropna().sort_values("time_s")
        if data.empty:
            return None, "strain_cluster.csv has no usable rows"
        med = data.groupby("time_s", as_index=False)[["eps1_major", "eps2_minor"]].median()
        med = med.drop_duplicates(subset=["time_s"]).sort_values("time_s")
        if len(med) < 3:
            return None, "not enough cluster-median frames"
        return med, None

    def _fracture_cluster_anchor(job_dir):
        fp = _resolve_job_file(job_dir, "strain_cluster_faces.csv")
        if not os.path.exists(fp):
            return [], 0
        faces = _load_csv(fp)
        required = {"element_label", "role", "x", "y"}
        if not required <= set(faces.columns):
            return [], 0
        faces = faces.copy()
        faces["x"] = pd.to_numeric(faces["x"], errors="coerce")
        faces["y"] = pd.to_numeric(faces["y"], errors="coerce")
        faces = faces.dropna(subset=["element_label", "role", "x", "y"])
        role = faces["role"].astype(str)
        frac = faces[role.isin(["fracture_deleted", "crack_deleted"])]
        if frac.empty:
            frac = faces[role == "first_deleted"]
        if frac.empty:
            return [], 0
        pts = []
        for _, grp in frac.groupby("element_label"):
            pts.append((float(grp["x"].mean()), float(grp["y"].mean())))
        return pts, len(pts)

    def _fracture_neighborhood_label_set(job_dir):
        fp = os.path.join(job_dir, "strain_neighborhood.csv")
        if not os.path.exists(fp):
            return set()
        try:
            df = pd.read_csv(fp, usecols=["element_label"])
        except Exception:
            return set()
        labels = pd.to_numeric(df["element_label"], errors="coerce").dropna()
        return set(str(int(v)) for v in labels.unique())

    def _paths_within_anchor_hops(pids, centroids, anchor_points, conn_radius, hops):
        if not anchor_points or hops is None:
            return set(pids)
        pids = list(pids)
        if not pids:
            return set()
        seed_radius = max(float(conn_radius) * 1.05, 1e-6)
        allowed = set()
        frontier = set()
        for pid in pids:
            x, y = centroids[pid]
            if min(math.hypot(x - ax, y - ay) for ax, ay in anchor_points) <= seed_radius:
                allowed.add(pid)
                frontier.add(pid)
        for _ in range(int(hops)):
            next_frontier = set()
            for pid in frontier:
                x0, y0 = centroids[pid]
                for qid in pids:
                    if qid in allowed:
                        continue
                    x1, y1 = centroids[qid]
                    if math.hypot(x1 - x0, y1 - y0) <= conn_radius:
                        allowed.add(qid)
                        next_frontier.add(qid)
            frontier = next_frontier
            if not frontier:
                break
        return allowed

    def _volk_hora_connected_zone_fig(csv_path, title, prefer_fracture_center,
                                      smoothing_window=20, weight_by_area=False,
                                      anchor_points=None, anchor_name=None,
                                      anchor_radius=None, allowed_labels=None,
                                      anchor_hops=None):
        if not os.path.exists(csv_path):
            return None, os.path.basename(csv_path) + " not found"
        df = _load_csv(csv_path)
        required = {
            "time_s", "element_label", "integration_point",
            "centroid_x", "centroid_y", "eps1_major", "eps2_minor",
        }
        if not required <= set(df.columns):
            return None, os.path.basename(csv_path) + " is missing required columns"

        data = df.copy()
        for col in ("time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        if "top_face_area" in data.columns:
            data["top_face_area"] = pd.to_numeric(data["top_face_area"], errors="coerce")
        else:
            data["top_face_area"] = 1.0
        data["top_face_area"] = data["top_face_area"].fillna(1.0).clip(lower=1e-12)
        data = data.dropna(subset=["time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"])
        if data.empty:
            return None, os.path.basename(csv_path) + " has no usable rows"
        data["path_id"] = data["element_label"].astype(str) + "_IP" + data["integration_point"].astype(str)
        data = data.sort_values(["path_id", "time_s"])
        times = sorted(data["time_s"].dropna().unique().tolist())
        if len(times) < 5:
            return None, "not enough frames for Volk-Hora"

        path_data = {}
        centroids = {}
        for pid, grp in data.groupby("path_id"):
            grp = grp.drop_duplicates(subset=["time_s"]).sort_values("time_s")
            if len(grp) != len(times):
                continue
            if any(abs(float(a) - float(b)) > 1e-9 for a, b in zip(grp["time_s"].tolist(), times)):
                continue
            e1_vals = grp["eps1_major"].tolist()
            e2_vals = grp["eps2_minor"].tolist()
            strain_sum = [a + b for a, b in zip(e1_vals, e2_vals)]
            rate_vals = [0.0] * len(times)
            for i in range(len(times)):
                if i == 0:
                    dt = times[1] - times[0]
                    rate_vals[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
                elif i == len(times) - 1:
                    dt = times[i] - times[i - 1]
                    rate_vals[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                else:
                    dt = times[i + 1] - times[i - 1]
                    rate_vals[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
            path_data[pid] = {"e1": e1_vals, "e2": e2_vals, "rate": rate_vals}
            path_data[pid]["weight"] = float(grp["top_face_area"].iloc[0]) if weight_by_area else 1.0
            path_data[pid]["element_label"] = str(int(float(grp["element_label"].iloc[0])))
            centroids[pid] = (float(grp["centroid_x"].iloc[0]), float(grp["centroid_y"].iloc[0]))

        if len(path_data) < 3:
            return None, "not enough complete paths"

        nearest = []
        pids = list(path_data.keys())
        for i, pid in enumerate(pids):
            x0, y0 = centroids[pid]
            ds = []
            for j, qid in enumerate(pids):
                if i == j:
                    continue
                x1, y1 = centroids[qid]
                ds.append(math.hypot(x1 - x0, y1 - y0))
            if ds:
                nearest.append(min(ds))
        conn_radius = 1.6 * sorted(nearest)[len(nearest) // 2] if nearest else 2.0
        conn_radius = max(conn_radius, 1e-6)

        admissible = set(pids)
        allowed_labels = set(allowed_labels or [])
        if allowed_labels:
            admissible &= {pid for pid in pids if path_data[pid]["element_label"] in allowed_labels}
        if anchor_points and anchor_radius is not None:
            r = float(anchor_radius)
            admissible &= {
                pid for pid in pids
                if min(
                    math.hypot(centroids[pid][0] - ax, centroids[pid][1] - ay)
                    for ax, ay in anchor_points
                ) <= r
            }
        hop_allowed = _paths_within_anchor_hops(
            pids, centroids, anchor_points, conn_radius, anchor_hops
        ) if anchor_points and anchor_hops is not None else set(pids)
        admissible &= hop_allowed
        if not admissible:
            return None, "no V&H candidates inside fracture-constrained neighborhood"

        k_eval = max(1, len(times) - 2)
        rates_eval = sorted([path_data[p]["rate"][k_eval] for p in admissible], reverse=True)
        top_n = min(5, len(rates_eval))
        rep_max = sum(rates_eval[:top_n]) / float(top_n)
        alpha = VH_ALPHA
        threshold = alpha * rep_max
        hot = [pid for pid in admissible if path_data[pid]["rate"][k_eval] >= threshold]
        if not hot:
            return None, "no high-thinning-rate candidates found inside fracture-constrained neighborhood"

        hot_set = set(hot)
        components = []
        while hot_set:
            seed = hot_set.pop()
            comp = [seed]
            stack = [seed]
            while stack:
                pid = stack.pop()
                x0, y0 = centroids[pid]
                neighbors = []
                for qid in list(hot_set):
                    x1, y1 = centroids[qid]
                    if math.hypot(x1 - x0, y1 - y0) <= conn_radius:
                        neighbors.append(qid)
                for qid in neighbors:
                    hot_set.remove(qid)
                    stack.append(qid)
                    comp.append(qid)
            components.append(comp)

        center_xy = None
        anchor_points = list(anchor_points or [])
        if prefer_fracture_center and {"fracture_center_x", "fracture_center_y"} <= set(data.columns):
            cx = pd.to_numeric(data["fracture_center_x"], errors="coerce").dropna()
            cy = pd.to_numeric(data["fracture_center_y"], errors="coerce").dropna()
            if not cx.empty and not cy.empty:
                center_xy = (float(cx.iloc[0]), float(cy.iloc[0]))

        def comp_score(comp):
            wsum = sum(path_data[p]["weight"] for p in comp)
            mean_rate = sum(path_data[p]["weight"] * path_data[p]["rate"][k_eval] for p in comp) / wsum
            if anchor_points:
                min_dist = min(
                    math.hypot(centroids[p][0] - ax, centroids[p][1] - ay)
                    for p in comp
                    for ax, ay in anchor_points
                )
                return (-min_dist, mean_rate, wsum)
            if center_xy is None:
                return (mean_rate, wsum)
            cx0, cy0 = center_xy
            min_dist = min(math.hypot(centroids[p][0] - cx0, centroids[p][1] - cy0) for p in comp)
            return (-min_dist, mean_rate)

        zone = max(components, key=comp_score)
        zone_wsum = sum(path_data[p]["weight"] for p in zone)
        rep_rate = []
        rep_e1 = []
        rep_e2 = []
        for i in range(len(times)):
            rep_rate.append(sum(path_data[p]["weight"] * path_data[p]["rate"][i] for p in zone) / zone_wsum)
            rep_e1.append(sum(path_data[p]["weight"] * path_data[p]["e1"][i] for p in zone) / zone_wsum)
            rep_e2.append(sum(path_data[p]["weight"] * path_data[p]["e2"][i] for p in zone) / zone_wsum)

        rate_for_fit = _moving_average(rep_rate, smoothing_window)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times,
            y=rate_for_fit,
            mode="lines",
            name="signal" if smoothing_window <= 1 else f"signal ({smoothing_window} pts)",
            line=dict(width=2.5, color="steelblue"),
            hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
        ))

        fit = _volk_hora_fit(times, rate_for_fit)
        if fit is not None:
            stable = fit["stable"]
            unstable = fit["unstable"]
            ts = [fit["t_fit_start"], fit["t_cross"]]
            ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
            tu = [fit["t_cross"], fit["t_fit_end"]]
            yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
            k_stable = fit["kstable"]
            fig.add_trace(go.Scatter(
                x=ts, y=ys, mode="lines", name="stable fit",
                line=dict(width=2.5, color="seagreen"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>stable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=tu, y=yu, mode="lines", name="unstable fit",
                line=dict(width=2.5, color="firebrick"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>unstable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=[fit["t_cross"]], y=[fit["y_cross"]],
                mode="markers", name="intersection",
                marker=dict(size=11, color="#facc15", symbol="x"),
                hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra>intersection</extra>",
            ))
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.98,
                text=(
                    "zone n=%d, A=%.2f mm², alpha=%.2f, t=%.4f s, ε₁=%.4f, ε₂=%.4f%s"
                    if weight_by_area else
                    "zone n=%d, alpha=%.2f, t=%.4f s, ε₁=%.4f, ε₂=%.4f%s"
                ) % (
                    (len(zone), zone_wsum, alpha, times[k_stable], rep_e1[k_stable], rep_e2[k_stable],
                     ", anchored to %s%s%s" % (
                         anchor_name,
                         " within %.1f mm" % float(anchor_radius) if anchor_radius is not None else "",
                         ", max %d hops" % int(anchor_hops) if anchor_hops is not None else
                         ", neighborhood-limited" if allowed_labels else "",
                     ) if anchor_points and anchor_name else "")
                    if weight_by_area else
                    (len(zone), alpha, times[k_stable], rep_e1[k_stable], rep_e2[k_stable],
                     ", anchored to %s%s%s" % (
                         anchor_name,
                         " within %.1f mm" % float(anchor_radius) if anchor_radius is not None else "",
                         ", max %d hops" % int(anchor_hops) if anchor_hops is not None else
                         ", neighborhood-limited" if allowed_labels else "",
                     ) if anchor_points and anchor_name else "")
                ),
                showarrow=False,
            )
        else:
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.98,
                text="Fit unavailable for connected V&H zone",
                showarrow=False,
                font=dict(color="firebrick"),
            )

        fig.update_layout(
            title=title,
            xaxis_title="Time [s]",
            yaxis_title="Mean thinning rate d(ε₁+ε₂)/dt [1/s]",
            template="plotly_white",
            height=450,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1.0, title=None,
                itemclick="toggleothers",
            ),
            margin=dict(t=70, r=20),
        )
        return _strip_plot_descriptions(fig), None

    def _volk_hora_fracture_neighborhood_fig(job_dir, smoothing_window=20):
        csv_path = os.path.join(job_dir, "strain_neighborhood.csv")
        if not os.path.exists(csv_path):
            return None, "strain_neighborhood.csv not found"
        df = _load_csv(csv_path)
        required = {
            "time_s", "element_label", "integration_point",
            "eps1_major", "eps2_minor",
        }
        if not required <= set(df.columns):
            return None, "strain_neighborhood.csv is missing required columns"

        data = df.copy()
        for col in ("time_s", "eps1_major", "eps2_minor"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna(subset=["time_s", "eps1_major", "eps2_minor"])
        if data.empty:
            return None, "strain_neighborhood.csv has no usable rows"

        data["path_id"] = data["element_label"].astype(str) + "_IP" + data["integration_point"].astype(str)
        data = data.sort_values(["path_id", "time_s"])
        times = sorted(data["time_s"].dropna().unique().tolist())
        if len(times) < 5:
            return None, "not enough fracture-neighborhood frames for Volk-Hora"

        path_data = {}
        for pid, grp in data.groupby("path_id"):
            grp = grp.drop_duplicates(subset=["time_s"]).sort_values("time_s")
            if len(grp) != len(times):
                continue
            if any(abs(float(a) - float(b)) > 1e-9 for a, b in zip(grp["time_s"].tolist(), times)):
                continue
            e1_vals = grp["eps1_major"].tolist()
            e2_vals = grp["eps2_minor"].tolist()
            strain_sum = [a + b for a, b in zip(e1_vals, e2_vals)]
            rate_vals = [0.0] * len(times)
            for i in range(len(times)):
                if i == 0:
                    dt = times[1] - times[0]
                    rate_vals[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
                elif i == len(times) - 1:
                    dt = times[i] - times[i - 1]
                    rate_vals[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                else:
                    dt = times[i + 1] - times[i - 1]
                    rate_vals[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
            path_data[pid] = {"e1": e1_vals, "e2": e2_vals, "rate": rate_vals}

        if len(path_data) < 3:
            return None, "not enough complete fracture-neighborhood paths"

        rep_rate = []
        rep_e1 = []
        rep_e2 = []
        n_paths = float(len(path_data))
        for i in range(len(times)):
            rep_rate.append(sum(p["rate"][i] for p in path_data.values()) / n_paths)
            rep_e1.append(sum(p["e1"][i] for p in path_data.values()) / n_paths)
            rep_e2.append(sum(p["e2"][i] for p in path_data.values()) / n_paths)

        fracture_n = None
        if "fracture_cluster_size" in data.columns:
            vals = pd.to_numeric(data["fracture_cluster_size"], errors="coerce").dropna()
            if not vals.empty:
                fracture_n = int(vals.iloc[0])

        rate_for_fit = _moving_average(rep_rate, smoothing_window)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times,
            y=rate_for_fit,
            mode="lines",
            name="signal" if smoothing_window <= 1 else f"signal ({smoothing_window} pts)",
            line=dict(width=2.5, color="steelblue"),
            hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
        ))

        fit = _volk_hora_fit(times, rate_for_fit)
        if fit is not None:
            stable = fit["stable"]
            unstable = fit["unstable"]
            ts = [fit["t_fit_start"], fit["t_cross"]]
            ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
            tu = [fit["t_cross"], fit["t_fit_end"]]
            yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
            k_stable = fit["kstable"]
            fig.add_trace(go.Scatter(
                x=ts, y=ys, mode="lines", name="stable fit",
                line=dict(width=2.5, color="seagreen"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>stable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=tu, y=yu, mode="lines", name="unstable fit",
                line=dict(width=2.5, color="firebrick"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>unstable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=[fit["t_cross"]], y=[fit["y_cross"]],
                mode="markers", name="intersection",
                marker=dict(size=11, color="#facc15", symbol="x"),
                hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra>intersection</extra>",
            ))
            prefix = (
                "fracture elements=%d, centroid paths=%d"
                % (fracture_n, len(path_data))
                if fracture_n is not None else
                "centroid paths=%d" % len(path_data)
            )
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.98,
                text="%s, t=%.4f s, ε₁=%.4f, ε₂=%.4f" % (
                    prefix, times[k_stable], rep_e1[k_stable], rep_e2[k_stable]
                ),
                showarrow=False,
            )
        else:
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.98,
                text="Fit unavailable for fracture-cluster neighborhood",
                showarrow=False,
                font=dict(color="firebrick"),
            )

        fig.update_layout(
            title="Volk-Hora Signal from Fracture-Element Cluster Neighborhood",
            xaxis_title="Time [s]",
            yaxis_title="Mean thinning rate d(ε₁+ε₂)/dt [1/s]",
            template="plotly_white",
            height=450,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1.0, title=None,
                itemclick="toggleothers",
            ),
            margin=dict(t=70, r=20),
        )
        return _strip_plot_descriptions(fig), None

    def _volk_hora_cluster_rate_fig(job_dir, smoothing_window=20):
        fig, reason = _volk_hora_fracture_neighborhood_fig(
            job_dir,
            smoothing_window=smoothing_window,
        )
        if fig is not None:
            return _strip_plot_descriptions(fig), None

        # Backward-compatible fallback for old runs without strain_neighborhood.csv.
        neigh_fp = os.path.join(job_dir, "strain_neighborhood.csv")
        if os.path.exists(neigh_fp):
            df = _load_csv(neigh_fp)
            required = {
                "time_s", "element_label", "integration_point",
                "centroid_x", "centroid_y", "eps1_major", "eps2_minor",
            }
            if not required <= set(df.columns):
                return None, "strain_neighborhood.csv is missing required columns"

            data = df.copy()
            for col in ("time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"):
                data[col] = pd.to_numeric(data[col], errors="coerce")
            data = data.dropna(subset=["time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"])
            if data.empty:
                return None, "strain_neighborhood.csv has no usable rows"
            data["path_id"] = data["element_label"].astype(str) + "_IP" + data["integration_point"].astype(str)
            data = data.sort_values(["path_id", "time_s"])
            times = sorted(data["time_s"].dropna().unique().tolist())
            if len(times) < 5:
                return None, "not enough neighborhood frames for Volk-Hora"

            path_data = {}
            centroids = {}
            for pid, grp in data.groupby("path_id"):
                grp = grp.drop_duplicates(subset=["time_s"]).sort_values("time_s")
                if len(grp) != len(times):
                    continue
                if any(abs(float(a) - float(b)) > 1e-9 for a, b in zip(grp["time_s"].tolist(), times)):
                    continue
                e1_vals = grp["eps1_major"].tolist()
                e2_vals = grp["eps2_minor"].tolist()
                strain_sum = [a + b for a, b in zip(e1_vals, e2_vals)]
                rate_vals = [0.0] * len(times)
                for i in range(len(times)):
                    if i == 0:
                        dt = times[1] - times[0]
                        rate_vals[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
                    elif i == len(times) - 1:
                        dt = times[i] - times[i - 1]
                        rate_vals[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                    else:
                        dt = times[i + 1] - times[i - 1]
                        rate_vals[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                path_data[pid] = {"e1": e1_vals, "e2": e2_vals, "rate": rate_vals}
                centroids[pid] = (float(grp["centroid_x"].iloc[0]), float(grp["centroid_y"].iloc[0]))

            if len(path_data) < 3:
                return None, "not enough complete neighborhood paths"

            k_eval = max(1, len(times) - 2)
            rates_eval = sorted([v["rate"][k_eval] for v in path_data.values()], reverse=True)
            if not rates_eval:
                return None, "no thinning-rate values available"
            top_n = min(5, len(rates_eval))
            rep_max = sum(rates_eval[:top_n]) / float(top_n)
            alpha = VH_ALPHA
            threshold = alpha * rep_max
            hot = [pid for pid, v in path_data.items() if v["rate"][k_eval] >= threshold]
            if not hot:
                return None, "no high-thinning-rate candidates found"

            nearest = []
            for i, pid in enumerate(path_data.keys()):
                x0, y0 = centroids[pid]
                ds = []
                for j, qid in enumerate(path_data.keys()):
                    if i == j:
                        continue
                    x1, y1 = centroids[qid]
                    ds.append(math.hypot(x1 - x0, y1 - y0))
                if ds:
                    nearest.append(min(ds))
            conn_radius = 1.6 * sorted(nearest)[len(nearest) // 2] if nearest else 2.0
            conn_radius = max(conn_radius, 1e-6)

            hot_set = set(hot)
            components = []
            while hot_set:
                seed = hot_set.pop()
                comp = [seed]
                stack = [seed]
                while stack:
                    pid = stack.pop()
                    x0, y0 = centroids[pid]
                    neighbors = []
                    for qid in list(hot_set):
                        x1, y1 = centroids[qid]
                        if math.hypot(x1 - x0, y1 - y0) <= conn_radius:
                            neighbors.append(qid)
                    for qid in neighbors:
                        hot_set.remove(qid)
                        stack.append(qid)
                        comp.append(qid)
                components.append(comp)

            center_xy = None
            if {"fracture_center_x", "fracture_center_y"} <= set(data.columns):
                cx = pd.to_numeric(data["fracture_center_x"], errors="coerce").dropna()
                cy = pd.to_numeric(data["fracture_center_y"], errors="coerce").dropna()
                if not cx.empty and not cy.empty:
                    center_xy = (float(cx.iloc[0]), float(cy.iloc[0]))

            def comp_score(comp):
                mean_rate = sum(path_data[p]["rate"][k_eval] for p in comp) / float(len(comp))
                if center_xy is None:
                    return (0.0, mean_rate)
                cx0, cy0 = center_xy
                min_dist = min(math.hypot(centroids[p][0] - cx0, centroids[p][1] - cy0) for p in comp)
                return (-min_dist, mean_rate)

            zone = max(components, key=comp_score)
            rep_rate = []
            rep_e1 = []
            rep_e2 = []
            for i in range(len(times)):
                rep_rate.append(sum(path_data[p]["rate"][i] for p in zone) / float(len(zone)))
                rep_e1.append(sum(path_data[p]["e1"][i] for p in zone) / float(len(zone)))
                rep_e2.append(sum(path_data[p]["e2"][i] for p in zone) / float(len(zone)))

            rate_for_fit = _moving_average(rep_rate, smoothing_window)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=times,
                y=rate_for_fit,
                mode="lines",
                name="signal" if smoothing_window <= 1 else f"signal ({smoothing_window} pts)",
                line=dict(width=2.5, color="steelblue"),
                hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
            ))

            fit = _volk_hora_fit(times, rate_for_fit)
            if fit is not None:
                stable = fit["stable"]
                unstable = fit["unstable"]
                ts = [fit["t_fit_start"], fit["t_cross"]]
                ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
                tu = [fit["t_cross"], fit["t_fit_end"]]
                yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
                k_stable = fit["kstable"]
                fig.add_trace(go.Scatter(
                    x=ts, y=ys, mode="lines", name="stable fit",
                    line=dict(width=2.5, color="seagreen"),
                    hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>stable</extra>",
                ))
                fig.add_trace(go.Scatter(
                    x=tu, y=yu, mode="lines", name="unstable fit",
                    line=dict(width=2.5, color="firebrick"),
                    hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>unstable</extra>",
                ))
                fig.add_trace(go.Scatter(
                    x=[fit["t_cross"]], y=[fit["y_cross"]],
                    mode="markers", name="intersection",
                    marker=dict(size=11, color="#facc15", symbol="x"),
                    hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra>intersection</extra>",
                ))
                fig.add_annotation(
                    xref="paper", yref="paper", x=0.01, y=0.98,
                    text="V&H zone: n=%d, alpha=%.2f, t=%.4f s, ε₁=%.4f, ε₂=%.4f" % (
                        len(zone), alpha, times[k_stable], rep_e1[k_stable], rep_e2[k_stable]
                    ),
                    showarrow=False,
                )
            else:
                fig.add_annotation(
                    xref="paper", yref="paper", x=0.01, y=0.98,
                    text="Fit unavailable for connected V&H zone",
                    showarrow=False,
                    font=dict(color="firebrick"),
                )

            fig.update_layout(
                title="Volk-Hora Signal from Connected High-Thinning-Rate Zone",
                xaxis_title="Time [s]",
                yaxis_title="Mean thinning rate d(ε₁+ε₂)/dt [1/s]",
                template="plotly_white",
                height=450,
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1.0, title=None,
                    itemclick="toggleothers",
                ),
                margin=dict(t=70, r=20),
            )
            return _strip_plot_descriptions(fig), None

        med, reason = _cluster_median_df(job_dir)
        if med is None:
            return None, reason

        t = med["time_s"].tolist()
        e1 = med["eps1_major"].tolist()
        e2 = med["eps2_minor"].tolist()
        strain_sum = (med["eps1_major"] + med["eps2_minor"]).tolist()
        rate = [0.0] * len(t)
        for i in range(len(t)):
            if i == 0:
                dt = t[1] - t[0]
                rate[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
            elif i == len(t) - 1:
                dt = t[i] - t[i - 1]
                rate[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
            else:
                dt = t[i + 1] - t[i - 1]
                rate[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0

        rate_for_fit = _moving_average(rate, smoothing_window)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t,
            y=rate_for_fit,
            mode="lines",
            name="signal" if smoothing_window <= 1 else f"signal ({smoothing_window} pts)",
            line=dict(width=2.5, color="steelblue"),
            hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
        ))

        fit = _volk_hora_fit(t, rate_for_fit)
        if fit is not None:
            stable = fit["stable"]
            unstable = fit["unstable"]
            ts = [fit["t_fit_start"], fit["t_cross"]]
            ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
            tu = [fit["t_cross"], fit["t_fit_end"]]
            yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
            k_stable = fit["kstable"]
            fig.add_trace(go.Scatter(
                x=ts,
                y=ys,
                mode="lines",
                name="stable fit",
                line=dict(width=2.5, color="seagreen"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>stable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=tu,
                y=yu,
                mode="lines",
                name="unstable fit",
                line=dict(width=2.5, color="firebrick"),
                hovertemplate="t=%{x:.4f} s<br>fit=%{y:.5g} 1/s<extra>unstable</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=[fit["t_cross"]],
                y=[fit["y_cross"]],
                mode="markers",
                name="intersection",
                marker=dict(size=11, color="#facc15", symbol="x"),
                hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra>intersection</extra>",
            ))
            fig.add_annotation(
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.98,
                text="V&H point: t=%.4f s, ε₁=%.4f, ε₂=%.4f" % (
                    t[k_stable], e1[k_stable], e2[k_stable]
                ),
                showarrow=False,
            )
        else:
            fig.add_annotation(
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.98,
                text="Fit unavailable for this cluster/window",
                showarrow=False,
                font=dict(color="firebrick"),
            )

        fig.update_layout(
            title="Volk-Hora Signal from Top-5 Fracture-Neighborhood Median",
            xaxis_title="Time [s]",
            yaxis_title="d(ε₁+ε₂)/dt [1/s]",
            template="plotly_white",
            height=450,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1.0,
                title=None,
                itemclick="toggleothers",
            ),
            margin=dict(t=70, r=20),
        )
        return _strip_plot_descriptions(fig), None

    def _volk_hora_path(job_dir, smoothing_window=1, constrained=True):
        csv_path = os.path.join(job_dir, "strain_dome.csv")
        if not os.path.exists(csv_path):
            return None
        df = _load_csv(csv_path)
        required = {
            "time_s", "element_label", "integration_point",
            "centroid_x", "centroid_y", "eps1_major", "eps2_minor",
        }
        if not required <= set(df.columns):
            return None
        data = df.copy()
        for col in ("time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna(subset=["time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"])
        if data.empty:
            return None
        data["path_id"] = data["element_label"].astype(str) + "_IP" + data["integration_point"].astype(str)
        data = data.sort_values(["path_id", "time_s"])
        times = sorted(data["time_s"].dropna().unique().tolist())
        if len(times) < 5:
            return None

        path_data = {}
        centroids = {}
        for pid, grp in data.groupby("path_id"):
            grp = grp.drop_duplicates(subset=["time_s"]).sort_values("time_s")
            if len(grp) != len(times):
                continue
            if any(abs(float(a) - float(b)) > 1e-9 for a, b in zip(grp["time_s"].tolist(), times)):
                continue
            e1_vals = grp["eps1_major"].tolist()
            e2_vals = grp["eps2_minor"].tolist()
            strain_sum = [a + b for a, b in zip(e1_vals, e2_vals)]
            rate_vals = [0.0] * len(times)
            for i in range(len(times)):
                if i == 0:
                    dt = times[1] - times[0]
                    rate_vals[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
                elif i == len(times) - 1:
                    dt = times[i] - times[i - 1]
                    rate_vals[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                else:
                    dt = times[i + 1] - times[i - 1]
                    rate_vals[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
            path_data[pid] = {
                "e1": e1_vals,
                "e2": e2_vals,
                "rate": rate_vals,
                "element_label": str(int(float(grp["element_label"].iloc[0]))),
            }
            centroids[pid] = (float(grp["centroid_x"].iloc[0]), float(grp["centroid_y"].iloc[0]))

        if len(path_data) < 3:
            return None

        pids = list(path_data.keys())
        nearest = []
        for i, pid in enumerate(pids):
            x0, y0 = centroids[pid]
            ds = []
            for j, qid in enumerate(pids):
                if i == j:
                    continue
                x1, y1 = centroids[qid]
                ds.append(math.hypot(x1 - x0, y1 - y0))
            if ds:
                nearest.append(min(ds))
        conn_radius = 1.6 * sorted(nearest)[len(nearest) // 2] if nearest else 2.0
        conn_radius = max(conn_radius, 1e-6)

        admissible = set(pids)
        anchor_points = []
        if constrained:
            anchor_points, fracture_n = _fracture_cluster_anchor(job_dir)
            if not anchor_points:
                return None
            admissible &= _paths_within_anchor_hops(
                pids, centroids, anchor_points, conn_radius, VH_FRACTURE_HOPS
            )
            if not admissible:
                return None

        k_eval = max(1, len(times) - 2)
        rates_eval = sorted([path_data[p]["rate"][k_eval] for p in admissible], reverse=True)
        top_n = min(5, len(rates_eval))
        if top_n <= 0:
            return None
        rep_max = sum(rates_eval[:top_n]) / float(top_n)
        threshold = VH_ALPHA * rep_max
        hot = [pid for pid in admissible if path_data[pid]["rate"][k_eval] >= threshold]
        if not hot:
            return None

        hot_set = set(hot)
        components = []
        while hot_set:
            seed = hot_set.pop()
            comp = [seed]
            stack = [seed]
            while stack:
                pid = stack.pop()
                x0, y0 = centroids[pid]
                neighbors = []
                for qid in list(hot_set):
                    x1, y1 = centroids[qid]
                    if math.hypot(x1 - x0, y1 - y0) <= conn_radius:
                        neighbors.append(qid)
                for qid in neighbors:
                    hot_set.remove(qid)
                    stack.append(qid)
                    comp.append(qid)
            components.append(comp)
        if not components:
            return None

        zone = max(
            components,
            key=lambda comp: sum(path_data[p]["rate"][k_eval] for p in comp) / float(len(comp)),
        )
        rep_rate = []
        rep_e1 = []
        rep_e2 = []
        for i in range(len(times)):
            rep_rate.append(sum(path_data[p]["rate"][i] for p in zone) / float(len(zone)))
            rep_e1.append(sum(path_data[p]["e1"][i] for p in zone) / float(len(zone)))
            rep_e2.append(sum(path_data[p]["e2"][i] for p in zone) / float(len(zone)))

        fit = _volk_hora_fit(times, _moving_average(rep_rate, smoothing_window))
        k_stable = fit["kstable"] if fit is not None else len(times) - 1
        return {
            "time": times,
            "e1": rep_e1,
            "e2": rep_e2,
            "rate": rep_rate,
            "end_e1": float(rep_e1[k_stable]),
            "end_e2": float(rep_e2[k_stable]),
            "end_time": float(times[k_stable]),
            "zone_n": len(zone),
            "constraint_n": len(admissible),
            "constrained": bool(constrained),
            "top_n": top_n,
            "alpha": VH_ALPHA,
        }

    def _volk_hora_dome_rate_fig(job_dir, smoothing_window=20):
        anchor_points, fracture_n = _fracture_cluster_anchor(job_dir)
        if not anchor_points:
            return None, "fracture cluster not found; rerun postprocessing to generate strain_cluster_faces.csv"
        return _volk_hora_connected_zone_fig(
            os.path.join(job_dir, "strain_dome.csv"),
            "Fracture-Constrained Volk-Hora Signal",
            prefer_fracture_center=True,
            smoothing_window=smoothing_window,
            anchor_points=anchor_points,
            anchor_name="fracture cluster",
            anchor_hops=VH_FRACTURE_HOPS,
        )

    def _volk_hora_zone_location_fig(csv_path, title, prefer_fracture_center,
                                     weight_by_area=False, anchor_points=None,
                                     anchor_name=None, anchor_radius=None,
                                     allowed_labels=None, anchor_hops=None):
        if not os.path.exists(csv_path):
            return None, os.path.basename(csv_path) + " not found"
        df = _load_csv(csv_path)
        required = {
            "time_s", "element_label", "integration_point",
            "centroid_x", "centroid_y", "eps1_major", "eps2_minor",
        }
        if not required <= set(df.columns):
            return None, os.path.basename(csv_path) + " is missing required columns"

        data = df.copy()
        for col in ("time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        if "top_face_area" in data.columns:
            data["top_face_area"] = pd.to_numeric(data["top_face_area"], errors="coerce")
        else:
            data["top_face_area"] = 1.0
        data["top_face_area"] = data["top_face_area"].fillna(1.0).clip(lower=1e-12)
        data = data.dropna(subset=["time_s", "centroid_x", "centroid_y", "eps1_major", "eps2_minor"])
        if data.empty:
            return None, os.path.basename(csv_path) + " has no usable rows"
        data["path_id"] = data["element_label"].astype(str) + "_IP" + data["integration_point"].astype(str)
        times = sorted(data["time_s"].dropna().unique().tolist())
        if len(times) < 5:
            return None, "not enough frames for V&H zone location"

        path_data = {}
        centroids = {}
        for pid, grp in data.groupby("path_id"):
            grp = grp.drop_duplicates(subset=["time_s"]).sort_values("time_s")
            if len(grp) != len(times):
                continue
            e1_vals = grp["eps1_major"].tolist()
            e2_vals = grp["eps2_minor"].tolist()
            strain_sum = [a + b for a, b in zip(e1_vals, e2_vals)]
            rate_vals = [0.0] * len(times)
            for i in range(len(times)):
                if i == 0:
                    dt = times[1] - times[0]
                    rate_vals[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
                elif i == len(times) - 1:
                    dt = times[i] - times[i - 1]
                    rate_vals[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                else:
                    dt = times[i + 1] - times[i - 1]
                    rate_vals[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
            path_data[pid] = {
                "rate": rate_vals,
                "weight": float(grp["top_face_area"].iloc[0]) if weight_by_area else 1.0,
                "element_label": str(int(float(grp["element_label"].iloc[0]))),
            }
            centroids[pid] = (float(grp["centroid_x"].iloc[0]), float(grp["centroid_y"].iloc[0]))

        if len(path_data) < 3:
            return None, "not enough complete paths"

        pids = list(path_data.keys())
        nearest = []
        for i, pid in enumerate(pids):
            x0, y0 = centroids[pid]
            ds = []
            for j, qid in enumerate(pids):
                if i == j:
                    continue
                x1, y1 = centroids[qid]
                ds.append(math.hypot(x1 - x0, y1 - y0))
            if ds:
                nearest.append(min(ds))
        conn_radius = 1.6 * sorted(nearest)[len(nearest) // 2] if nearest else 2.0
        conn_radius = max(conn_radius, 1e-6)

        admissible = set(pids)
        allowed_labels = set(allowed_labels or [])
        if allowed_labels:
            admissible &= {pid for pid in pids if path_data[pid]["element_label"] in allowed_labels}
        if anchor_points and anchor_radius is not None:
            r = float(anchor_radius)
            admissible &= {
                pid for pid in pids
                if min(
                    math.hypot(centroids[pid][0] - ax, centroids[pid][1] - ay)
                    for ax, ay in anchor_points
                ) <= r
            }
        hop_allowed = _paths_within_anchor_hops(
            pids, centroids, anchor_points, conn_radius, anchor_hops
        ) if anchor_points and anchor_hops is not None else set(pids)
        admissible &= hop_allowed
        if not admissible:
            return None, "no V&H candidates inside fracture-constrained neighborhood"

        k_eval = max(1, len(times) - 2)
        rates_eval = sorted([path_data[p]["rate"][k_eval] for p in admissible], reverse=True)
        top_n = min(5, len(rates_eval))
        rep_max = sum(rates_eval[:top_n]) / float(top_n)
        alpha = VH_ALPHA
        threshold = alpha * rep_max
        hot = [pid for pid in admissible if path_data[pid]["rate"][k_eval] >= threshold]
        if not hot:
            return None, "no high-thinning-rate candidates found inside fracture-constrained neighborhood"

        hot_set = set(hot)
        components = []
        while hot_set:
            seed = hot_set.pop()
            comp = [seed]
            stack = [seed]
            while stack:
                pid = stack.pop()
                x0, y0 = centroids[pid]
                neighbors = []
                for qid in list(hot_set):
                    x1, y1 = centroids[qid]
                    if math.hypot(x1 - x0, y1 - y0) <= conn_radius:
                        neighbors.append(qid)
                for qid in neighbors:
                    hot_set.remove(qid)
                    stack.append(qid)
                    comp.append(qid)
            components.append(comp)

        center_xy = None
        anchor_points = list(anchor_points or [])
        if prefer_fracture_center and {"fracture_center_x", "fracture_center_y"} <= set(data.columns):
            cx = pd.to_numeric(data["fracture_center_x"], errors="coerce").dropna()
            cy = pd.to_numeric(data["fracture_center_y"], errors="coerce").dropna()
            if not cx.empty and not cy.empty:
                center_xy = (float(cx.iloc[0]), float(cy.iloc[0]))

        def comp_score(comp):
            wsum = sum(path_data[p]["weight"] for p in comp)
            mean_rate = sum(path_data[p]["weight"] * path_data[p]["rate"][k_eval] for p in comp) / wsum
            if anchor_points:
                min_dist = min(
                    math.hypot(centroids[p][0] - ax, centroids[p][1] - ay)
                    for p in comp
                    for ax, ay in anchor_points
                )
                return (-min_dist, mean_rate, wsum)
            if center_xy is None:
                return (mean_rate, wsum)
            cx0, cy0 = center_xy
            min_dist = min(math.hypot(centroids[p][0] - cx0, centroids[p][1] - cy0) for p in comp)
            return (-min_dist, mean_rate)

        zone = set(max(components, key=comp_score))
        zone_weight = sum(path_data[p]["weight"] for p in zone)
        hot_set_all = set(hot)
        top5_set = set(sorted(admissible, key=lambda p: path_data[p]["rate"][k_eval], reverse=True)[:top_n])
        hot_list = sorted(hot, key=lambda p: path_data[p]["rate"][k_eval], reverse=True)
        top5_list = sorted(top5_set, key=lambda p: path_data[p]["rate"][k_eval], reverse=True)
        admissible_list = sorted(admissible - set(hot), key=lambda p: path_data[p]["rate"][k_eval], reverse=True)

        fig = go.Figure()
        outline_fp = os.path.join(os.path.dirname(csv_path), "specimen_outline.csv")
        if os.path.exists(outline_fp):
            outline = _load_csv(outline_fp)
            needed = {"x1", "y1", "x2", "y2"}
            if needed <= set(outline.columns):
                xs = []
                ys = []
                for _, row in outline.iterrows():
                    xs.extend([row["x1"], row["x2"], None])
                    ys.extend([row["y1"], row["y2"], None])
                fig.add_trace(go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name="specimen contour",
                    line=dict(color="#e5e7eb", width=2),
                    hoverinfo="skip",
                ))
        if admissible_list:
            fig.add_trace(go.Scattergl(
                x=[centroids[p][0] for p in admissible_list],
                y=[centroids[p][1] for p in admissible_list],
                mode="markers",
                name="constraint zone",
                marker=dict(size=5, color="rgba(107, 114, 128, 0.35)"),
                customdata=[path_data[p]["rate"][k_eval] for p in admissible_list],
                hovertemplate="x=%{x:.3f} mm<br>y=%{y:.3f} mm<br>rate=%{customdata:.5g}<extra>constraint zone</extra>",
            ))
        if hot_list:
            fig.add_trace(go.Scattergl(
                x=[centroids[p][0] for p in hot_list],
                y=[centroids[p][1] for p in hot_list],
                mode="markers",
                name="thresholded",
                marker=dict(size=7, color="rgba(251, 191, 36, 0.62)"),
                customdata=[path_data[p]["rate"][k_eval] for p in hot_list],
                hovertemplate="x=%{x:.3f} mm<br>y=%{y:.3f} mm<br>rate=%{customdata:.5g}<extra>thresholded</extra>",
            ))
        if top5_list:
            fig.add_trace(go.Scattergl(
                x=[centroids[p][0] for p in top5_list],
                y=[centroids[p][1] for p in top5_list],
                mode="markers",
                name="top 5 max set",
                marker=dict(size=10, color="#2563eb", symbol="diamond", line=dict(width=1, color="white")),
                customdata=[path_data[p]["rate"][k_eval] for p in top5_list],
                hovertemplate="x=%{x:.3f} mm<br>y=%{y:.3f} mm<br>rate=%{customdata:.5g}<extra>top 5 max set</extra>",
            ))
        if center_xy is not None:
            fig.add_trace(go.Scatter(
                x=[center_xy[0]],
                y=[center_xy[1]],
                mode="markers",
                name="first deletion",
                marker=dict(size=13, symbol="x", color="red", line=dict(width=2, color="red")),
                hovertemplate="x=%{x:.3f} mm<br>y=%{y:.3f} mm<extra>first deletion</extra>",
            ))
        if anchor_points:
            fig.add_trace(go.Scattergl(
                x=[p[0] for p in anchor_points],
                y=[p[1] for p in anchor_points],
                mode="markers",
                name=anchor_name or "fracture cluster",
                marker=dict(size=7, color="rgba(220, 38, 38, 0.72)", line=dict(width=1, color="white")),
                hovertemplate="x=%{x:.3f} mm<br>y=%{y:.3f} mm<extra>fracture cluster</extra>",
            ))
            if anchor_radius is not None:
                circle_x = []
                circle_y = []
                ax0 = sum(p[0] for p in anchor_points) / float(len(anchor_points))
                ay0 = sum(p[1] for p in anchor_points) / float(len(anchor_points))
                for i in range(121):
                    a = 2.0 * math.pi * i / 120.0
                    circle_x.append(ax0 + float(anchor_radius) * math.cos(a))
                    circle_y.append(ay0 + float(anchor_radius) * math.sin(a))
                fig.add_trace(go.Scatter(
                    x=circle_x,
                    y=circle_y,
                    mode="lines",
                    name="anchor radius",
                    line=dict(color="rgba(220, 38, 38, 0.75)", width=1.2, dash="dash"),
                    hoverinfo="skip",
                ))

        fig.update_layout(
            title=title,
            xaxis_title="X [mm]",
            yaxis_title="Y [mm]",
            template="plotly_white",
            height=430,
            hovermode="closest",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
                title=None,
            ),
            margin=dict(t=65, r=20, b=95),
        )
        fig.update_yaxes(scaleanchor="x", scaleratio=1)
        fig.add_annotation(
            xref="paper", yref="paper", x=0.01, y=0.98,
            text=(
                "alpha=%.2f, top%d max, used n=%d, A=%.2f mm², high-rate n=%d%s"
                if weight_by_area else
                "alpha=%.2f, top%d max, used n=%d, high-rate n=%d%s"
            ) % (
                (alpha, top_n, len(zone), zone_weight, len(hot),
                     ", anchored to %s%s%s" % (
                         anchor_name,
                         " within %.1f mm" % float(anchor_radius) if anchor_radius is not None else "",
                         ", max %d hops" % int(anchor_hops) if anchor_hops is not None else
                         ", neighborhood-limited" if allowed_labels else "",
                     ) if anchor_points and anchor_name else "")
                if weight_by_area else
                (alpha, top_n, len(zone), len(hot),
                 ", anchored to %s%s%s" % (
                     anchor_name,
                     " within %.1f mm" % float(anchor_radius) if anchor_radius is not None else "",
                     ", max %d hops" % int(anchor_hops) if anchor_hops is not None else
                     ", neighborhood-limited" if allowed_labels else "",
                 ) if anchor_points and anchor_name else "")
            ),
            showarrow=False,
        )
        return _strip_plot_descriptions(fig), None

    def _strain_cluster_fig(job_dir):
        fp = _resolve_job_file(job_dir, "strain_cluster.csv")
        if not os.path.exists(fp):
            return None, "strain_cluster.csv not found in %s; rerun postprocessing and sync results" % job_dir

        df = _load_csv(fp)
        required = {
            "element_label", "integration_point",
            "eps1_major", "eps2_minor", "selection_rank",
        }
        if not required <= set(df.columns):
            return None, "strain_cluster.csv is missing required columns"

        data = df.copy()
        for col in ("eps1_major", "eps2_minor", "selection_rank"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna(subset=["eps1_major", "eps2_minor", "selection_rank"])
        if data.empty:
            return None, "strain_cluster.csv has no usable rows"

        if "time_s" in data.columns:
            data["time_s"] = pd.to_numeric(data["time_s"], errors="coerce")
            data = data.sort_values(["selection_rank", "time_s"])
        else:
            data = data.sort_values(["selection_rank"])

        data["path_id"] = (
            data["element_label"].astype(str) + " IP" +
            data["integration_point"].astype(str)
        )

        fig = go.Figure()
        for path_id, grp in data.groupby("path_id", sort=False):
            rank = int(grp["selection_rank"].iloc[0])
            fig.add_trace(go.Scatter(
                x=grp["eps2_minor"],
                y=grp["eps1_major"],
                mode="lines",
                name=path_id,
                legendgroup="cluster",
                showlegend=False,
                opacity=0.18,
                line=dict(color="#4b5563", width=1),
                hovertemplate=(
                    path_id + "<br>rank=" + str(rank) +
                "<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>top-5 cluster</extra>"
                ),
            ))

        grouped = data.groupby("time_s", dropna=True) if "time_s" in data.columns else None
        if grouped is not None and data["time_s"].notna().any():
            med = grouped[["eps1_major", "eps2_minor"]].median().reset_index()
            med = med.sort_values("time_s")
            avg = grouped[["eps1_major", "eps2_minor"]].mean().reset_index()
            avg = avg.sort_values("time_s")
            fig.add_trace(go.Scatter(
                x=med["eps2_minor"],
                y=med["eps1_major"],
                mode="lines",
                name="median",
                line=dict(color="#dc2626", width=3),
                hovertemplate="ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>median</extra>",
            ))
            fig.add_trace(go.Scatter(
                x=avg["eps2_minor"],
                y=avg["eps1_major"],
                mode="lines",
                name="average",
                line=dict(color="#2563eb", width=3, dash="dash"),
                hovertemplate="ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>average</extra>",
            ))

        n_paths = data["path_id"].nunique()
        fig.update_layout(
            title="Top-5 Fracture-Neighborhood Strain-Path Cluster",
            xaxis_title="ε₂ minor strain (-)",
            yaxis_title="ε₁ major strain (-)",
            template="plotly_white",
            height=520,
            hovermode="closest",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1.0,
                title=None,
                itemclick="toggleothers",
            ),
            margin=dict(t=80, r=20),
        )
        fig.add_annotation(
            xref="paper", yref="paper", x=0.01, y=0.99,
            text="%d paths: top-surface elements near first deletion with highest pre-fracture ε₁" % n_paths,
            showarrow=False,
        )
        fig.add_vline(x=0, line_width=0.6, line_dash="dot", line_color="gray")
        fig.add_hline(y=0, line_width=0.6, line_dash="dot", line_color="gray")
        return _strip_plot_descriptions(fig), None

    def _strain_path_compare_fig(job_dir):
        fig, reason = _strain_cluster_fig(job_dir)
        if fig is None:
            return None, reason
        vh = _volk_hora_path(job_dir, smoothing_window=1)
        if vh is None:
            return None, "V&H representative path unavailable; rerun postprocessing to generate strain_dome.csv"
        fig.add_trace(go.Scatter(
            x=vh["e2"],
            y=vh["e1"],
            mode="lines",
            name="constrained V&H zone average",
            line=dict(color="#111827", width=3.2),
            hovertemplate="ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>constrained V&H zone average</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[vh["end_e2"]],
            y=[vh["end_e1"]],
            mode="markers",
            name="constrained V&H limit",
            marker=dict(size=11, symbol="x", color="#111827", line=dict(width=2, color="#111827")),
            hovertemplate=(
                "ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<br>"
                + "t=%.4f s<br>zone n=%d<extra>constrained V&H limit</extra>"
                % (vh["end_time"], vh["zone_n"])
            ),
        ))
        fig.update_layout(title="Strain Path Comparison")
        return _strip_plot_descriptions(fig), None

    def _cluster_location_fig(job_dir):
        cluster_fp = _resolve_job_file(job_dir, "strain_cluster.csv")
        if not os.path.exists(cluster_fp):
            return None, "strain_cluster.csv not found"
        df = _load_csv(cluster_fp)
        required = {"centroid_x", "centroid_y", "eps1_major", "selection_rank"}
        if not required <= set(df.columns):
            return None, "strain_cluster.csv is missing cluster-location columns"

        data = df.copy()
        for col in ("centroid_x", "centroid_y", "eps1_major", "selection_rank"):
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.dropna(subset=["centroid_x", "centroid_y", "eps1_major", "selection_rank"])
        if data.empty:
            return None, "strain_cluster.csv has no usable location rows"

        if "time_s" in data.columns:
            data["time_s"] = pd.to_numeric(data["time_s"], errors="coerce")
            last_t = data["time_s"].max()
            data_last = data[data["time_s"] == last_t].copy()
        else:
            data_last = data.copy()

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Specimen", "Fracture Neighborhood"),
            horizontal_spacing=0.08,
        )

        center_xy = None
        if {"fracture_center_x", "fracture_center_y"} <= set(data.columns):
            cx = pd.to_numeric(data["fracture_center_x"], errors="coerce").dropna()
            cy = pd.to_numeric(data["fracture_center_y"], errors="coerce").dropna()
            if not cx.empty and not cy.empty:
                center_xy = (float(cx.iloc[0]), float(cy.iloc[0]))

        def _add_trace_both(trace):
            fig.add_trace(trace, row=1, col=1)
            zoom_trace = go.Figure(data=[trace]).data[0]
            zoom_trace.showlegend = False
            fig.add_trace(zoom_trace, row=1, col=2)

        outline_fp = os.path.join(job_dir, "specimen_outline.csv")
        if os.path.exists(outline_fp):
            outline = _load_csv(outline_fp)
            needed = {"x1", "y1", "x2", "y2"}
            if needed <= set(outline.columns):
                xs = []
                ys = []
                for _, row in outline.iterrows():
                    xs.extend([row["x1"], row["x2"], None])
                    ys.extend([row["y1"], row["y2"], None])
                _add_trace_both(go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name="outline",
                    line=dict(color="#e5e7eb", width=2),
                    hoverinfo="skip",
                ))

        face_fp = _resolve_job_file(job_dir, "strain_cluster_faces.csv")
        drew_faces = False
        fracture_face_count = 0
        strain_face_count = 0
        if os.path.exists(face_fp):
            faces = _load_csv(face_fp)
            needed = {"element_label", "role", "selection_rank", "point_order", "x", "y"}
            if needed <= set(faces.columns):
                for col in ("selection_rank", "point_order", "x", "y"):
                    faces[col] = pd.to_numeric(faces[col], errors="coerce")
                faces = faces.dropna(subset=["element_label", "role", "point_order", "x", "y"])
                role_text = faces["role"].astype(str)
                fracture_face_count = int(faces[
                    role_text.isin(["fracture_deleted", "crack_deleted"])
                ]["element_label"].nunique())
                strain_face_count = int(faces[
                    role_text == "cluster"
                ]["element_label"].nunique())
                faces["role_priority"] = role_text.map({
                    "cluster": 1,
                    "fracture_deleted": 2,
                    "crack_deleted": 2,
                    "first_deleted": 3,
                }).fillna(1)
                faces = faces.sort_values([
                    "role_priority", "selection_rank", "element_label", "point_order"
                ])
                shown = set()
                for (role, label), grp in faces.groupby(["role", "element_label"], sort=False):
                    grp = grp.sort_values("point_order")
                    xs = grp["x"].tolist()
                    ys = grp["y"].tolist()
                    if len(xs) < 3:
                        continue
                    xs.append(xs[0])
                    ys.append(ys[0])
                    role_s = str(role)
                    is_first = role_s == "first_deleted"
                    is_fracture_cluster = role_s in {"fracture_deleted", "crack_deleted"}
                    if is_first:
                        name = "first deletion"
                        color = "rgba(255, 255, 255, 0.05)"
                        line_color = "#ffffff"
                    elif is_fracture_cluster:
                        name = "fracture element cluster"
                        color = "rgba(220, 38, 38, 0.68)"
                        line_color = "#ffffff"
                    else:
                        name = "strain-path cells"
                        color = "rgba(249, 115, 22, 0.42)"
                        line_color = "#fed7aa"
                    _add_trace_both(go.Scatter(
                        x=xs,
                        y=ys,
                        mode="lines",
                        fill="toself",
                        name=name,
                        legendgroup=name,
                        showlegend=name not in shown,
                        line=dict(
                            color=line_color,
                            width=2.3 if (is_first or is_fracture_cluster) else 1.0,
                        ),
                        fillcolor=color,
                        hovertemplate=(
                            "element=%s<br>x=%%{x:.3f} mm<br>y=%%{y:.3f} mm<extra>%s</extra>"
                            % (str(label), name)
                        ),
                    ))
                    shown.add(name)
                    drew_faces = True

        if not drew_faces:
            _add_trace_both(go.Scatter(
                x=data_last["centroid_x"],
                y=data_last["centroid_y"],
                mode="markers",
                name="cluster",
                marker=dict(
                    size=8,
                    color="#f97316",
                    line=dict(width=0.5, color="white"),
                ),
                customdata=data_last[["selection_rank", "eps1_major"]],
                hovertemplate=(
                    "x=%{x:.3f} mm<br>y=%{y:.3f} mm"
                    "<br>rank=%{customdata[0]:.0f}<br>ε₁=%{customdata[1]:.4f}"
                    "<extra>cluster</extra>"
                ),
            ))

        if center_xy is not None:
                x0, y0 = center_xy
                if not drew_faces:
                    _add_trace_both(go.Scatter(
                        x=[x0], y=[y0],
                        mode="markers",
                        name="first deletion",
                        marker=dict(size=14, symbol="x", color="red", line=dict(width=2, color="red")),
                        hovertemplate="x=%{x:.3f} mm<br>y=%{y:.3f} mm<extra>first deleted</extra>",
                    ))

        _add_trace_both(go.Scatter(
            x=[0.0],
            y=[0.0],
            mode="markers",
            name="apex",
            marker=dict(size=10, symbol="cross", color="#2563eb"),
            hovertemplate="x=0<br>y=0<extra>apex</extra>",
        ))

        if center_xy is not None:
            x0, y0 = center_xy
            zoom_radius = 7.0
            fig.update_xaxes(range=[x0 - zoom_radius, x0 + zoom_radius], row=1, col=2)
            fig.update_yaxes(range=[y0 - zoom_radius, y0 + zoom_radius], row=1, col=2)

        fig.update_layout(
            title="Top-5 Cluster Location",
            xaxis_title="X [mm]",
            yaxis_title="Y [mm]",
            template="plotly_white",
            height=560,
            hovermode="closest",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.16,
                xanchor="center",
                x=0.5,
                title=None,
                itemclick="toggleothers",
            ),
            margin=dict(t=80, r=35, b=95),
        )
        fig.update_xaxes(title_text="X [mm]", row=1, col=1)
        fig.update_yaxes(title_text="Y [mm]", row=1, col=1)
        fig.update_xaxes(title_text="X [mm]", row=1, col=2)
        fig.update_yaxes(title_text="Y [mm]", row=1, col=2)
        fig.update_yaxes(scaleanchor="x", scaleratio=1, row=1, col=1)
        fig.update_yaxes(scaleanchor="x2", scaleratio=1, row=1, col=2)
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=0.01,
            y=0.99,
            text=(
                "fracture elements=%d, strain-path cells=%d"
                % (fracture_face_count, strain_face_count)
                if fracture_face_count else
                "strain-path cells=%d" % data_last["element_label"].nunique()
            ),
            showarrow=False,
        )
        return _strip_plot_descriptions(fig), None

    # ── New diagnostic helpers ────────────────────────────────────────────────

    def _fracture_u3(job_dir):
        """Return (U3_frac_mm, fracture_type_str) or (None, None).

        Primary source: forming_limits.csv (fracture row, updated postproc format).
        Fallbacks for older result sets:
          - fracture_type: read from strain_path.csv last row (always present)
          - U3_mm: interpolate from punch_fd.csv total_time_s → U3_mm
        """
        fp = os.path.join(job_dir, "forming_limits.csv")
        if not os.path.exists(fp):
            return None, None
        df = _load_csv(fp)
        row = df[df["method"] == "fracture"]
        if row.empty:
            return None, None
        r = row.iloc[0]

        # fracture_type: forming_limits.csv (new format) or strain_path.csv (old)
        ft = str(r["fracture_type"]) if "fracture_type" in r.index and pd.notna(r.get("fracture_type")) else None
        if ft is None:
            sp_fp = os.path.join(job_dir, "strain_path.csv")
            if os.path.exists(sp_fp):
                try:
                    sp = _load_csv(sp_fp)
                    if not sp.empty and "fracture_type" in sp.columns:
                        ft = str(sp["fracture_type"].iloc[-1])
                except Exception:
                    pass

        # U3_mm: forming_limits.csv (new format) or interpolated from punch_fd.csv
        if "U3_mm" in r.index and pd.notna(r.get("U3_mm")) and str(r.get("U3_mm", "")) != "":
            return float(r["U3_mm"]), ft
        if "time_s" not in r.index:
            return None, ft
        t_frac = float(r["time_s"])
        fd_fp = os.path.join(job_dir, "punch_fd.csv")
        if os.path.exists(fd_fp):
            fdf = _load_csv(fd_fp)
            if "total_time_s" in fdf.columns and "U3_mm" in fdf.columns:
                fdf = fdf.sort_values("total_time_s").reset_index(drop=True)
                idx = max(0, fdf["total_time_s"].searchsorted(t_frac, side="left") - 1)
                return float(fdf["U3_mm"].iloc[idx]), ft
        return None, ft

    def _eps1_at_u3(job_dir, u3_ref_mm):
        """Interpolate ε₁ (and ε₂) at a fixed punch displacement u3_ref_mm.

        Uses punch_fd.csv (total_time_s, U3_mm) to find the simulation time
        corresponding to u3_ref_mm, then interpolates eps1_major from
        strain_path.csv at that time.  Returns (eps1, eps2) or (None, None)
        if data is missing or the job didn't reach u3_ref_mm.
        """
        import numpy as np
        fd_fp = os.path.join(job_dir, "punch_fd.csv")
        sp_fp = os.path.join(job_dir, "strain_path.csv")
        if not os.path.exists(fd_fp) or not os.path.exists(sp_fp):
            return None, None
        try:
            fdf = _load_csv(fd_fp)
            spdf = _load_csv(sp_fp)
        except Exception:
            return None, None
        if "total_time_s" not in fdf.columns or "U3_mm" not in fdf.columns:
            return None, None
        if "time_s" not in spdf.columns or "eps1_major" not in spdf.columns:
            return None, None
        fdf = fdf.sort_values("total_time_s").reset_index(drop=True)
        spdf = spdf.sort_values("time_s").reset_index(drop=True)
        # Job didn't reach the reference displacement
        if fdf["U3_mm"].max() < u3_ref_mm:
            return None, None
        # Time corresponding to reference U3 (linear interpolation)
        t_ref = float(np.interp(u3_ref_mm, fdf["U3_mm"].values, fdf["total_time_s"].values))
        eps1 = float(np.interp(t_ref, spdf["time_s"].values, spdf["eps1_major"].values))
        eps2 = float(np.interp(t_ref, spdf["time_s"].values, spdf["eps2_minor"].values)) \
               if "eps2_minor" in spdf.columns else None
        return eps1, eps2

    def _width_from_job(name):
        m = re.search(r'W(\d+)', str(name))
        return int(m.group(1)) if m else None

    def _fd_with_fracture_fig(job_dir, title_suffix=""):
        """F-d curve with fracture marker."""
        for fname in ("global.csv", "punch_fd.csv"):
            fp = os.path.join(job_dir, fname)
            if not os.path.exists(fp):
                continue
            df = _load_csv(fp)
            if "U3_mm" not in df.columns or "RF3_N" not in df.columns:
                continue
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["U3_mm"], y=df["RF3_N"],
                mode="lines", name="Punch force [N]",
                line=dict(color="#1f77b4", width=2),
            ))
            u3_frac, ft = _fracture_u3(job_dir)
            if u3_frac is not None:
                leg_name = f"Fracture — {ft}" if ft else "Fracture"
                y_top = float(df["RF3_N"].max()) * 1.05
                fig.add_trace(go.Scatter(
                    x=[u3_frac, u3_frac], y=[0, y_top],
                    mode="lines", name=leg_name,
                    line=dict(color="#d62728", width=1.5, dash="dash"),
                ))
            fig.update_layout(
                title=f"Punch Force–Displacement{title_suffix}",
                xaxis_title="Displacement [mm]",
                yaxis_title="Force [N]",
                template="plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
            )
            return _strip_plot_descriptions(fig)
        return None

    def _strain_path_extras_fig(job_dir):
        """β(t), thinning(t), d_dome_max(t) from strain_path.csv."""
        fp = os.path.join(job_dir, "strain_path.csv")
        if not os.path.exists(fp):
            return None
        df = _load_csv(fp)
        needed = {"time_s", "eps1_major", "eps2_minor"}
        if not needed <= set(df.columns):
            return None
        df = df.apply(pd.to_numeric, errors="coerce").dropna(subset=list(needed))
        df = df.sort_values("time_s")
        g = df.groupby("time_s", as_index=False)[list(df.columns)].mean()
        g["beta"] = g["eps2_minor"] / g["eps1_major"].replace(0, float("nan"))
        g["thinning"] = g["eps1_major"] + g["eps2_minor"]   # = -ε₃ > 0

        has_d     = "d_dome_max" in g.columns
        has_triax = "TRIAX" in g.columns
        panels = [
            ("Strain ratio  β = ε₂/ε₁",      "β  [–]",         "beta",     "#ff7f0e", "β = ε₂/ε₁  (strain ratio)"),
            ("Thinning  ε₁+ε₂  =  −ε₃",       "ε₁+ε₂  [–]",    "thinning", "#2ca02c", "ε₁+ε₂ = −ε₃  (thinning magnitude)"),
        ]
        if has_triax:
            panels.append(("Stress triaxiality  η", "η  [–]", "TRIAX", "#e377c2", "η = σ_m / σ_eq  (triaxiality)"))
        if has_d:
            panels.append(("Damage variable  D", "D  [–]", "d_dome_max", "#9467bd", "D_max  (max dome damage)"))

        n_rows = len(panels)
        fig = make_subplots(
            rows=n_rows, cols=1, shared_xaxes=True,
            vertical_spacing=0.10,
            subplot_titles=[p[0] for p in panels],
        )
        for row_i, (_, y_title, col, color, leg_name) in enumerate(panels, 1):
            if col not in g.columns:
                continue
            fig.add_trace(go.Scatter(
                x=g["time_s"], y=g[col],
                mode="lines", name=leg_name,
                line=dict(color=color, width=2),
            ), row=row_i, col=1)
            fig.update_yaxes(title_text=y_title, row=row_i, col=1)
        fig.update_xaxes(title_text="Time [s]", row=n_rows, col=1)
        fig.update_layout(
            height=190 * n_rows,
            template="plotly_white",
            margin=dict(t=60),
            legend=dict(orientation="h", yanchor="top", y=-0.10,
                        xanchor="center", x=0.5),
        )
        return _strip_plot_descriptions(fig)

    def _energy_fig_v2(job_dir):
        """KE/IE ratio — quasi-static validity check."""
        for fname in ("global.csv", "energy_data.csv"):
            fp = os.path.join(job_dir, fname)
            if not os.path.exists(fp):
                continue
            df = _load_csv(fp)
            if "ALLKE" not in df.columns or "ALLIE" not in df.columns:
                continue
            df = df[df["ALLIE"] > 0].copy()
            # Drop first 2 % of frames — initial transient can spike the axis
            n_trim = max(1, int(len(df) * 0.02))
            df = df.iloc[n_trim:].reset_index(drop=True)
            df["ratio"] = df["ALLKE"] / df["ALLIE"]
            x_col   = "U3_mm" if "U3_mm" in df.columns else "total_time_s"
            x_label = "Displacement [mm]" if x_col == "U3_mm" else "Time [s]"
            peak_y  = float(df["ratio"].max())
            x_min   = float(df[x_col].min())
            x_max   = float(df[x_col].max())

            fig = go.Figure()
            # Main ratio curve
            fig.add_trace(go.Scatter(
                x=df[x_col], y=df["ratio"],
                mode="lines", name="ALLKE / ALLIE",
                line=dict(color="#1f77b4", width=2),
            ))
            # 5 % ISO limit — named trace so it appears in legend
            fig.add_trace(go.Scatter(
                x=[x_min, x_max], y=[0.05, 0.05],
                mode="lines", name=f"5 % ISO limit  (peak = {peak_y:.4f})",
                line=dict(color="#888888", width=1.2, dash="dash"),
            ))
            # Fracture instant — named trace so it appears in legend
            u3_frac, ft = _fracture_u3(job_dir)
            if u3_frac is not None and x_col == "U3_mm":
                y_top = max(0.06, peak_y * 1.05)
                leg_name = f"Fracture — {ft}" if ft else "Fracture"
                fig.add_trace(go.Scatter(
                    x=[u3_frac, u3_frac], y=[0, y_top],
                    mode="lines", name=leg_name,
                    line=dict(color="#d62728", width=1.5, dash="solid"),
                ))
            fig.update_layout(
                title="KE / IE — quasi-static check",
                xaxis_title=x_label,
                yaxis_title="ALLKE / ALLIE",
                template="plotly_white",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
            )
            return _strip_plot_descriptions(fig)
        return None

    def _diagnostics_render(job_dir, key_prefix=""):
        """Fracture-type badge + ISO validity + β linearity summary."""
        u3_frac, ft = _fracture_u3(job_dir)
        fl_fp = os.path.join(job_dir, "forming_limits.csv")
        sp_fp = os.path.join(job_dir, "strain_path.csv")
        cols = st.columns(3)
        with cols[0]:
            if ft:
                colour = "green" if ft == "dome" else "red"
                st.markdown(f"**Fracture type:** :{colour}[{ft}]")
            else:
                st.markdown("**Fracture type:** —")
        with cols[1]:
            if u3_frac is not None:
                st.metric("U3 at fracture", f"{u3_frac:.1f} mm")
            else:
                st.metric("U3 at fracture", "—")
        with cols[2]:
            # β linearity: std-dev of β in the last 50% of the path
            if os.path.exists(sp_fp):
                sp = _load_csv(sp_fp)
                needed = {"time_s", "eps1_major", "eps2_minor"}
                if needed <= set(sp.columns):
                    sp = sp.apply(pd.to_numeric, errors="coerce").dropna(subset=list(needed))
                    g = sp.groupby("time_s")[["eps1_major", "eps2_minor"]].mean()
                    g["beta"] = g["eps2_minor"] / g["eps1_major"].replace(0, float("nan"))
                    g = g.dropna(subset=["beta"])
                    if len(g) >= 4:
                        half = g.iloc[len(g) // 2:]
                        beta_std = float(half["beta"].std())
                        st.metric("β std (2nd half)", f"{beta_std:.4f}",
                                  help="< 0.05 indicates a linear strain path")
                    else:
                        st.metric("β std (2nd half)", "—")
                else:
                    st.metric("β std (2nd half)", "—")
            else:
                st.metric("β std (2nd half)", "—")

        if os.path.exists(fl_fp):
            df_fl = _load_csv(fl_fp)
            st.dataframe(df_fl, use_container_width=True, hide_index=True)

        # TRIAX vs EQPS fracture path (reuse sp_fp from above)
        if os.path.exists(sp_fp):
            sp2 = _load_csv(sp_fp)
            if {"EQPS", "TRIAX"} <= set(sp2.columns):
                sp2 = sp2[["EQPS", "TRIAX", "time_s"]].apply(pd.to_numeric, errors="coerce").dropna()
                sp2 = sp2.groupby("time_s", as_index=False).mean().sort_values("time_s")
                if not sp2.empty:
                    fig_tx = go.Figure()
                    fig_tx.add_trace(go.Scatter(
                        x=sp2["EQPS"], y=sp2["TRIAX"],
                        mode="lines+markers",
                        name="Stress-state path",
                        line=dict(color="#1f77b4", width=2),
                        marker=dict(size=4, color=sp2["time_s"],
                                    colorscale="Viridis", showscale=True,
                                    colorbar=dict(title="Time [s]", thickness=12)),
                        hovertemplate="EQPS=%{x:.4f}<br>η=%{y:.4f}<extra></extra>",
                    ))
                    # Reference triaxiality lines for common stress states
                    for eta, label in [
                        (1/3,       "Uniaxial tension  η = 1/3"),
                        (0.577,     "Plane-strain  η ≈ 0.577"),
                        (2/3,       "Equibiaxial  η = 2/3"),
                    ]:
                        fig_tx.add_hline(y=eta, line_dash="dot", line_color="#bbbbbb",
                                         line_width=1,
                                         annotation_text=label,
                                         annotation_position="right",
                                         annotation_font_color="#888888")
                    fig_tx.update_layout(
                        title="Stress-state path: η vs EQPS",
                        xaxis_title="Equivalent plastic strain (EQPS)",
                        yaxis_title="Triaxiality η = σ_m / σ_eq",
                        template="plotly_white",
                        showlegend=False,
                        height=360,
                    )
                    _plotly_chart(fig_tx, use_container_width=True)

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
            _scan.clear()
            _load_csv.clear()
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
    if job_dirs:
        modes.append("Sensitivity")

    def _persisted_choice(label, options, key, default=None, **kwargs):
        options = list(options)
        if not options:
            return None
        fallback = default if default in options else options[0]
        if st.session_state.get(key) not in options:
            st.session_state[key] = fallback
        return st.selectbox(label, options, key=key, **kwargs)

    if st.session_state.get("results_view_mode") not in modes:
        st.session_state["results_view_mode"] = modes[0]
    view_mode = st.segmented_control(
        "View",
        modes,
        default=st.session_state["results_view_mode"],
        key="results_view_mode",
    )

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # Single Job view
    # ══════════════════════════════════════════════════════════════════════════
    if view_mode == "Single Job":

        sel = _persisted_choice("Job", list(job_dirs.keys()), "results_single_job")
        job_dir = job_dirs[sel]

        pngs = sorted(f for f in os.listdir(job_dir) if f.endswith(".png"))
        if pngs:
            img_cols = st.columns(min(len(pngs), 3))
            for i, png in enumerate(pngs):
                img_cols[i % 3].image(os.path.join(job_dir, png), use_container_width=True)

        _display_job_videos(job_dir)

        tab_fd, tab_sp, tab_cmp, tab_loc, tab_vh, tab_en, tab_fl, tab_diag = st.tabs(
            ["Force-Disp.", "Strain Path", "Path Compare", "Cluster Location", "V&H", "Energy", "Forming Limits", "Diagnostics"]
        )

        with tab_fd:
            fig_fd = _fd_with_fracture_fig(job_dir)
            if fig_fd is not None:
                _plotly_chart(fig_fd, use_container_width=True, key=f"fd_{sel}")
            else:
                st.info("Force–displacement data unavailable")

        with tab_sp:
            fig, reason = _strain_cluster_fig(job_dir)
            if fig is not None:
                _plotly_chart(fig, use_container_width=True, key=f"strain_path_cluster_{sel}")
            else:
                st.info(reason or "top-5 cluster strain path unavailable")
            fig_extras = _strain_path_extras_fig(job_dir)
            if fig_extras is not None:
                _plotly_chart(fig_extras, use_container_width=True, key=f"sp_extras_{sel}")

        with tab_cmp:
            fig, reason = _strain_path_compare_fig(job_dir)
            if fig is not None:
                _plotly_chart(fig, use_container_width=True, key=f"strain_path_compare_{sel}")
            else:
                st.info(reason or "strain-path comparison unavailable")

        with tab_loc:
            fig, reason = _cluster_location_fig(job_dir)
            if fig is not None:
                _plotly_chart(fig, use_container_width=True, key=f"cluster_location_{sel}")
            else:
                st.info(reason or "Cluster location data unavailable")

        with tab_vh:
            smoothing_window_combined = st.number_input(
                "V&H fit smoothing",
                min_value=1,
                max_value=101,
                value=1,
                step=2,
                key=f"vh_combined_smoothing_{sel}",
            )
            fig, reason = _volk_hora_dome_rate_fig(
                job_dir,
                smoothing_window=int(smoothing_window_combined),
            )
            if fig is not None:
                _plotly_chart(fig, use_container_width=True, key=f"vh_dome_{sel}")
            else:
                st.info(reason or "Independent dome Volk-Hora data unavailable")
            anchor_points, _fracture_n = _fracture_cluster_anchor(job_dir)
            if anchor_points:
                zone_fig, zone_reason = _volk_hora_zone_location_fig(
                    os.path.join(job_dir, "strain_dome.csv"),
                    "Fracture-Constrained V&H Zone Selection",
                    prefer_fracture_center=True,
                    anchor_points=anchor_points,
                    anchor_name="fracture cluster",
                    anchor_hops=VH_FRACTURE_HOPS,
                )
            else:
                zone_fig, zone_reason = None, "fracture cluster not found; rerun postprocessing to generate strain_cluster_faces.csv"
            if zone_fig is not None:
                _plotly_chart(zone_fig, use_container_width=True, key=f"vh_dome_zone_{sel}")
            else:
                st.info(zone_reason or "V&H dome zone location unavailable")

        with tab_en:
            fig_en = _energy_fig_v2(job_dir)
            if fig_en is not None:
                _plotly_chart(fig_en, use_container_width=True, key=f"energy_{sel}")
            else:
                st.info("Energy data unavailable")

        with tab_fl:
            fp = os.path.join(job_dir, "forming_limits.csv")
            if os.path.exists(fp):
                df = _load_csv(fp)
                st.dataframe(df, use_container_width=True, hide_index=True)

        with tab_diag:
            _diagnostics_render(job_dir, key_prefix=f"diag_{sel}")

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

        sel_flc = _persisted_choice("FLC set", list(flc_dirs.keys()), "results_full_flc_set")
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

        # ── Variant selector: filter to one suffix when multiple exist ────────
        def _job_variant(name):
            m = re.search(r'_ang\d+_(.*)', name)
            return m.group(1) if m else ''

        _variants = sorted(set(_job_variant(n) for n in sub_jobs))
        if len(_variants) > 1:
            _sel_variant = st.selectbox(
                "Variant",
                _variants,
                format_func=lambda v: v if v else '(default)',
                key="results_full_flc_variant",
            )
            sub_jobs = {n: d for n, d in sub_jobs.items()
                        if _job_variant(n) == _sel_variant}

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
            _df_agg = _load_csv(flc_csv)
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
                _dfl = _load_csv(_flim)
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

        def _cluster_path(job_dir, reducer="median"):
            fp = _resolve_job_file(job_dir, "strain_cluster.csv")
            if not os.path.exists(fp):
                return None
            df = _load_csv(fp)
            required = {"time_s", "eps1_major", "eps2_minor"}
            if not required <= set(df.columns):
                return None
            data = df[["time_s", "eps1_major", "eps2_minor"]].apply(pd.to_numeric, errors="coerce")
            data = data.dropna().sort_values("time_s")
            if data.empty:
                return None
            grouped = data.groupby("time_s", as_index=False)[["eps1_major", "eps2_minor"]]
            path = grouped.mean() if reducer == "average" else grouped.median()
            path = path.sort_values("time_s")
            if path.empty:
                return None
            return {
                "time": path["time_s"].tolist(),
                "e1": path["eps1_major"].tolist(),
                "e2": path["eps2_minor"].tolist(),
                "end_e1": float(path["eps1_major"].iloc[-1]),
                "end_e2": float(path["eps2_minor"].iloc[-1]),
                "end_time": float(path["time_s"].iloc[-1]),
            }

        def _add_fld_reference_lines(fig, e1_values):
            _L = max(max(e1_values), 0.8) * 1.3 if e1_values else 1.0
            fig.add_trace(go.Scatter(
                x=[-_L / 2, 0], y=[_L, 0], mode='lines', name='Uniaxial tension',
                line=dict(color='lightgray', width=1.2, dash='dashdot'), hoverinfo='skip',
            ))
            fig.add_trace(go.Scatter(
                x=[0, _L], y=[0, _L], mode='lines', name='Equibiaxial',
                line=dict(color='lightgray', width=1.2, dash='dash'), hoverinfo='skip',
            ))

        def _cluster_flc_fig(points, reducer="median"):
            cluster_pts = []
            for p in points:
                if not p.get("dir") or not os.path.isdir(p["dir"]):
                    continue
                path = _cluster_path(p["dir"], reducer=reducer)
                if path is None:
                    continue
                q = dict(p)
                q.update(path)
                cluster_pts.append(q)

            if not cluster_pts:
                return None

            fig = go.Figure()
            for p in cluster_pts:
                col = _cmap_flc.get(p["name"], "#4b5563")
                m = re.search(r'W\d+', p["name"])
                lbl = m.group(0) if m else p["name"]
                fig.add_trace(go.Scatter(
                    x=p["e2"], y=p["e1"], mode="lines",
                    legendgroup=p["name"], showlegend=False,
                    line=dict(color=col, width=1.4), opacity=0.35,
                    hoverinfo="skip",
                ))
                fig.add_trace(go.Scatter(
                    x=[p["end_e2"]], y=[p["end_e1"]],
                    mode="markers", name=lbl, legendgroup=p["name"],
                    marker=dict(size=9, color=col, line=dict(width=2, color=col)),
                    hovertemplate=(
                        lbl + "<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}"
                        "<br>t=" + ("%.4f" % p["end_time"]) + " s"
                        "<extra>top-5 " + reducer + " endpoint</extra>"
                    ),
                ))

            curve_pts = sorted(cluster_pts, key=lambda p: p["end_e2"])
            curve_name = "FLC (top-5 cluster %s)" % reducer
            curve_color = "red" if reducer == "median" else "#2563eb"
            fig.add_trace(go.Scatter(
                x=[p["end_e2"] for p in curve_pts],
                y=[p["end_e1"] for p in curve_pts],
                mode="lines+markers",
                name=curve_name,
                line=dict(color=curve_color, width=2.5),
                marker=dict(symbol="circle", size=8, color=curve_color),
                text=[
                    re.search(r'W\d+', p["name"]).group(0)
                    if re.search(r'W\d+', p["name"]) else p["name"]
                    for p in curve_pts
                ],
                hovertemplate="%{text}<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>top-5 " + reducer + " FLC</extra>",
            ))

            _e2v = [p["end_e2"] for p in cluster_pts]
            _e1v = [p["end_e1"] for p in cluster_pts]
            _add_fld_reference_lines(fig, _e1v)
            _pad = 0.2
            _xr = max(abs(min(_e2v)), abs(max(_e2v)), 1e-6)
            _x0, _x1 = -(1 + _pad) * _xr, (1 + _pad) * _xr
            _y0 = min(0.0, min(_e1v)) - _pad * (max(_e1v) - min(_e1v) + 1e-6)
            _y1 = max(_e1v) + _pad * (max(_e1v) - min(_e1v) + 1e-6)
            fig.update_layout(
                xaxis=dict(title='ε₂  minor strain  (–)', range=[_x0, _x1]),
                yaxis=dict(title='ε₁  major strain  (–)', range=[_y0, _y1]),
                title='Forming Limit Curve from Top-5 Fracture-Neighborhood ' + reducer.title(),
                legend_title='Specimen',
                hovermode='closest',
                template='plotly_white',
                height=550,
            )
            fig.add_vline(x=0, line_width=0.6, line_dash='dot', line_color='gray')
            fig.add_hline(y=0, line_width=0.6, line_dash='dot', line_color='gray')
            return fig

        def _vh_flc_fig(points):
            vh_pts = []
            for p in points:
                if not p.get("dir") or not os.path.isdir(p["dir"]):
                    continue
                path = _volk_hora_path(p["dir"], smoothing_window=1)
                if path is None:
                    continue
                q = dict(p)
                q.update(path)
                vh_pts.append(q)

            if not vh_pts:
                return None

            fig = go.Figure()
            for p in vh_pts:
                col = _cmap_flc.get(p["name"], "#4b5563")
                m = re.search(r'W\d+', p["name"])
                lbl = m.group(0) if m else p["name"]
                fig.add_trace(go.Scatter(
                    x=p["e2"], y=p["e1"], mode="lines",
                    legendgroup=p["name"], showlegend=False,
                    line=dict(color=col, width=1.4), opacity=0.35,
                    hoverinfo="skip",
                ))
                fig.add_trace(go.Scatter(
                    x=[p["end_e2"]], y=[p["end_e1"]],
                    mode="markers", name=lbl, legendgroup=p["name"],
                    marker=dict(size=9, color=col, line=dict(width=2, color=col)),
                    hovertemplate=(
                        lbl + "<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}"
                        + "<br>t=" + ("%.4f" % p["end_time"]) + " s"
                        + "<br>zone n=" + str(p["zone_n"])
                        + "<extra>constrained V&H endpoint</extra>"
                    ),
                ))

            curve_pts = sorted(vh_pts, key=lambda p: p["end_e2"])
            fig.add_trace(go.Scatter(
                x=[p["end_e2"] for p in curve_pts],
                y=[p["end_e1"] for p in curve_pts],
                mode="lines+markers",
                name="FLC (constrained V&H average)",
                line=dict(color="#111827", width=2.5),
                marker=dict(symbol="circle", size=8, color="#111827"),
                text=[
                    re.search(r'W\d+', p["name"]).group(0)
                    if re.search(r'W\d+', p["name"]) else p["name"]
                    for p in curve_pts
                ],
                hovertemplate="%{text}<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>constrained V&H FLC</extra>",
            ))

            _e2v = [p["end_e2"] for p in vh_pts]
            _e1v = [p["end_e1"] for p in vh_pts]
            _add_fld_reference_lines(fig, _e1v)
            _pad = 0.2
            _xr = max(abs(min(_e2v)), abs(max(_e2v)), 1e-6)
            _x0, _x1 = -(1 + _pad) * _xr, (1 + _pad) * _xr
            _y0 = min(0.0, min(_e1v)) - _pad * (max(_e1v) - min(_e1v) + 1e-6)
            _y1 = max(_e1v) + _pad * (max(_e1v) - min(_e1v) + 1e-6)
            fig.update_layout(
                xaxis=dict(title='ε₂  minor strain  (–)', range=[_x0, _x1]),
                yaxis=dict(title='ε₁  major strain  (–)', range=[_y0, _y1]),
                title='Forming Limit Curve from Fracture-Constrained V&H Average',
                legend_title='Specimen',
                hovermode='closest',
                template='plotly_white',
                height=550,
            )
            fig.add_vline(x=0, line_width=0.6, line_dash='dot', line_color='gray')
            fig.add_hline(y=0, line_width=0.6, line_dash='dot', line_color='gray')
            return fig

        # ── Draw FLC chart ────────────────────────────────────────────────────
        if _pts:
            chart_tab, median_tab, average_tab, vh_tab = st.tabs([
                "Fracture FLC", "Top-5 Median FLC", "Top-5 Average FLC", "Constrained V&H FLC"
            ])
            flc_fig = go.Figure()

            # Faint strain paths per specimen
            for _p in _pts:
                if not _p['dir'] or not os.path.isdir(_p['dir']):
                    continue
                _e1p, _e2p = None, None
                for _fn, _c1, _c2 in [('strain_path.csv', 'eps1_major', 'eps2_minor'),
                                       ('elout.csv',       'eps1_le',    'eps2_le')]:
                    _fp2 = os.path.join(_p['dir'], _fn)
                    if os.path.exists(_fp2):
                        _dfsp = _load_csv(_fp2)
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

            # Red FFLC — fracture curve (sorted left → right, dome points only)
            _dome_pts = sorted([p for p in _pts if p['valid']], key=lambda p: p['e2'])
            if _dome_pts:
                flc_fig.add_trace(go.Scatter(
                    x=[p['e2'] for p in _dome_pts],
                    y=[p['e1'] for p in _dome_pts],
                    mode='lines+markers', name='FFLC (fracture)',
                    line=dict(color='red', width=2),
                    marker=dict(symbol='circle', size=8, color='red'),
                    hovertemplate='%{text}<br>ε₂=%{x:.3f}<br>ε₁=%{y:.3f}<extra>Fracture</extra>',
                    text=[re.search(r'W\d+', p['name']).group(0)
                          if re.search(r'W\d+', p['name']) else p['name']
                          for p in _dome_pts],
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
            with chart_tab:
                _plotly_chart(flc_fig, use_container_width=True)
            with median_tab:
                cluster_fig = _cluster_flc_fig(_pts, reducer="median")
                if cluster_fig is not None:
                    _plotly_chart(cluster_fig, use_container_width=True)
                else:
                    st.info("No top-5 cluster median data found yet. Rerun postprocessing and sync results.")
            with average_tab:
                cluster_fig = _cluster_flc_fig(_pts, reducer="average")
                if cluster_fig is not None:
                    _plotly_chart(cluster_fig, use_container_width=True)
                else:
                    st.info("No top-5 cluster average data found yet. Rerun postprocessing and sync results.")
            with vh_tab:
                vh_fig = _vh_flc_fig(_pts)
                if vh_fig is not None:
                    _plotly_chart(vh_fig, use_container_width=True)
                else:
                    st.info("No V&H necking-zone path data found yet. Rerun postprocessing and sync results.")

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
            sel_sub = _persisted_choice(
                "Width",
                list(sub_jobs.keys()),
                "results_full_flc_width",
            )
            job_dir = sub_jobs[sel_sub]

            pngs = sorted(f for f in os.listdir(job_dir) if f.endswith(".png"))
            if pngs:
                img_cols = st.columns(min(len(pngs), 3))
                for i, png in enumerate(pngs):
                    img_cols[i % 3].image(os.path.join(job_dir, png), use_container_width=True)

            _display_job_videos(job_dir)

            tab_fd2, tab_sp2, tab_vh2, tab_en2, tab_fl2, tab_diag2 = st.tabs(
                ["Force-Disp.", "Strain Path", "V&H Rate", "Energy", "Forming Limits", "Diagnostics"]
            )

            with tab_fd2:
                fig_fd2 = _fd_with_fracture_fig(job_dir)
                if fig_fd2 is not None:
                    _plotly_chart(fig_fd2, use_container_width=True, key=f"fd2_{sel_sub}")
                else:
                    st.info("Force–displacement data unavailable")

            with tab_sp2:
                fig, reason = _strain_cluster_fig(job_dir)
                if fig is not None:
                    _plotly_chart(fig, use_container_width=True, key=f"strain_path_cluster2_{sel_sub}")
                else:
                    st.info(reason or "top-5 cluster strain path unavailable")
                fig_extras2 = _strain_path_extras_fig(job_dir)
                if fig_extras2 is not None:
                    _plotly_chart(fig_extras2, use_container_width=True, key=f"sp_extras2_{sel_sub}")

            with tab_vh2:
                smoothing_window2 = st.number_input(
                    "Fit smoothing",
                    min_value=1,
                    max_value=101,
                    value=20,
                    step=2,
                    key=f"vh_fit_smoothing2_{sel_sub}",
                )
                fig, reason = _volk_hora_rate_fig(
                    job_dir,
                    smoothing_window=int(smoothing_window2),
                )
                if fig is not None:
                    _plotly_chart(fig, use_container_width=True, key=f"vh_rate2_{sel_sub}")
                else:
                    st.info(reason or "Volk-Hora rate data unavailable")

            with tab_en2:
                fig_en2 = _energy_fig_v2(job_dir)
                if fig_en2 is not None:
                    _plotly_chart(fig_en2, use_container_width=True, key=f"energy2_{sel_sub}")
                else:
                    st.info("Energy data unavailable")

            with tab_fl2:
                fp = os.path.join(job_dir, "forming_limits.csv")
                if os.path.exists(fp):
                    df = _load_csv(fp)
                    st.dataframe(df, use_container_width=True, hide_index=True)

            with tab_diag2:
                _diagnostics_render(job_dir, key_prefix=f"diag2_{sel_sub}")

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
            m = re.match(r'(?:FLC_)?(\w+?)_t([\dp]+)_ang(\d+)(.*)', dirname)
            if m:
                test      = m.group(1).capitalize()
                thickness = m.group(2).replace('p', '.')
                angle     = m.group(3)
                suffix    = m.group(4).lstrip('_')
                label = f"{test}  t = {thickness} mm"
                if angle != '0':
                    label += f"  {angle}°"
                if suffix:
                    label += f"  ({suffix})"
                return label
            return dirname

        def _job_variant_in_dir(name):
            m = re.search(r'_ang\d+_(.*)', name)
            return m.group(1) if m else ''

        def _fracture_points(flc_dir, variant=None):
            pts = []
            try:
                for entry in sorted(os.scandir(flc_dir), key=lambda e: e.name):
                    if not entry.is_dir():
                        continue
                    if variant is not None and _job_variant_in_dir(entry.name) != variant:
                        continue
                    fp = os.path.join(entry.path, 'forming_limits.csv')
                    if not os.path.exists(fp):
                        continue
                    df_lim = _load_csv(fp)
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
            for fname, c1, c2 in [('strain_path.csv', 'eps1_major', 'eps2_minor'),
                                   ('elout.csv',       'eps1_le',    'eps2_le')]:
                fp = os.path.join(job_dir, fname)
                if not os.path.exists(fp):
                    continue
                df_sp = _load_csv(fp)
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

        # Build flc_options: expand dirs that contain multiple variants into one
        # entry per variant so each comparison curve is always a clean single setup.
        # Value is (path, variant_filter) — variant_filter=None means no filtering.
        flc_options = {}
        for _k, _v in flc_dirs.items():
            if not _has_csv_data(_v):
                continue
            _base = _parse_label(_k)
            try:
                _subdirs = [e.name for e in os.scandir(_v)
                            if e.is_dir() and os.path.exists(
                                os.path.join(e.path, 'forming_limits.csv'))]
            except PermissionError:
                _subdirs = []
            _variants = sorted(set(_job_variant_in_dir(n) for n in _subdirs))
            if len(_variants) > 1:
                for _var in _variants:
                    _lbl = f"{_base}  ({_var})" if _var else _base
                    flc_options[_lbl] = (_v, _var)
            elif _variants and _variants[0]:
                flc_options[f"{_base}  ({_variants[0]})"] = (_v, _variants[0])
            else:
                flc_options[_base] = (_v, None)

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

            _flc_path, _flc_var = flc_options[label]
            pts = _fracture_points(_flc_path, variant=_flc_var)
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

        _plotly_chart(fig, use_container_width=True)

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

    # ══════════════════════════════════════════════════════════════════════════
    # Sensitivity view
    # ══════════════════════════════════════════════════════════════════════════
    elif view_mode == "Sensitivity":

        st.markdown(
            "Convergence study: ε₁ vs mesh-refinement factor and mass-scaling dt."
        )

        # ── Pick study directory ──────────────────────────────────────────────
        study_dirs = sorted([
            d for d in os.listdir(results_dir)
            if os.path.isdir(os.path.join(results_dir, d)) and "study" in d.lower()
        ])
        if not study_dirs:
            st.info("No study directory found in results folder (expected a folder with 'study' in the name).")
            st.stop()
        study_name = st.selectbox("Study directory", study_dirs)
        study_path = os.path.join(results_dir, study_name)

        # Scan only jobs inside the selected study directory
        _, study_job_dirs = _scan(study_path)
        # _scan returns relpaths from study_path; re-key to bare job name
        study_job_dirs = {os.path.basename(k): v for k, v in study_job_dirs.items()}

        if not study_job_dirs:
            st.info("No post-processed jobs found in this study directory.")
            st.stop()

        # ── Parse job name into (width, mr_factor, ms_dt, ps) ────────────────
        def _parse_sensitivity_params(name):
            w  = _width_from_job(name)
            mr = re.search(r'_mr([\dp]+)', name)
            ms = re.search(r'_ms(\d+)e(\d+)', name)
            ps = re.search(r'_ps([\dp]+)', name)
            mr_val = float(mr.group(1).replace('p', '.')) if mr else 1.0
            ms_val = (float(ms.group(1)) * 10 ** (-int(ms.group(2)))) if ms else 1e-5
            ps_val = float(ps.group(1).replace('p', '.')) if ps else 5.0
            return {"width": w, "mr": mr_val, "ms": ms_val, "ps": ps_val}

        # ── Fetch actual CPU runtimes from SLURM sacct ───────────────────────
        sacct_key = f"sacct_runtimes_{study_name}"
        c_fetch, c_clear = st.columns([1, 4])
        with c_fetch:
            fetch_rt = st.button("Fetch runtimes from Euler", key="fetch_runtimes")
        with c_clear:
            if st.button("Clear cached runtimes", key="clear_runtimes"):
                st.session_state.pop(sacct_key, None)

        if fetch_rt:
            with st.spinner("Querying sacct on Euler…"):
                try:
                    cmd = (
                        f"ssh {EULER_USER}@{EULER_HOST} "
                        f"\"sacct --format=JobName%100,Elapsed,State --noheader "
                        f"--parsable2 -S 2026-01-01 -u {EULER_USER} "
                        f"| grep -v '\\.batch' | grep -v '\\.extern'\""
                    )
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                    runtimes = {}
                    for line in result.stdout.splitlines():
                        parts = line.strip().split("|")
                        if len(parts) < 3:
                            continue
                        jname_raw, elapsed, state = parts[0].strip(), parts[1].strip(), parts[2].strip()
                        if jname_raw in study_job_dirs and elapsed:
                            # Keep the entry for the COMPLETED run (prefer COMPLETED over FAILED)
                            if jname_raw not in runtimes or state == "COMPLETED":
                                runtimes[jname_raw] = elapsed
                    st.session_state[sacct_key] = runtimes
                    st.success(f"Fetched runtimes for {len(runtimes)} jobs.")
                except Exception as exc:
                    st.error(f"sacct query failed: {exc}")

        job_runtimes = st.session_state.get(sacct_key, {})  # jname → "HH:MM:SS"

        # ── Load thinning curves for all study jobs ───────────────────────────
        import numpy as np

        job_curves = {}   # jname → DataFrame(U3_mm, thinning)
        job_meta   = {}   # jname → {mr, ms, is_partial}

        for jname, jdir in study_job_dirs.items():
            p = _parse_sensitivity_params(jname)
            sp_fp = os.path.join(jdir, "strain_path.csv")
            fd_fp = os.path.join(jdir, "punch_fd.csv")
            if not os.path.exists(sp_fp) or not os.path.exists(fd_fp):
                continue
            try:
                spdf = _load_csv(sp_fp)
                fddf = _load_csv(fd_fp)
            except Exception:
                continue
            if not {"time_s", "eps1_major", "eps2_minor"}.issubset(spdf.columns):
                continue
            if not {"total_time_s", "U3_mm"}.issubset(fddf.columns):
                continue
            fddf = fddf.sort_values("total_time_s")
            spdf = spdf.sort_values("time_s")
            # Interpolate U3 at each strain_path time
            u3_vals = np.interp(
                spdf["time_s"].values,
                fddf["total_time_s"].values,
                fddf["U3_mm"].values,
            )
            thinning = spdf["eps1_major"].values + spdf["eps2_minor"].values
            curve = pd.DataFrame({"U3_mm": u3_vals, "thinning": thinning})
            # Partial = no fracture row in forming_limits.csv
            is_partial = True
            fl_fp = os.path.join(jdir, "forming_limits.csv")
            if os.path.exists(fl_fp):
                try:
                    dfl = _load_csv(fl_fp)
                    if not dfl[dfl["method"] == "fracture"].empty:
                        is_partial = False
                except Exception:
                    pass
            # Load ALLKE/ALLIE ratio vs U3 from energy_data.csv
            ke_curve = None
            en_fp = os.path.join(jdir, "energy_data.csv")
            if os.path.exists(en_fp):
                try:
                    endf = _load_csv(en_fp)
                    if {"total_time_s", "ALLKE", "ALLIE"}.issubset(endf.columns):
                        endf = endf.sort_values("total_time_s")
                        u3_en = np.interp(
                            endf["total_time_s"].values,
                            fddf["total_time_s"].values,
                            fddf["U3_mm"].values,
                        )
                        denom = np.where(endf["ALLIE"].values > 1e-12,
                                         endf["ALLIE"].values, np.nan)
                        ratio = endf["ALLKE"].values / denom * 100.0  # percent
                        ke_curve = pd.DataFrame({"U3_mm": u3_en, "ke_ratio_pct": ratio})
                except Exception:
                    pass

            job_curves[jname] = curve
            job_meta[jname]   = {"mr": p["mr"], "ms": p["ms"],
                                  "is_partial": is_partial, "ke_curve": ke_curve}

        if not job_curves:
            st.info("No post-processed jobs found in this study directory.")
        else:
            # Summary table
            summary_rows = []
            for jname, meta in job_meta.items():
                summary_rows.append({
                    "job": jname,
                    "mr_factor": meta["mr"],
                    "ms_dt": f"{meta['ms']:.0e}",
                    "status": "partial ○" if meta["is_partial"] else "complete",
                    "max_U3_mm": round(float(job_curves[jname]["U3_mm"].max()), 2),
                    "thinning_at_end": round(float(job_curves[jname]["thinning"].iloc[-1]), 4),
                })
            st.dataframe(
                pd.DataFrame(summary_rows).sort_values(["mr_factor", "ms_dt"]),
                use_container_width=True, hide_index=True,
            )
            st.caption("○ = job did not reach fracture (solver hit wall time)")

            all_ms = sorted({m["ms"] for m in job_meta.values()})
            all_mr = sorted({m["mr"] for m in job_meta.values()})
            colors = px.colors.qualitative.Plotly

            def _thinning_curve_fig(fixed_param, fixed_val, vary_param, vary_vals, title):
                """Thinning strain vs U3 — one curve per vary_val, fixed_val held constant."""
                fig = go.Figure()
                for i, vv in enumerate(vary_vals):
                    color = colors[i % len(colors)]
                    for jname, meta in job_meta.items():
                        if meta[fixed_param] != fixed_val or meta[vary_param] != vv:
                            continue
                        curve = job_curves[jname]
                        if vary_param == "ms":
                            label = f"dt={meta['ms']:.0e}"
                        else:
                            label = f"mr={int(meta['mr'])}"
                        is_partial = meta["is_partial"]
                        fig.add_trace(go.Scatter(
                            x=curve["U3_mm"], y=curve["thinning"],
                            mode="lines", name=label if not is_partial else f"{label} ○",
                            line=dict(color=color, dash="dot" if is_partial else "solid"),
                        ))
                        # Mark the last point with an open circle for partial runs
                        if is_partial:
                            fig.add_trace(go.Scatter(
                                x=[curve["U3_mm"].iloc[-1]],
                                y=[curve["thinning"].iloc[-1]],
                                mode="markers",
                                marker=dict(color=color, size=10, symbol="circle-open",
                                            line=dict(width=2, color=color)),
                                showlegend=False,
                            ))
                fig.update_layout(
                    xaxis_title="Punch displacement U3 [mm]",
                    yaxis_title="Thinning strain ε₁ + ε₂",
                    title=title, template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                )
                return fig

            # ── Controls (shared across all three plots) ──────────────────────
            st.markdown("---")
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                ms_opts = [f"{v:.0e}" for v in all_ms]
                sel_ms_str = st.selectbox("Fixed ms_dt (mesh plot)",
                                          ms_opts,
                                          index=len(ms_opts) - 2 if len(ms_opts) >= 2 else 0,
                                          key="sens_ms_fix")
                sel_ms = float(sel_ms_str)
            with cc2:
                mr_opts = [str(int(v)) for v in all_mr]
                sel_mr_str = st.selectbox("Fixed mr (mass-scaling plot)",
                                          mr_opts, index=0, key="sens_mr_fix")
                sel_mr = float(sel_mr_str)
            with cc3:
                tol_pct = st.number_input("Thinning convergence tolerance [%]",
                                          min_value=0.5, max_value=20.0,
                                          value=2.0, step=0.5, key="sens_tol")
            cc4, _ = st.columns([1, 2])
            with cc4:
                ke_tol_pct = st.number_input("Quasi-static KE/IE limit [%]",
                                             min_value=1.0, max_value=20.0,
                                             value=5.0, step=1.0, key="sens_ke_tol")

            # ── Mesh convergence: fix ms_dt, vary mr ─────────────────────────
            if len(all_mr) > 1:
                st.markdown(f"#### Thinning vs U3 — mesh refinement  (dt = {sel_ms_str})")
                _plotly_chart(_thinning_curve_fig(
                    "ms", sel_ms, "mr", all_mr,
                    f"Mesh convergence (dt = {sel_ms_str})",
                ), use_container_width=True)

            # ── Mass-scaling sensitivity: fix mr, vary ms_dt ─────────────────
            if len(all_ms) > 1:
                st.markdown(f"#### Thinning vs U3 — mass-scaling  (mr = {sel_mr_str})")
                _plotly_chart(_thinning_curve_fig(
                    "mr", sel_mr, "ms", all_ms,
                    f"Mass-scaling sensitivity (mr = {sel_mr_str})",
                ), use_container_width=True)

            # ── Quasi-staticity: ALLKE/ALLIE vs U3, one line per ms_dt ───────
            ke_available = any(m["ke_curve"] is not None for m in job_meta.values())
            if ke_available and len(all_ms) > 1:
                st.markdown(f"#### Quasi-staticity ALLKE/ALLIE vs U3  (mr = {sel_mr_str})")
                fig_ke = go.Figure()
                colors = px.colors.qualitative.Plotly
                for i, ms_val in enumerate(all_ms):
                    jn = next((k for k, m in job_meta.items()
                                if m["mr"] == sel_mr and m["ms"] == ms_val), None)
                    if jn is None:
                        continue
                    kc = job_meta[jn]["ke_curve"]
                    if kc is None:
                        continue
                    color = colors[i % len(colors)]
                    is_partial = job_meta[jn]["is_partial"]
                    label = f"dt={ms_val:.0e}" + (" ○" if is_partial else "")
                    fig_ke.add_trace(go.Scatter(
                        x=kc["U3_mm"], y=kc["ke_ratio_pct"],
                        mode="lines", name=label,
                        line=dict(color=color, dash="dot" if is_partial else "solid"),
                    ))
                # ISO / Abaqus recommended limit line
                fig_ke.add_trace(go.Scatter(
                    x=[0, max(job_curves[jn]["U3_mm"].max() for jn in job_curves)],
                    y=[ke_tol_pct, ke_tol_pct],
                    mode="lines", name=f"{ke_tol_pct:.0f}% limit",
                    line=dict(color="black", dash="dash", width=1),
                ))
                fig_ke.update_layout(
                    xaxis_title="Punch displacement U3 [mm]",
                    yaxis_title="ALLKE / ALLIE [%]",
                    title=f"Quasi-staticity check (mr = {sel_mr_str})",
                    template="plotly_white",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                )
                _plotly_chart(fig_ke, use_container_width=True)

            # ── Convergence map: thinning deviation + quasi-staticity ─────────
            st.markdown("#### Convergence map")

            # Reference: finest available complete job in job_curves.
            # Pick by sorting complete jobs by (mr asc, ms asc) and taking the first.
            complete_in_curves = {
                jn: m for jn, m in job_meta.items()
                if not m["is_partial"] and jn in job_curves
            }
            if not complete_in_curves:
                st.info("No complete jobs with data available yet.")
            else:
                ref_key = min(complete_in_curves,
                              key=lambda jn: (job_meta[jn]["mr"], job_meta[jn]["ms"]))
                ref_mr  = job_meta[ref_key]["mr"]
                ref_ms  = job_meta[ref_key]["ms"]
                ref_curve = job_curves[ref_key]

                # Comparison range: U3 reached by the reference job.
                # Partial jobs are compared only over the range they completed.
                u3_max_ref = float(ref_curve["U3_mm"].max())
                u3_grid    = np.linspace(0, u3_max_ref, 200)
                ref_thinning = np.interp(u3_grid,
                                         ref_curve["U3_mm"].values,
                                         ref_curve["thinning"].values)

                ms_labels = [f"{v:.0e}" for v in all_ms]
                mr_labels = [f"mr={int(v)}" for v in all_mr]
                table_rows = {ml: [] for ml in mr_labels}

                for mr_val, mr_label in zip(all_mr, mr_labels):
                    for ms_val in all_ms:
                        jn = next((k for k, m in job_meta.items()
                                   if m["mr"] == mr_val and m["ms"] == ms_val), None)

                        if jn is None or jn not in job_curves:
                            table_rows[mr_label].append("—")
                            continue

                        c          = job_curves[jn]
                        is_partial = job_meta[jn]["is_partial"]
                        partial_flag = " ○" if is_partial else ""

                        # Thinning deviation
                        u3_max_j = min(float(c["U3_mm"].max()), u3_max_ref)
                        mask = u3_grid <= u3_max_j
                        if mask.sum() >= 2:
                            j_th  = np.interp(u3_grid[mask], c["U3_mm"].values, c["thinning"].values)
                            ref_t = ref_thinning[mask]
                            denom = np.where(np.abs(ref_t) > 1e-6, ref_t, np.nan)
                            thin_err = float(np.nanmax(np.abs((j_th - ref_t) / denom)) * 100.0)
                        else:
                            thin_err = float("nan")

                        # Max KE ratio — skip first 5% of U3 where ALLIE ≈ 0
                        kc = job_meta[jn]["ke_curve"]
                        ke_max = float("nan")
                        if kc is not None and not kc.empty:
                            kc_f = kc[kc["U3_mm"] > 0.05 * u3_max_ref]
                            if not kc_f.empty:
                                ke_max = float(np.nanmax(kc_f["ke_ratio_pct"].values))

                        thin_str = f"Δthin {thin_err:.1f}%" if not math.isnan(thin_err) else "Δthin —"
                        ke_str   = f"KE {ke_max:.1f}%"      if not math.isnan(ke_max)   else "KE —"
                        rt_str   = job_runtimes.get(jn, "—")
                        table_rows[mr_label].append(f"{thin_str} | {ke_str} | {rt_str}{partial_flag}")

                df_map = pd.DataFrame(
                    {ms_labels[ci]: [table_rows[ml][ci] for ml in mr_labels]
                     for ci in range(len(ms_labels))},
                    index=mr_labels,
                )
                df_map.index.name = "mr \\ dt"
                st.dataframe(df_map, use_container_width=True)
                st.caption(
                    f"Δthin = max thinning deviation from reference "
                    f"(mr={int(ref_mr)}, dt={ref_ms:.0e}).  ○ = partial run."
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
