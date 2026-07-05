# -*- coding: utf-8 -*-
import base64
import collections
import io
import json
import math
import os
import re
import shlex
import subprocess
import time
import zipfile
os.environ.setdefault("MPLCONFIGDIR", os.path.join("/tmp", "abaqusproject-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit_autorefresh import st_autorefresh

import config as pipeline_config
import static_postproc_plots



# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Abaqus Pipeline",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Preserve scroll position across Streamlit reruns.
# Each rerun re-executes this script; the injected JS saves scroll to
# sessionStorage before the DOM is torn down and restores it after render.
st_components.html("""
<script>
(function () {
    const KEY = 'st_scroll_y';
    const win = window.parent;

    // Save scroll position on every scroll event
    win.addEventListener('scroll', function () {
        sessionStorage.setItem(KEY, win.scrollY);
    }, { passive: true });

    // Restore: try a few times to handle variable render times
    const y = parseInt(sessionStorage.getItem(KEY) || '0');
    if (y > 0) {
        [80, 200, 400].forEach(function (t) {
            setTimeout(function () { win.scrollTo(0, y); }, t);
        });
    }
})();
</script>
""", height=0)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
EULER_USER = str(getattr(pipeline_config, "EULER_USER", "acruzfaria"))
EULER_HOST = str(getattr(pipeline_config, "EULER_HOST", "euler.ethz.ch"))
EULER_DIR_TEMPLATE = str(
    getattr(pipeline_config, "EULER_DIR_TEMPLATE", "/cluster/home/{user}/AbaqusProject")
)
EULER_SCRATCH_ROOT_TEMPLATE = str(
    getattr(pipeline_config, "EULER_SCRATCH_ROOT_TEMPLATE", "/cluster/scratch/{user}")
)

SSH_AUTH_NORMAL = "normal"
SSH_AUTH_KEY_ONLY = "key_only"
SSH_AUTH_LABELS = {
    SSH_AUTH_NORMAL: "Normal login via Terminal",
    SSH_AUTH_KEY_ONLY: "SSH key only",
}

WIDTH_OPTIONS = [20, 50, 80, 90, 100, 120, 200]
MS_OPTIONS = [1e-3, 1e-4, 5e-5, 1e-5, 5e-6, 1e-6, 1e-7]
PIP_OPTIONS   = ["PUNCH_2", "PUNCH_21", "PUNCH_23", "PUNCH_24", "PUNCH_25"]
VH_ALPHA = 0.55
VH_FRACTURE_RADIUS_MM = max(0.0, float(os.environ.get("POSTPROC_VH_FRACTURE_RADIUS_MM", "3.0")))
VH_SEED_COUNT = max(1, int(os.environ.get("POSTPROC_VH_SEED_COUNT", "50")))
VH_SEED_LABEL = "Top-%d" % VH_SEED_COUNT
VH_EVAL_BACK_FRAMES = max(0, int(os.environ.get("POSTPROC_VH_EVAL_BACK_FRAMES", "2")))
VH_FIT_WINDOW_SECONDS = max(0.0, float(os.environ.get("POSTPROC_VH_FIT_WINDOW_SECONDS", "2.0")))
VH_UNSTABLE_TAIL_POINTS = max(0, int(os.environ.get("POSTPROC_VH_UNSTABLE_TAIL_POINTS", "4")))
VH_UNSTABLE_FIT_WINDOW_SECONDS = max(0.0, float(os.environ.get("POSTPROC_VH_UNSTABLE_FIT_WINDOW_SECONDS", "0.6")))
VH_FIT_WINDOW_FRAC = max(0.1, min(1.0, float(os.environ.get("POSTPROC_VH_FIT_WINDOW_FRAC", "0.4"))))
VH_MIN_STABLE_POINTS = max(2, int(os.environ.get("POSTPROC_VH_MIN_STABLE_POINTS", "20")))
VH_MIN_UNSTABLE_POINTS = max(2, int(os.environ.get("POSTPROC_VH_MIN_UNSTABLE_POINTS", "4")))
CLUSTER_PATH_DISPLAY_MAX = max(1, int(os.environ.get("STREAMLIT_CLUSTER_PATH_DISPLAY_MAX", "40")))
USER_DEFAULTS_PATH = os.path.join(PROJECT_DIR, "streamlit_job_defaults.json")


def _format_remote_template(template, user):
    try:
        return str(template).format(user=user)
    except (KeyError, IndexError, ValueError):
        return str(template)


def _remote_project_root(user=None):
    user = user or EULER_USER
    return _format_remote_template(EULER_DIR_TEMPLATE, user)


def _remote_scratch_root(user=None):
    user = user or EULER_USER
    return _format_remote_template(EULER_SCRATCH_ROOT_TEMPLATE, user)


def _vh_eval_index(n_points):
    if n_points <= 1:
        return 0
    return max(1, min(n_points - 1, n_points - 1 - VH_EVAL_BACK_FRAMES))


def _plot_theme():
    base_opt = str(st.get_option("theme.base") or "").strip().lower()
    if base_opt not in ("dark", "light"):
        cfg_path = os.path.join(PROJECT_DIR, ".streamlit", "config.toml")
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg_text = f.read()
            m = re.search(r'^\s*base\s*=\s*["\']?(dark|light)["\']?', cfg_text, re.M | re.I)
            if m:
                base_opt = m.group(1).lower()
        except OSError:
            pass
    primary = st.get_option("theme.primaryColor") or "#2563eb"
    text_opt = st.get_option("theme.textColor")
    bg_opt = st.get_option("theme.backgroundColor")
    paper_opt = st.get_option("theme.secondaryBackgroundColor")

    def _hex_luma(hex_color):
        if not isinstance(hex_color, str):
            return None
        s = hex_color.strip().lstrip("#")
        if len(s) != 6:
            return None
        try:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
        except ValueError:
            return None
        return 0.299 * r + 0.587 * g + 0.114 * b

    text_luma = _hex_luma(text_opt)
    bg_luma = _hex_luma(bg_opt)
    if base_opt in ("dark", "light"):
        base = base_opt
    elif text_luma is not None:
        base = "dark" if text_luma > 160 else "light"
    elif bg_luma is not None:
        base = "dark" if bg_luma < 128 else "light"
    else:
        base = "dark"

    text = text_opt or ("#f3f4f6" if base == "dark" else "#111827")
    bg = bg_opt or ("#000000" if base == "dark" else "#ffffff")
    paper = paper_opt or ("#1f2937" if base == "dark" else "#f8fafc")
    template = "plotly_dark" if base == "dark" else "plotly_white"
    accent = "#f59e0b" if base == "dark" else "#f97316"
    return {
        "base": base,
        "template": template,
        "primary": primary,
        "accent": accent,
        "text": text,
        "bg": bg,
        "paper": paper,
    }


def _streamlit_plot_style(theme=None):
    theme = theme or _plot_theme()
    axis_color = "#ffffff" if theme["base"] == "dark" else "#000000"
    grid_color = "rgba(255,255,255,0.14)" if theme["base"] == "dark" else "rgba(0,0,0,0.10)"
    guide_color = "rgba(255,255,255,0.42)" if theme["base"] == "dark" else "rgba(0,0,0,0.42)"
    annotation_bg = "rgba(17,24,39,0.74)" if theme["base"] == "dark" else "rgba(255,255,255,0.74)"
    hover_bg = "#111827" if theme["base"] == "dark" else "#ffffff"
    return {
        "axis": axis_color,
        "grid": grid_color,
        "guide": guide_color,
        "annotation_bg": annotation_bg,
        "hover_bg": hover_bg,
        "transparent": "rgba(0,0,0,0)",
    }


def _bm_mesh_zone_diagram_html():
    return """
    <div style="width:100%;overflow:visible;">
      <svg viewBox="0 0 980 640" role="img" aria-label="BM mesh zone diagram"
           style="width:100%;height:auto;display:block;border:1px solid rgba(125,125,125,.24);border-radius:6px;background:#f8fafc;">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#475569"/>
          </marker>
          <style>
            .title{font:700 18px system-ui,-apple-system,Segoe UI,sans-serif;fill:#111827}
            .label{font:600 13px system-ui,-apple-system,Segoe UI,sans-serif;fill:#111827}
            .small{font:500 11px system-ui,-apple-system,Segoe UI,sans-serif;fill:#334155}
            .axis{stroke:#475569;stroke-width:1.4;marker-end:url(#arrow)}
            .line{stroke:#334155;stroke-width:1.2;fill:none}
            .dash{stroke:#334155;stroke-width:1.1;stroke-dasharray:5 4;fill:none}
            .dashdot{stroke:#334155;stroke-width:1.1;stroke-dasharray:7 3 2 3;fill:none}
            .dim{stroke:#64748b;stroke-width:1;marker-end:url(#arrow)}
          </style>
        </defs>

        <!-- ── Titles ── -->
        <text class="title" x="52"  y="32">W20-W120 BM mesh zones</text>
        <text class="title" x="530" y="32">W200 BM mesh zones</text>

        <!-- ── W20-W120 ── shifted right to leave left margin for outside seeding labels -->
        <g transform="translate(115,430)">
          <!-- Zone fills -->
          <rect x="0"  y="-324" width="232" height="324" fill="#fecaca" opacity=".95"/>
          <path d="M0 -302 A302 302 0 0 1 232 -193 L232 -58 H0 Z" fill="#fde68a" opacity=".95"/>
          <path d="M0 -302 A302 302 0 0 1 232 -193 L232 -138 A270 270 0 0 0 0 -270 Z" fill="#fdba74" opacity=".95"/>
          <rect x="0"  y="-58"  width="232" height="35"  fill="#86efac" opacity=".95"/>
          <rect x="46" y="-23"  width="186" height="23"  fill="#bae6fd" opacity=".95"/>
          <rect x="0"  y="-23"  width="46"  height="23"  fill="#93c5fd" opacity=".9"/>
          <!-- Specimen outline -->
          <path d="M0 0 H232 V-324 H0 Z" class="line"/>
          <!-- Horizontal partitions -->
          <path d="M0 -23 H232" class="dash"/>
          <path d="M0 -58 H232" class="dash"/>
          <!-- P_inner_x vertical (x=46) -->
          <path d="M46 0 V-58" class="line"/>
          <!-- P_inner_r arc: centre(603,-58), r=557; start(46,-58), top exit(115,-324) -->
          <path d="M46 -58 A557 557 0 0 1 115 -324" class="line"/>
          <!-- P_circle_r: centre(0,0), r=302; (0,-302)→(232,-193) -->
          <path d="M0 -302 A302 302 0 0 1 232 -193" class="line"/>
          <!-- Extra W20/W50-only S3_1 split at the flat-cutout intersection radius -->
          <path d="M0 -270 A270 270 0 0 1 232 -138" class="dashdot"/>
          <!-- Zone labels centered in rectangular zones -->
          <text class="label" text-anchor="middle" x="23"  y="-11">S1</text>
          <text class="label" text-anchor="middle" x="139" y="-11">S2</text>
          <text class="label" text-anchor="middle" x="116" y="-40">S2</text>
          <text class="label" x="14"  y="-180">S3</text>
          <text class="label" text-anchor="middle" x="116" y="-311">S4</text>

          <!-- Y-seeding labels outside left — arrows point into diagram -->
          <line x1="-10" y1="-11"  x2="0" y2="-11"  class="dim"/>
          <text class="small" text-anchor="end" x="-13" y="-7" >S1 y</text>
          <line x1="-10" y1="-40"  x2="0" y2="-40"  class="dim"/>
          <text class="small" text-anchor="end" x="-13" y="-36">S2 y</text>
          <line x1="-10" y1="-180" x2="0" y2="-180" class="dim"/>
          <text class="small" text-anchor="end" x="-13" y="-176">S3 y</text>
          <line x1="-10" y1="-280" x2="0" y2="-280" class="dim"/>
          <text class="small" text-anchor="end" x="-13" y="-276">S3_1 y (W20/W50)</text>
          <line x1="-10" y1="-313" x2="0" y2="-313" class="dim"/>
          <text class="small" text-anchor="end" x="-13" y="-309">S4 y</text>
          <!-- X-seeding labels outside below x-axis -->
          <text class="small" text-anchor="middle" x="23"  y="40">S1 x</text>
          <text class="small" text-anchor="middle" x="139" y="40">S2 x</text>
          <!-- Geometric partition labels -->
          <line x1="0" y1="10" x2="46" y2="10" class="dim"/>
          <line x1="0" y1="4"  x2="0"  y2="14" stroke="#64748b" stroke-width="1" fill="none"/>
          <text class="small" x="2"   y="26">P_inner_x</text>
          <text class="small" x="236" y="-20">← P_XZplane_1</text>
          <text class="small" x="236" y="-55">← 12.5 mm</text>
          <text class="small" x="236" y="-190">← P_circle_r</text>
          <text class="small" x="236" y="-138">← S3_1 split</text>
          <text class="small" x="246" y="-122">W20/W50 only</text>
          <text class="small" x="70"  y="-198">P_inner_r</text>
          <!-- Axes -->
          <line x1="0" y1="0" x2="258" y2="0" class="axis"/>
          <line x1="0" y1="0" x2="0"   y2="-344" class="axis"/>
          <text class="small" x="263" y="5">x</text>
          <text class="small" x="-10" y="-354">y</text>
        </g>

        <!-- ── W200 ── same scale 4.63 px/mm; origin at specimen corner, x right, y up
             r: outer=324(70mm), S3/S4 boundary=231(50mm=P_section3_r),
                S2/S3 boundary=93(20mm=P_section2_r), S1 square side=46(10mm=P_section1_y)
             diagonal: (46,-46)→(229,-229) = (P_s1_y,P_s1_y)→(70/√2,70/√2) mm -->
        <g transform="translate(530,430)">
          <!-- Zone fills: painters back→front -->
          <path d="M0 0 L0 -324 A324 324 0 0 1 324 0 Z" fill="#fecaca" opacity=".95"/>
          <path d="M0 0 L0 -231 A231 231 0 0 1 231 0 Z" fill="#fde68a" opacity=".95"/>
          <path d="M0 0 L0 -93  A93  93  0 0 1  93 0 Z" fill="#86efac" opacity=".95"/>
          <rect x="0" y="-46" width="46" height="46" fill="#93c5fd" opacity=".9"/>
          <!-- Outer arc (specimen boundary) -->
          <path d="M0 0 L0 -324 A324 324 0 0 1 324 0 Z" class="line"/>
          <!-- P_section3_r = 50 mm = 231 px -->
          <path d="M0 -231 A231 231 0 0 1 231 0" class="dash"/>
          <!-- P_section2_r = 20 mm = 93 px -->
          <path d="M0 -93 A93 93 0 0 1 93 0" class="dash"/>
          <!-- P_section1_y square sides: x=46 (y=0→-46) and y=-46 (x=0→46) -->
          <path d="M46 0 V-46 H0" class="line"/>
          <!-- 45° diagonal partition: (46,-46)→(229,-229) -->
          <path d="M46 -46 L229 -229" class="dash"/>
          <!-- Zone labels centered in each region -->
          <text class="label" text-anchor="middle" x="23"  y="-23">S1</text>
          <text class="label" x="52"  y="-52">S2</text>
          <text class="label" x="108" y="-114">S3</text>
          <text class="label" x="191" y="-197">S4</text>
          <!-- Partition ticks on x-axis, labels staggered below -->
          <line x1="46"  y1="0" x2="46"  y2="8" stroke="#64748b" stroke-width="1"/>
          <text class="small" x="28"  y="20">P_section1_y</text>
          <line x1="93"  y1="0" x2="93"  y2="8" stroke="#64748b" stroke-width="1"/>
          <text class="small" x="75"  y="33">P_section2_r</text>
          <line x1="231" y1="0" x2="231" y2="8" stroke="#64748b" stroke-width="1"/>
          <text class="small" x="213" y="46">P_section3_r</text>
          <!-- Axes -->
          <line x1="0" y1="0" x2="344" y2="0" class="axis"/>
          <line x1="0" y1="0" x2="0"   y2="-344" class="axis"/>
          <text class="small" x="349" y="5">x</text>
          <text class="small" x="-10" y="-354">y</text>
        </g>

        <!-- ── Legend (below both diagrams) ── -->
        <g transform="translate(28,500)">
          <text class="title" x="0" y="0">Control mapping</text>
          <rect x="0"   y="15" width="14" height="14" fill="#93c5fd"/>
          <text class="small" x="20"  y="27">S1: finest center zone</text>
          <rect x="190" y="15" width="14" height="14" fill="#86efac"/>
          <text class="small" x="210" y="27">S2: transition zone</text>
          <rect x="380" y="15" width="14" height="14" fill="#fde68a"/>
          <text class="small" x="400" y="27">S3: outer transition</text>
          <rect x="570" y="15" width="14" height="14" fill="#fdba74"/>
          <text class="small" x="590" y="27">S3_1: W20/W50 extra band</text>
          <rect x="775" y="15" width="14" height="14" fill="#fecaca"/>
          <text class="small" x="795" y="27">S4: outer coarse band</text>
          <text class="small" x="0" y="58">W200: P_section1_y = square side (S1); P_section2_r, P_section3_r = circle radii from origin; diagonal from (P_s1_y, P_s1_y) to (70/√2, 70/√2).</text>
        </g>
      </svg>
    </div>
    """

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
# The old JS scroll-keeper was removed: fragments now stop full-page reruns,
# and its focus-triggered restore caused stale upward scroll jumps.


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


@st.cache_data(ttl=300)
def _scan(base):
    """Return (flc_dirs, job_dirs) as label→path dicts. Cached for 300 s.

    The cache is cleared explicitly after a sync or a manual rescan, so the
    long TTL only matters for files changed outside the app.
    """
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
    return flc, _dedupe_jobs_by_parameters(jobs)


def _job_mtime(path):
    best = 0.0
    for marker in _JOB_MARKERS:
        fp = os.path.join(path, marker)
        try:
            t = os.path.getmtime(fp)
            if t > best:
                best = t
        except OSError:
            pass
    if best == 0.0:
        try:
            best = os.path.getmtime(path)
        except OSError:
            pass
    return best


def _job_parameter_key(name_or_path):
    """Canonical job identity for deduplication; non-separator tokens are ignored."""
    text = os.path.basename(os.path.normpath(str(name_or_path)))
    text = text[4:] if text.startswith("FLC_") else text
    lower = text.lower()

    if "marc" in lower:
        test_type = "marciniak"
    elif "pip" in lower:
        test_type = "pip"
    elif "naka" in lower or "nakazima" in lower:
        test_type = "nakazima"
    else:
        test_type = lower.split("_")[0] if lower else "job"

    punch = ""
    punch_match = re.search(r"(?:^|_)(?:naka|marc)(\d+)", text, flags=re.I)
    if punch_match:
        punch = f"p{punch_match.group(1).lower()}"
    else:
        pip_match = re.search(r"(?:^|_)p(\d+)(?=_|$)", text, flags=re.I)
        if pip_match:
            punch = f"p{pip_match.group(1).lower()}"

    def _token(pattern, default=""):
        match = re.search(pattern, text, flags=re.I)
        return match.group(1).lower() if match else default

    width = _token(r"(?:^|_)W(\d+)(?=_|$)")
    thickness = _token(r"(?:^|_)t([\dp]+)(?=_|$)")
    angle = _token(r"(?:^|_)ang(\d+)(?=_|$)")
    mass_scaling = _token(r"(?:^|_)ms(\d+e\d+)(?=_|$)")
    mesh_refinement = _token(r"(?:^|_)mr([\dp]+)(?=_|$)", "1")
    nt = _token(r"(?:^|_)nt(\d+)(?=_|$)")
    punch_speed = _token(r"(?:^|_)ps([\dp]+)(?=_|$)", "5")

    return (
        test_type,
        punch,
        width,
        thickness,
        angle,
        mass_scaling,
        f"mr{mesh_refinement}" if mesh_refinement else "",
        f"nt{nt}" if nt else "",
        f"ps{punch_speed}",
    )


def _dedupe_jobs_by_parameters(jobs):
    """Keep the most recently written job when canonical parameters are identical."""
    latest = {}
    for label, path in jobs.items():
        key = _job_parameter_key(label or path)
        mtime = _job_mtime(path)
        existing = latest.get(key)
        if existing is None or (mtime, str(label)) > (existing[2], str(existing[0])):
            latest[key] = (label, path, mtime)
    return {
        label: path
        for label, path, _ in sorted(latest.values(), key=lambda item: str(item[0]))
    }


def _job_campaign_key(name_or_path):
    """Job identity for FLD campaigns: same setup, different specimen width."""
    test_type, punch, _width, thickness, angle, mass_scaling, mesh_refinement, nt, punch_speed = (
        _job_parameter_key(name_or_path)
    )
    return (
        test_type,
        punch,
        thickness,
        angle,
        mass_scaling,
        mesh_refinement,
        nt,
        punch_speed,
    )


@st.cache_data(show_spinner=False, max_entries=256)
def _load_csv_cached(path, mtime):
    return pd.read_csv(path)


def _load_csv(path):
    """Read a postproc CSV, cached by (path, mtime) so file changes invalidate."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    return _load_csv_cached(path, mtime)


_load_csv.clear = _load_csv_cached.clear


def _invalidate_results_caches():
    """Drop every Results-page cache after a sync or manual rescan."""
    _scan.clear()
    _load_csv.clear()
    st.session_state.pop("_results_fig_memo", None)
    st.session_state.pop("_flc_source_options_memo", None)
    st.session_state["results_scan_token"] = (
        st.session_state.get("results_scan_token", 0) + 1
    )


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


@st.fragment
def _display_job_videos(job_dir):
    """Movies live in their own fragment: toggling "Load movies" reruns only
    this block, so the surrounding plots and selectors never rebuild."""
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
    total_mb = sum(os.path.getsize(os.path.join(job_dir, f)) for f in webms) / (1024.0 * 1024.0)
    video_key = re.sub(r"[^A-Za-z0-9_]+", "_", os.path.abspath(job_dir))
    load_movies = st.checkbox(
        f"Load movies ({len(webms)} file{'s' if len(webms) != 1 else ''}, {total_mb:.1f} MB)",
        value=False,
        key=f"load_movies_{video_key}",
        help="Movies are intentionally lazy-loaded because embedding them makes Streamlit reruns slow.",
    )
    if not load_movies:
        return

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
                  punch_diameter, mesh_factor, thickness_seeds=None,
                  mass_scaling_dt=1e-5, pip_punch2_id=None,
                  punch_speed=5.0, punch_displacement=35.0,
                  bm_mesh_manual=False, bm_mesh_tag="",
                  punch_velocity_profile="smoothstep",
                  fr_punch=0.0):

    _t   = str(blank_thickness).replace(".", "p")
    _ang = str(int(angle))

    _pip = f"_p2{pip_punch2_id.replace('PUNCH_', '')}" if pip_punch2_id else ""

    _ms_exp  = int(math.floor(math.log10(mass_scaling_dt)))
    _ms_mant = int(round(mass_scaling_dt / 10 ** _ms_exp))
    _ms      = f"_ms{_ms_mant}e{abs(_ms_exp)}"

    _mr = ""
    if abs(mesh_factor - 1.0) > 1e-6:
        _mr = "_mr" + f"{mesh_factor:.4g}".replace(".", "p")

    _ts = ""
    if thickness_seeds is not None and int(thickness_seeds) != 10:
        _ts = f"_nt{int(thickness_seeds)}"

    _ps = ""
    if test_type != "pip" and abs(punch_speed - 5.0) > 1e-6:
        _ps = "_ps" + f"{punch_speed:.4g}".replace(".", "p")

    _pd = ""
    if test_type != "pip" and abs(punch_displacement - 35.0) > 1e-6:
        _pd = "_pd" + f"{punch_displacement:.4g}".replace(".", "p")

    _bm = ""
    if bm_mesh_manual:
        safe_tag = re.sub(r"[^A-Za-z0-9]+", "", str(bm_mesh_tag or ""))[:24]
        _bm = "_bm" + (safe_tag or "man")

    _vp = "_vconst" if str(punch_velocity_profile).lower() == "constant" else ""

    _fr = ""
    if abs(fr_punch) > 1e-9:
        _fr = "_fr" + f"{fr_punch:.4g}".replace(".", "p")

    if test_type == "nakazima":
        prefix = f"Naka{int(round(punch_diameter))}"
    elif test_type == "marciniak":
        prefix = f"Marc{int(round(punch_diameter))}"
    else:
        prefix = "Pip"

    return f"{prefix}_W{specimen_width}_t{_t}_ang{_ang}{_pip}{_ms}{_mr}{_ts}{_ps}{_pd}{_bm}{_vp}{_fr}"


def make_study_root_name(test_type, blank_thickness, angle, punch_diameter,
                         mesh_factor, thickness_seeds=None,
                         mass_scaling_dt=1e-5, pip_punch2_id=None,
                         punch_speed=5.0, punch_displacement=35.0,
                         bm_mesh_manual=False, bm_mesh_tag="",
                         punch_velocity_profile="smoothstep",
                         fr_punch=0.0):
    job_name = make_job_name(
        test_type=test_type,
        specimen_width=0,
        blank_thickness=blank_thickness,
        angle=angle,
        punch_diameter=punch_diameter,
        mesh_factor=mesh_factor,
        thickness_seeds=thickness_seeds,
        mass_scaling_dt=mass_scaling_dt,
        pip_punch2_id=pip_punch2_id,
        punch_speed=punch_speed,
        punch_displacement=punch_displacement,
        bm_mesh_manual=bm_mesh_manual,
        bm_mesh_tag=bm_mesh_tag,
        punch_velocity_profile=punch_velocity_profile,
        fr_punch=fr_punch,
    )
    return "FLC_" + re.sub(r"_W\d+(?=_t)", "", job_name, count=1)


def build_env(cfg, include_width=True):
    euler_user = st.session_state.get("euler_user", EULER_USER)
    euler_host = st.session_state.get("euler_host", EULER_HOST)
    env = {
        **os.environ,
        "EULER_USER": euler_user,
        "EULER_HOST": euler_host,
        "EULER_DIR": _remote_project_root(euler_user),
        "EULER_SCRATCH_ROOT": _remote_scratch_root(euler_user),
        "SSH_AUTH_MODE": _current_ssh_auth_mode(),
        "SSH_CONTROL_PATH": _current_ssh_control_path(),
        "TEST_TYPE": cfg["test_type"],
        "BLANK_THICKNESS": str(cfg["thickness"]),
        "MATERIAL_ORIENTATION_ANGLE": str(cfg["angle"]),
        "MESH_BACKEND": "bm",
        "MESH_REFINEMENT_FACTOR": str(cfg["mesh_factor"]),
        "N_THICKNESS_SEEDS": str(cfg["thickness_seeds"]),
        "NUM_CPUS": str(cfg["num_cpus"]),
        "SLURM_CPUS_PER_TASK": str(cfg["num_cpus"]),
        "SLURM_MEM_PER_CPU_GB": f"{cfg['slurm_mem_per_cpu_gb']:.6g}",
        "SLURM_TIME_LIMIT": cfg["slurm_time_limit"],
        "ABAQUS_MEMORY_PERCENT": str(cfg["abaqus_memory_percent"]),
        "ENABLE_SYMMETRIES": "1" if cfg.get("enable_symmetries", True) else "0",
        "BM_MESH_USE_MANUAL": "1" if cfg.get("bm_mesh_manual") else "0",
        "BM_MIRROR": "0",
        "MASS_SCALING_DT": f"{cfg['mass_scaling']:.2e}",
        "PUNCH_SPEED": f"{cfg['punch_speed']:.6g}",
        "PUNCH_DISPLACEMENT": f"{cfg['punch_displacement']:.6g}",
        "PUNCH_VELOCITY_PROFILE": str(cfg.get("punch_velocity_profile", "smoothstep")),
        "FR_PUNCH": f"{cfg.get('fr_punch', 0.0):.6g}",
    }

    if cfg.get("bm_mesh_manual"):
        env.update({
            "BM_MESH_TAG": re.sub(r"[^A-Za-z0-9]+", "", str(cfg.get("bm_mesh_tag", "")))[:24],
            "BM_P_INNER_X": str(cfg["bm_p_inner_x"]),
            "BM_P_INNER_R": str(cfg["bm_p_inner_r"]),
            "BM_P_CIRCLE_R": str(cfg["bm_p_circle_r"]),
            "BM_P_XZPLANE_1": str(cfg["bm_p_xzplane_1"]),
            "BM_W200_SECTION1_Y": str(cfg["bm_w200_section1_y"]),
            "BM_W200_SECTION2_R": str(cfg["bm_w200_section2_r"]),
            "BM_W200_SECTION3_R": str(cfg["bm_w200_section3_r"]),
            "BM_MESH_SECTION1_X": str(cfg["bm_mesh_section1_x"]),
            "BM_MESH_SECTION1_Y": str(cfg["bm_mesh_section1_y"]),
            "BM_MESH_SECTION2_X": str(cfg["bm_mesh_section2_x"]),
            "BM_MESH_SECTION2_Y": str(cfg["bm_mesh_section2_y"]),
            "BM_MESH_SECTION3_Y": str(cfg["bm_mesh_section3_y"]),
            "BM_MESH_SECTION3_1_Y": str(cfg["bm_mesh_section3_1_y"]),
            "BM_MESH_SECTION4_Y": str(cfg["bm_mesh_section4_y"]),
            "BM_MESH_W200_SECTION1": str(cfg["bm_mesh_w200_section1"]),
            "BM_MESH_W200_SECTION2": str(cfg["bm_mesh_w200_section2"]),
            "BM_MESH_W200_SECTION3": str(cfg["bm_mesh_w200_section3"]),
            "BM_MESH_W200_SECTION4": str(cfg["bm_mesh_w200_section4"]),
        })

    if include_width:
        env["SPECIMEN_WIDTH"] = str(cfg["width"])

    if cfg["test_type"] == "pip":
        env["PIP_PUNCH2_ID"] = cfg["pip_id"]
    else:
        env["PUNCH_RADIUS"] = str(cfg["punch_diam"] / 2.0)

    return env


def _ceil_div(length, size):
    size = max(float(size), 1e-9)
    return max(1, int(math.ceil(max(float(length), 0.0) / size)))


def _bm_estimate_for_width(cfg, specimen_width):
    """Approximate BM element count from the same section sizes used by Nakazima_BM.py."""
    width = int(specimen_width)
    thickness_seeds = max(1, int(cfg["thickness_seeds"]))
    mesh_scale = float(cfg["mesh_factor"])
    manual = bool(cfg.get("bm_mesh_manual"))

    if width == 20:
        p_inner_x, p_circle_r, p_xz = 5.0, 55.0, 5.0
    else:
        p_inner_x, p_circle_r, p_xz = 10.0, 65.0, 5.0

    if manual:
        p_inner_x = float(cfg["bm_p_inner_x"])
        p_circle_r = float(cfg["bm_p_circle_r"])
        p_xz = float(cfg["bm_p_xzplane_1"])
        s1x = float(cfg["bm_mesh_section1_x"])
        s1y = float(cfg["bm_mesh_section1_y"])
        s2x = float(cfg["bm_mesh_section2_x"])
        s2y = float(cfg["bm_mesh_section2_y"])
        s3y = float(cfg["bm_mesh_section3_y"])
        s31y = float(cfg["bm_mesh_section3_1_y"])
        s4y = float(cfg["bm_mesh_section4_y"])
        w200_s1 = float(cfg["bm_mesh_w200_section1"])
        w200_s2 = float(cfg["bm_mesh_w200_section2"])
        w200_s3 = float(cfg["bm_mesh_w200_section3"])
        w200_s4 = float(cfg["bm_mesh_w200_section4"])
        w200_p1 = float(cfg["bm_w200_section1_y"])
        w200_p2 = float(cfg["bm_w200_section2_r"])
        w200_p3 = float(cfg["bm_w200_section3_r"])
    else:
        s1x = s1y = 0.2 * mesh_scale
        s2x = s2y = 0.4 * mesh_scale
        s3y = s31y = 0.8 * mesh_scale
        s4y = 1.2 * mesh_scale
        w200_s1 = 0.2 * mesh_scale
        w200_s2 = 0.4 * mesh_scale
        w200_s3 = 0.8 * mesh_scale
        w200_s4 = 0.4 * mesh_scale
        w200_p1, w200_p2, w200_p3 = 10.0, 20.0, 50.0

    if width == 200:
        quarter = math.pi / 4.0
        a1 = max(w200_p1, 0.0) ** 2
        a2 = max(quarter * w200_p2 ** 2 - a1, 0.0)
        a3 = max(quarter * (w200_p3 ** 2 - w200_p2 ** 2), 0.0)
        a4 = max(quarter * (70.0 ** 2 - w200_p3 ** 2), 0.0)
        in_plane = (
            a1 / max(w200_s1 ** 2, 1e-9)
            + a2 / max(w200_s2 ** 2, 1e-9)
            + a3 / max(w200_s3 ** 2, 1e-9)
            + a4 / max(w200_s4 ** 2, 1e-9)
        )
        return {
            "width": width,
            "in_plane": int(round(in_plane)),
            "solid": int(round(in_plane * thickness_seeds)),
            "method": "area",
        }

    half_width = width / 2.0
    n1x = _ceil_div(min(p_inner_x, half_width), s1x)
    n2x = _ceil_div(max(half_width - p_inner_x, 0.0), s2x)
    n1y = _ceil_div(p_xz, s1y)
    n2y = _ceil_div(12.5 - p_xz, s2y)
    if width == 20:
        n3y = _ceil_div(48.35 - 12.5, s3y)
        n31y = _ceil_div(p_circle_r - 48.35, s31y)
    elif width == 50:
        n3y = _ceil_div(58.21 - 12.5, s3y)
        n31y = _ceil_div(p_circle_r - 58.21, s31y)
    else:
        n3y = _ceil_div(p_circle_r - 12.5, s3y)
        n31y = 0
    n4y = _ceil_div(70.0 - p_circle_r, s4y)
    in_plane = (n1x + n2x) * (n1y + n2y + n3y + n31y + n4y)
    return {
        "width": width,
        "in_plane": int(in_plane),
        "solid": int(in_plane * thickness_seeds),
        "method": "seed",
    }


def _bm_mesh_estimates(cfg, widths):
    sym_factor = 1.0 if cfg.get("enable_symmetries", True) else 4.0
    rows = []
    for w in widths:
        est = _bm_estimate_for_width(cfg, w)
        # Apply symmetry factor to both in-plane and total solid cells
        est["in_plane"] = int(round(est["in_plane"] * sym_factor))
        est["solid"] = int(round(est["solid"] * sym_factor))
        rows.append(est)
    total = sum(r["solid"] for r in rows)
    return rows, total


def _bm_suggest_resources(cell_count):
    """
    Return a solver resource suggestion based on estimated cell count.
    User Rule: 1 CPU per 10,000 elements.
    """
    cells = max(1, int(cell_count))

    # Calculate CPUs based on 10k rule
    suggested_cpus = int(math.ceil(cells / 10000.0))
    # Round to nearest even number for better node alignment
    if suggested_cpus % 2 != 0:
        suggested_cpus += 1
    
    # Constrain between 4 and 32
    cpus = max(4, min(32, suggested_cpus))

    # Wall time scaling (conservative estimates for Explicit forming)
    if cells <= 100000:
        hours = 24
    elif cells <= 400000:
        hours = 48
    else:
        hours = 72

    return {
        "num_cpus": cpus,
        "slurm_cpus_per_task": cpus,
        "slurm_mem_per_cpu_gb": 4.0,  # 4GB/CPU is the safe standard for Euler
        "slurm_time_hours": hours,
        "slurm_time_limit": f"{hours:02d}:00:00",
        "abaqus_memory_percent": 90,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Job-progress helpers
# ─────────────────────────────────────────────────────────────────────────────
_TEST_MAP = {'Naka': 'nakazima', 'Marc': 'marciniak', 'Pip': 'pip'}
_JOB_RE   = re.compile(r'^(Naka|Marc|Pip)\d*_W\d+_t([\dp]+)_ang(\d+)')


# config.py default: STEP_TIME = 35 mm / 5 mm/s = 7 s; PiP both steps = 10 s.
# Speed/travel overrides are captured in _ps/_pd suffixes and handled below.
_STEP_TIMES = {'nakazima': [7.0], 'marciniak': [7.0], 'pip': [10.0, 10.0], '_punch_disp': 35.0}


def _parse_float_token(token: str) -> float | None:
    try:
        return float(str(token).replace("p", "."))
    except Exception:
        return None


def _clean_result_suffix(text: str) -> str:
    """Normalize result-label suffixes without dropping real job-name tokens."""
    cleaned = str(text)
    cleaned = re.sub(r'__+', '_', cleaned).strip('_')
    return cleaned


def _job_step_times(job_name: str, test_type: str) -> list[float]:
    """Return expected simulation step time(s), honoring job-name speed/travel suffixes."""
    if test_type != "pip":
        punch_disp = float(_STEP_TIMES.get('_punch_disp', 35.0))
        m_pd = re.search(r'_pd([\dp]+)(?:_|$)', job_name)
        if m_pd:
            parsed_disp = _parse_float_token(m_pd.group(1))
            if parsed_disp and parsed_disp > 0:
                punch_disp = parsed_disp
        m_ps = re.search(r'_ps([\dp]+)(?:_|$)', job_name)
        if m_ps:
            speed = _parse_float_token(m_ps.group(1))
            if speed and speed > 0:
                return [punch_disp / speed]
        return [punch_disp / 5.0]
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
    then tail the .sta file in that directory.  Works for flat and grouped
    submit_one layouts without any path inference.
    """
    home       = _remote_project_root(user)
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
        res = _run_ssh_command(
            _ssh_command(f"{user}@{host}", batch, connect_timeout=8),
            timeout=_ssh_timeout(default_normal=120, default_key_only=30),
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
    "thickness_seeds": 16,
    "enable_symmetries": True,
    "bm_mesh_manual": False,
    "bm_mesh_tag": "",
    "bm_p_inner_x": 10.0,
    "bm_p_inner_r": 120.0,
    "bm_p_circle_r": 65.0,
    "bm_p_xzplane_1": 5.0,
    "bm_w200_section1_y": 10.0,
    "bm_w200_section2_r": 20.0,
    "bm_w200_section3_r": 50.0,
    "bm_mesh_section1_x": 0.2,
    "bm_mesh_section1_y": 0.2,
    "bm_mesh_section2_x": 0.4,
    "bm_mesh_section2_y": 0.4,
    "bm_mesh_section3_y": 0.8,
    "bm_mesh_section3_1_y": 0.8,
    "bm_mesh_section4_y": 1.2,
    "bm_mesh_w200_section1": 0.2,
    "bm_mesh_w200_section2": 0.4,
    "bm_mesh_w200_section3": 0.8,
    "bm_mesh_w200_section4": 0.4,
    "mass_scaling": 1e-5,
    "punch_speed": 5.0,
    "punch_displacement": 35.0,
    "punch_velocity_profile": "smoothstep",
    "fr_punch": 0.0,
    "pip_id": "PUNCH_21",
}

DEFAULT_KEYS = tuple(defaults.keys())
USER_DEFAULT_KEYS = (
    "test_type",
    "width",
    "thickness",
    "angle",
    "punch_diam",
    "mesh_factor",
    "thickness_seeds",
    "enable_symmetries",
    "mass_scaling",
    "punch_speed",
    "punch_displacement",
    "punch_velocity_profile",
    "fr_punch",
    "pip_id",
)


def _load_user_job_defaults():
    try:
        with open(USER_DEFAULTS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _sanitize_job_defaults(values):
    cleaned = dict(values)
    if cleaned.get("test_type") not in ("nakazima", "marciniak", "pip"):
        cleaned.pop("test_type", None)
    if cleaned.get("width") not in WIDTH_OPTIONS:
        cleaned.pop("width", None)
    if cleaned.get("mass_scaling") not in MS_OPTIONS:
        cleaned.pop("mass_scaling", None)
    if cleaned.get("pip_id") not in PIP_OPTIONS:
        cleaned.pop("pip_id", None)
    return cleaned


def _save_user_job_defaults(values):
    cleaned = {k: values[k] for k in USER_DEFAULT_KEYS if k in values}
    with open(USER_DEFAULTS_PATH, "w", encoding="utf-8") as fp:
        json.dump(cleaned, fp, indent=2, sort_keys=True)
        fp.write("\n")


defaults.update(_sanitize_job_defaults(_load_user_job_defaults()))

# Seed defaults, then re-assert every value on every run. Streamlit garbage-
# collects the session_state entry of any keyed widget that is not rendered on a
# given run (e.g. the Submit Job inputs while you are on another page). Without
# this re-assertion, returning to the page recreates the bare number_inputs with
# their implicit default of 0, silently zeroing punch_diam, thickness, etc.
for k, v in defaults.items():
    st.session_state[k] = st.session_state.get(k, v)


# ─────────────────────────────────────────────────────────────────────────────
# UI Header
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Account (Euler user) — mirrors the Tkinter app's login: pick and verify an
# ETH user once; sync paths, remote listings and job monitoring adapt to it.
# ─────────────────────────────────────────────────────────────────────────────
_USER_SETTINGS_PATH = os.path.join(PROJECT_DIR, ".streamlit", "user_settings.json")


def _normalize_ssh_auth_mode(mode):
    return mode if mode in SSH_AUTH_LABELS else SSH_AUTH_NORMAL


def _load_user_settings():
    data = {}
    try:
        with open(_USER_SETTINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        pass
    users = [u for u in data.get("known_users", []) if isinstance(u, str) and u]
    current = data.get("username") or EULER_USER
    for u in (current, EULER_USER):
        if u not in users:
            users.append(u)
    return {
        "username": current,
        "host": data.get("host") or EULER_HOST,
        "known_users": users,
        "auto_login": bool(data.get("auto_login")),
        "ssh_auth_mode": _normalize_ssh_auth_mode(data.get("ssh_auth_mode")),
    }


def _save_user_settings():
    try:
        os.makedirs(os.path.dirname(_USER_SETTINGS_PATH), exist_ok=True)
        with open(_USER_SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump({
                "username": st.session_state["euler_user"],
                "host": st.session_state["euler_host"],
                "known_users": st.session_state["euler_known_users"],
                "auto_login": bool(st.session_state.get("euler_auto_login")),
                "ssh_auth_mode": _current_ssh_auth_mode(),
            }, fh, indent=2)
            fh.write("\n")
    except OSError:
        pass


if "euler_user" not in st.session_state:
    _us = _load_user_settings()
    st.session_state["euler_user"] = _us["username"]
    st.session_state["euler_host"] = _us["host"]
    st.session_state["euler_known_users"] = _us["known_users"]
    st.session_state["euler_auto_login"] = _us["auto_login"]
    st.session_state["euler_ssh_auth_mode"] = _us["ssh_auth_mode"]
    # "Remember me" skips the login screen for the saved user.
    st.session_state.setdefault("euler_logged_in", _us["auto_login"])


def _current_user():
    return st.session_state.get("euler_user", EULER_USER)


def _current_host():
    return st.session_state.get("euler_host", EULER_HOST)


def _current_ssh_auth_mode():
    return _normalize_ssh_auth_mode(st.session_state.get("euler_ssh_auth_mode"))


def _mark_euler_verified(user, host, auth_mode, control_path=None):
    st.session_state["euler_verify_status"] = "ok"
    st.session_state["euler_verified_user"] = user
    st.session_state["euler_verified_host"] = host
    st.session_state["euler_verified_auth_mode"] = _normalize_ssh_auth_mode(auth_mode)
    if control_path:
        st.session_state["euler_ssh_control_path"] = control_path
    else:
        st.session_state.pop("euler_ssh_control_path", None)


def _clear_euler_verified():
    st.session_state["euler_verify_status"] = None
    st.session_state.pop("euler_verified_user", None)
    st.session_state.pop("euler_verified_host", None)
    st.session_state.pop("euler_verified_auth_mode", None)
    st.session_state.pop("euler_ssh_control_path", None)


def _current_ssh_control_path():
    path = st.session_state.get("euler_ssh_control_path")
    if path and os.path.exists(path):
        return path
    return ""


def _euler_access_verified():
    verified = (
        st.session_state.get("euler_verify_status") == "ok"
        and st.session_state.get("euler_verified_user") == _current_user()
        and st.session_state.get("euler_verified_host") == _current_host()
        and st.session_state.get("euler_verified_auth_mode") == _current_ssh_auth_mode()
    )
    if not verified:
        return False
    if _current_ssh_auth_mode() == SSH_AUTH_NORMAL:
        return bool(_current_ssh_control_path())
    return True


def _ssh_auth_options(connect_timeout=8, auth_mode=None):
    mode = _normalize_ssh_auth_mode(auth_mode or _current_ssh_auth_mode())
    opts = ["-o", f"ConnectTimeout={int(connect_timeout)}", "-o", "LogLevel=ERROR"]
    if mode == SSH_AUTH_KEY_ONLY:
        opts[0:0] = ["-o", "BatchMode=yes"]
    elif _current_ssh_control_path():
        opts.extend(
            [
                "-o", "BatchMode=yes",
                "-o", "ControlMaster=no",
                "-S", _current_ssh_control_path(),
            ]
        )
    else:
        opts.extend(
            [
                "-o", "BatchMode=no",
                "-o", "PubkeyAuthentication=no",
                "-o", "PreferredAuthentications=keyboard-interactive,password",
                "-o", "KbdInteractiveAuthentication=yes",
                "-o", "PasswordAuthentication=yes",
                "-o", "ControlMaster=no",
                "-S", "none",
            ]
        )
    return opts


def _ssh_command(spec, remote_command, connect_timeout=8, auth_mode=None):
    return ["ssh", *_ssh_auth_options(connect_timeout, auth_mode), spec, remote_command]


def _ssh_transport(connect_timeout=8, auth_mode=None):
    return "ssh " + " ".join(shlex.quote(part) for part in _ssh_auth_options(connect_timeout, auth_mode))


def _ssh_timeout(default_normal=120, default_key_only=30, auth_mode=None):
    return default_key_only if _normalize_ssh_auth_mode(auth_mode or _current_ssh_auth_mode()) == SSH_AUTH_KEY_ONLY else default_normal


def _run_ssh_command(cmd, timeout, auth_mode=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


_TERMINAL_AUTH_DIR = os.path.join(PROJECT_DIR, ".streamlit", "terminal_auth")


def _terminal_verify_marker(user, host):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{user}_{host}")
    return os.path.join(_TERMINAL_AUTH_DIR, f"verify_{safe}.json")


def _terminal_verify_script(user, host):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{user}_{host}")
    return os.path.join(_TERMINAL_AUTH_DIR, f"verify_{safe}.sh")


def _terminal_control_path(user, host):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{user}_{host}")
    return os.path.join("/tmp", f"abaqusproject_ssh_{safe}.sock")


def _terminal_window_title(user, host):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{user}_{host}")
    return f"Abaqus Euler Login {safe}"


def _apple_string(text):
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _open_macos_terminal(shell_command, title=None):
    escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
    title_escaped = _apple_string(title or "")
    script = (
        "tell application \"Terminal\"\n"
        f"  set targetTab to do script \"{escaped}\"\n"
        "  try\n"
        f"    set custom title of targetTab to \"{title_escaped}\"\n"
        "  end try\n"
        "  return id of front window\n"
        "end tell\n"
    )
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)


def _schedule_terminal_window_close(title=None, window_id=None, delay_seconds=6):
    if not title and not window_id:
        return
    escaped = _apple_string(title or "")
    lines = [f"delay {int(delay_seconds)}", 'tell application "Terminal"']
    if window_id:
        lines.extend(
            [
                "  repeat with w in windows",
                f"    if id of w is {int(window_id)} then",
                "      close w",
                "      return",
                "    end if",
                "  end repeat",
            ]
        )
    if title:
        lines.extend(
            [
                "  repeat with w in windows",
                f"    if name of w contains \"{escaped}\" then",
                "      close w",
                "      return",
                "    end if",
                "  end repeat",
            ]
        )
    lines.append("end tell")
    script = "\n".join(lines)
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def _start_terminal_euler_verify(user, host):
    marker = _terminal_verify_marker(user, host)
    script_path = _terminal_verify_script(user, host)
    control_path = _terminal_control_path(user, host)
    window_title = f"{_terminal_window_title(user, host)} {int(time.time())}"
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    try:
        os.remove(marker)
    except FileNotFoundError:
        pass
    spec = f"{user}@{host}"
    close_master_cmd = " ".join(
        shlex.quote(part)
        for part in [
            "ssh",
            "-S", control_path,
            "-O", "exit",
            "-o", "BatchMode=yes",
            "-o", "ControlMaster=no",
            "-o", "ConnectTimeout=5",
            "-o", "LogLevel=ERROR",
            spec,
        ]
    )
    start_master_parts = [
        "ssh",
        "-M",
        "-S", control_path,
        "-fN",
        "-o", "ControlPersist=4h",
        "-o", "ConnectTimeout=15",
        "-o", "LogLevel=ERROR",
        "-o", "BatchMode=no",
        "-o", "PubkeyAuthentication=no",
        "-o", "PreferredAuthentications=keyboard-interactive,password",
        "-o", "KbdInteractiveAuthentication=yes",
        "-o", "PasswordAuthentication=yes",
        spec,
    ]
    start_master_cmd = " ".join(shlex.quote(part) for part in start_master_parts)
    check_master_parts = [
        "ssh",
        "-S", control_path,
        "-o", "BatchMode=yes",
        "-o", "ControlMaster=no",
        "-o", "ConnectTimeout=8",
        "-o", "LogLevel=ERROR",
        spec,
        "true",
    ]
    check_master_cmd = " ".join(shlex.quote(part) for part in check_master_parts)
    close_self_lines = [
        'tell application "Terminal"',
        '  repeat with w in windows',
        f'    if name of w contains "{_apple_string(window_title)}" then',
        '      close w',
        '      exit repeat',
        '    end if',
        '  end repeat',
        'end tell',
    ]
    close_self_cmd = " ".join(
        shlex.quote(part)
        for part in ["osascript", *[part for line in close_self_lines for part in ("-e", line)]]
    )
    close_self_later_cmd = (
        " ".join(
            shlex.quote(part)
            for part in ["nohup", "bash", "-c", f"sleep 5; {close_self_cmd}"]
        )
        + " >/dev/null 2>&1 &"
    )
    ok_payload = json.dumps(
        {
            "ok": True,
            "user": user,
            "host": host,
            "auth_mode": SSH_AUTH_NORMAL,
            "control_path": control_path,
        }
    )
    fail_payload = json.dumps({"ok": False, "user": user, "host": host, "auth_mode": SSH_AUTH_NORMAL})
    script = (
        "#!/bin/bash\n"
        "clear\n"
        f"printf '\\033]0;%s\\007' {shlex.quote(window_title)}\n"
        f"echo {shlex.quote(f'Euler login: {user}@{host}')}\n"
        "echo\n"
        "echo 'If SSH asks, type your password or 2FA here.'\n"
        "echo 'Password input is hidden while typing.'\n"
        "echo\n"
        f"mkdir -p {shlex.quote(os.path.dirname(marker))}\n"
        f"rm -f {shlex.quote(marker)}\n"
        f"{close_master_cmd} >/dev/null 2>&1 || true\n"
        f"rm -f {shlex.quote(control_path)}\n"
        f"if {start_master_cmd} >/dev/null && {check_master_cmd} >/dev/null; then\n"
        f"  printf '%s\\n' {shlex.quote(ok_payload)} > {shlex.quote(marker)}\n"
        "  echo\n"
        "  echo 'Verified. Streamlit will update automatically.'\n"
        "else\n"
        f"  printf '%s\\n' {shlex.quote(fail_payload)} > {shlex.quote(marker)}\n"
        "  echo\n"
        "  echo 'Login failed. Streamlit will show the error.'\n"
        "fi\n"
        "echo\n"
        "echo 'This window closes in 5 seconds.'\n"
        f"{close_self_later_cmd}\n"
        "exit 0\n"
    )
    try:
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(script)
        os.chmod(script_path, 0o700)
    except OSError as exc:
        return False, f"Could not create Terminal login helper: {exc}", marker
    result = _open_macos_terminal(f"bash {shlex.quote(script_path)}", title=window_title)
    if result.returncode != 0:
        return False, result.stderr or result.stdout or "Could not open Terminal.", marker
    window_id = None
    try:
        window_id = int((result.stdout or "").strip().splitlines()[-1])
    except (IndexError, ValueError):
        pass
    st.session_state["_terminal_verify"] = {
        "user": user,
        "host": host,
        "marker": marker,
        "title": window_title,
        "window_id": window_id,
    }
    return True, "", marker


def _check_terminal_euler_verify():
    pending = st.session_state.get("_terminal_verify") or {}
    marker = pending.get("marker")
    if not marker or not os.path.exists(marker):
        return None, "Still waiting for the Terminal verification result."
    try:
        with open(marker, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False, "Could not read the Terminal verification result."
    if data.get("ok"):
        control_path = data.get("control_path")
        if not control_path or not os.path.exists(control_path):
            return False, "Terminal login succeeded, but the reusable SSH connection is missing. Verify again."
        pending["control_path"] = control_path
        st.session_state["_terminal_verify"] = pending
        return True, ""
    return False, "Terminal SSH verification failed."


def _finish_terminal_euler_login(pending):
    st.session_state["euler_auto_login"] = bool(
        pending.get("remember", st.session_state.get("euler_auto_login"))
    )
    _switch_user(pending["user"], pending["host"])
    _mark_euler_verified(
        pending["user"],
        pending["host"],
        SSH_AUTH_NORMAL,
        control_path=pending.get("control_path"),
    )
    st.session_state["euler_logged_in"] = True
    st.session_state.pop("_terminal_verify", None)
    _save_user_settings()
    _schedule_terminal_window_close(
        title=pending.get("title") or _terminal_window_title(pending["user"], pending["host"]),
        window_id=pending.get("window_id"),
        delay_seconds=6,
    )


def _render_terminal_login_poll(key_prefix):
    pending = st.session_state.get("_terminal_verify") or {}
    if not pending.get("user") or not pending.get("host"):
        return False

    ok, reason = _check_terminal_euler_verify()
    if ok is True:
        pending = st.session_state.get("_terminal_verify") or pending
        _finish_terminal_euler_login(pending)
        st.rerun()
    if ok is False:
        st.session_state.pop("_terminal_verify", None)
        st.error(reason)
        return False

    st.info(f"Waiting for Terminal login: {pending['user']}@{pending['host']}")
    st.caption("After the password or 2FA succeeds, Streamlit logs in automatically.")
    st_autorefresh(interval=1000, limit=600, key=f"{key_prefix}_terminal_login_poll")
    return True


def _default_results_dir(user=None):
    """Per-user local mirror so one user's sync never mixes into another's."""
    user = user or _current_user()
    suffix = "" if user == EULER_USER else f"_{user}"
    return os.path.join(PROJECT_DIR, f"FLC_output{suffix}")


def _default_euler_src(user=None, host=None):
    user = user or _current_user()
    host = host or _current_host()
    return f"{user}@{host}:{_remote_project_root(user)}/FLC_output/"


def _switch_user(new_user, new_host):
    """Re-point every user-dependent path, widget and cache, then persist."""
    _clear_euler_verified()
    st.session_state["euler_user"] = new_user
    st.session_state["euler_host"] = new_host
    known = st.session_state.get("euler_known_users", [])
    if new_user not in known:
        known.append(new_user)
    st.session_state["euler_known_users"] = known
    st.session_state["results_local_dir"] = _default_results_dir(new_user)
    st.session_state["results_euler_src"] = _default_euler_src(new_user, new_host)
    st.session_state.pop("_remote_job_index", None)
    st.session_state.pop("sta_cache", None)
    for key in [k for k in st.session_state if str(k).startswith("sens_runtimes")]:
        st.session_state.pop(key, None)
    _invalidate_results_caches()
    _save_user_settings()


def _verify_euler_connection(user, host, auth_mode=None):
    """Return (ok, reason) for non-interactive key checks."""
    auth_mode = _normalize_ssh_auth_mode(auth_mode or _current_ssh_auth_mode())
    try:
        r = _run_ssh_command(
            _ssh_command(f"{user}@{host}", "echo ok", connect_timeout=15, auth_mode=auth_mode),
            timeout=_ssh_timeout(default_normal=180, default_key_only=20, auth_mode=auth_mode),
            auth_mode=auth_mode,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception:
        return False, "error"
    if r.returncode == 0 and "ok" in r.stdout:
        return True, ""
    err = (getattr(r, "stderr", None) or "").lower()
    if "permission denied" in err:
        return False, "no-key" if auth_mode == SSH_AUTH_KEY_ONLY else "auth"
    if "can't open /dev/tty" in err or "read_passphrase" in err:
        return False, "terminal"
    if "timed out" in err or "no route" in err or "network is unreachable" in err:
        return False, "vpn"
    if "could not resolve" in err:
        return False, "host"
    return False, "error"


_SSH_FAIL_HINTS = {
    "no-key": "This machine's SSH key is not authorized for that user. "
              "Password login is not possible from the app — set up key "
              "access once in a terminal (see below), then retry.",
    "auth":   "SSH authentication failed. In normal SSH mode, complete the "
              "Euler password or 2FA prompt in the separate Terminal login window.",
    "terminal": "SSH could not open the separate Terminal login window. Retry normal SSH mode.",
    "vpn":    "Euler is unreachable — connect the ETH VPN and retry.",
    "timeout": "Euler is unreachable — connect the ETH VPN and retry.",
    "host":   "Hostname not found — check the Host field.",
    "error":  "SSH failed — check VPN, hostname and key access.",
}


def _ssh_key_setup_help(user, host):
    with st.expander("Set up key access for this user (one-time)"):
        st.markdown(
            "Run these in a terminal. The second command asks for the "
            "Euler password once, after that the app connects without it."
        )
        st.code(
            "[ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519\n"
            f"ssh-copy-id {user}@{host}",
            language="bash",
        )


def _login_screen():
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.title("⚙️ Abaqus Pipeline")
        st.caption("Sign in to ETH Euler")
        known = st.session_state["euler_known_users"]
        pick = st.selectbox(
            "ETH user",
            known + ["New user…"],
            index=known.index(_current_user()),
        )
        if pick == "New user…":
            pick = st.text_input("New ETH username", key="login_new_user").strip()
        host = st.text_input("Host", value=_current_host(), key="login_host")
        remember = st.checkbox(
            "Remember me — skip this screen next time",
            value=bool(st.session_state.get("euler_auto_login")),
            key="login_remember",
        )
        auth_mode = st.radio(
            "SSH authentication",
            [SSH_AUTH_NORMAL, SSH_AUTH_KEY_ONLY],
            format_func=lambda mode: SSH_AUTH_LABELS[mode],
            horizontal=True,
            key="euler_ssh_auth_mode",
            help=(
                "Normal mode can use password or 2FA in a separate Terminal window. "
                "It deliberately ignores SSH keys. Key-only mode fails fast and never prompts."
            ),
        )
        if auth_mode == SSH_AUTH_NORMAL:
            st.caption("A Terminal window will open for password or 2FA. Password input is hidden while typing.")
        if _render_terminal_login_poll("login"):
            return
        c_go, c_off = st.columns(2)
        connect = c_go.button("Connect", type="primary", width="stretch",
                              disabled=not pick)
        offline = c_off.button("Continue offline", width="stretch",
                               disabled=not pick,
                               help="Skip the SSH check (e.g. no VPN). Local "
                                    "results work; sync and job monitoring "
                                    "need a connection.")
        if (connect or offline) and pick:
            verify_state = None
            host_clean = host.strip() or EULER_HOST
            if connect:
                if auth_mode == SSH_AUTH_NORMAL:
                    launched, reason, _marker = _start_terminal_euler_verify(pick, host_clean)
                    if not launched:
                        st.error(reason)
                    else:
                        st.session_state["_terminal_verify"]["remember"] = bool(remember)
                        st.rerun()
                    return
                else:
                    with st.spinner(f"Connecting {pick}@{host_clean}..."):
                        ok, reason = _verify_euler_connection(pick, host_clean, auth_mode=auth_mode)
                    if not ok:
                        st.error(_SSH_FAIL_HINTS.get(reason, _SSH_FAIL_HINTS["error"]))
                        if reason == "no-key":
                            _ssh_key_setup_help(pick, host_clean)
                        st.caption("You can still **Continue offline** to browse local results.")
                        return
                    verify_state = "ok"
            st.session_state["euler_auto_login"] = bool(remember)
            _switch_user(pick, host_clean)
            if verify_state == "ok":
                _mark_euler_verified(pick, host_clean, auth_mode)
            st.session_state["euler_logged_in"] = True
            st.rerun()


if not st.session_state.get("euler_logged_in"):
    _login_screen()
    st.stop()


_c_title, _c_user = st.columns([4, 1.3], vertical_alignment="center")
with _c_title:
    st.title("⚙️ Abaqus Pipeline")
with _c_user:
    _verify_state = st.session_state.get("euler_verify_status")
    _user_icon = "🟢" if _euler_access_verified() else {"fail": "🔴"}.get(_verify_state, "⚪")
    with st.popover(f"{_user_icon} {_current_user()}", width="stretch"):
        _known_users = st.session_state["euler_known_users"]
        _pick = st.selectbox(
            "ETH user",
            _known_users + ["New user…"],
            index=_known_users.index(_current_user()),
        )
        if _pick == "New user…":
            _pick = st.text_input("New ETH username", key="account_new_user").strip()
        _host_pick = st.text_input("Host", value=_current_host(), key="account_host")
        _auth_pick = st.radio(
            "SSH authentication",
            [SSH_AUTH_NORMAL, SSH_AUTH_KEY_ONLY],
            format_func=lambda mode: SSH_AUTH_LABELS[mode],
            horizontal=True,
            key="euler_ssh_auth_mode",
            help="Normal mode prompts only in a separate Terminal window and deliberately ignores SSH keys. Key-only mode never prompts.",
        )
        _terminal_login_pending = _render_terminal_login_poll("account")
        _c_verify, _c_switch = st.columns(2)
        if _c_verify.button("Verify", key="account_verify", width="stretch",
                            disabled=(not _pick) or _terminal_login_pending):
            _host_clean = _host_pick.strip() or EULER_HOST
            if _auth_pick == SSH_AUTH_NORMAL:
                _launched, _reason, _marker = _start_terminal_euler_verify(_pick, _host_clean)
                if _launched:
                    st.rerun()
                else:
                    st.error(_reason)
            else:
                with st.spinner(f"ssh {_pick}@{_host_clean}..."):
                    _ok, _reason = _verify_euler_connection(_pick, _host_clean, auth_mode=_auth_pick)
                if _ok:
                    _mark_euler_verified(_pick, _host_clean, _auth_pick)
                    st.success(f"Connected as {_pick}@{_host_clean}")
                else:
                    _clear_euler_verified()
                    st.session_state["euler_verify_status"] = "fail"
                    st.error(_SSH_FAIL_HINTS.get(_reason, _SSH_FAIL_HINTS["error"]))
                    if _reason == "no-key":
                        _ssh_key_setup_help(_pick, _host_clean)
        if _c_switch.button("Switch user", type="primary", key="account_switch",
                            width="stretch", disabled=(not _pick) or _terminal_login_pending,
                            help="Re-points results directory, Euler paths and "
                                 "job monitoring to this user."):
            _switch_user(_pick, _host_pick.strip() or EULER_HOST)
            st.session_state["euler_verify_status"] = None
            st.rerun()
        if st.button("Log out", key="account_logout", width="stretch",
                     help="Back to the sign-in screen; disables auto sign-in."):
            st.session_state["euler_logged_in"] = False
            st.session_state["euler_auto_login"] = False
            _clear_euler_verified()
            _save_user_settings()
            st.rerun()
        if _current_user() != EULER_USER:
            st.caption(f"Local mirror: `{os.path.basename(_default_results_dir())}`")

# Pages are plain functions handed to st.navigation (top bar) at the end of
# this file. Navigation state lives in the URL, so refresh and back/forward
# keep the current page.

# ══════════════════════════════════════════════════════════════════════════════
# Submit Job
# ══════════════════════════════════════════════════════════════════════════════
def _page_submit_job():

    st.subheader("Submit Job")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        test_type = st.selectbox("Test Type", ["nakazima", "marciniak", "pip"], key="test_type")

    with c2:
        width = st.selectbox("Width", WIDTH_OPTIONS, key="width")

    with c3:
        thickness = st.number_input("Thickness", key="thickness")

    with c4:
        angle = st.number_input("Angle", key="angle")

    c5, c6, c7, c8, c9, c10 = st.columns(6)
    with c5:
        if test_type == "pip":
            pip_id = st.selectbox("PiP Punch", PIP_OPTIONS, key="pip_id")
            punch_diam = None
        else:
            punch_diam = st.number_input("Punch Diameter", key="punch_diam")
            pip_id = None
    with c6:
        mesh_factor = st.number_input("Mesh Factor", key="mesh_factor")
    with c7:
        thickness_seeds = st.number_input("Thickness Seeds", min_value=1, max_value=64, step=1, key="thickness_seeds")
    with c8:
        mass_scaling = st.selectbox(
            "Mass Scaling Δt (s)",
            MS_OPTIONS,
            format_func=lambda x: f"{x:.1e}",
            key="mass_scaling",
        )
    with c9:
        punch_speed = st.number_input(
            "Punch Speed (mm/s)",
            min_value=0.1,
            step=0.5,
            key="punch_speed",
            disabled=(test_type == "pip"),
            help="Standard Nakazima/Marciniak punch speed. PiP uses its two configured step times.",
        )
    with c10:
        punch_displacement = st.number_input(
            "Punch Travel (mm)",
            min_value=0.1,
            step=1.0,
            key="punch_displacement",
            disabled=(test_type == "pip"),
            help="Standard Nakazima/Marciniak punch travel. PiP uses its two configured punch displacements.",
        )

    punch_velocity_profile = st.selectbox(
        "Punch velocity profile",
        ["smoothstep", "constant"],
        key="punch_velocity_profile",
        disabled=(test_type == "pip"),
        help=(
            "smoothstep (default): SmoothStep displacement — velocity 0→peak→0, "
            "decelerates through fracture (masks the Volk-Hora bifurcation). "
            "constant: constant punch speed with short smooth end-ramps — keeps "
            "the strain rate steady through fracture so V&H necking is resolvable. "
            "Constant runs get a '_vconst' job suffix and a separate ODB, so the "
            "two can be compared without collision."
        ),
    )

    fr_punch = st.number_input(
        "Punch Friction μ",
        min_value=0.0,
        max_value=0.50,
        step=0.01,
        format="%.3f",
        key="fr_punch",
        disabled=(test_type == "pip"),
        help=(
            "Coulomb friction coefficient between punch and blank. "
            "Default 0.0 (frictionless). Typical experimental values with "
            "PTFE+Lanolin lubrication are 0.03–0.10. Non-zero values add a "
            "'_frXpXX' suffix to the job name."
        ),
    )

    enable_symmetries = st.checkbox(
        "Enable Symmetries",
        key="enable_symmetries",
        help="Apply XSYMM and YSYMM boundary conditions on the x=0 and y=0 specimen symmetry planes.",
    )

    with st.expander("Advanced mesh settings"):
        st_components.html(_bm_mesh_zone_diagram_html(), height=720, scrolling=False)
        bm_mesh_manual = st.checkbox(
            "Enable manual mesh settings",
            key="bm_mesh_manual",
            help="Use absolute BM section sizes below instead of scaling the legacy mesh by Mesh Factor.",
        )
        bm_mesh_tag = st.text_input(
            "Manual mesh tag for directory labeling",
            max_chars=24,
            key="bm_mesh_tag",
            disabled=not bm_mesh_manual,
            help="Optional suffix for manual mesh comparison jobs.",
        )
        bm_general_disabled = (not bm_mesh_manual) or (int(width) == 200)
        st.caption("Partition geometry for W20-W120")
        pcols = st.columns(4)
        with pcols[0]:
            bm_p_inner_x = st.number_input("Inner split x", min_value=0.1, step=0.5,
                                           key="bm_p_inner_x",
                                           disabled=bm_general_disabled,
                                           help="Vertical partition at x = P_inner_x. Not used by W200.")
        with pcols[1]:
            bm_p_inner_r = st.number_input("Inner arc radius", min_value=1.0, step=5.0,
                                           key="bm_p_inner_r",
                                           disabled=bm_general_disabled,
                                           help="Radius of the curved partition centered at (P_inner_x + P_inner_r, 12.5). Not used by W200.")
        with pcols[2]:
            bm_p_circle_r = st.number_input("Circle radius", min_value=1.0, step=1.0,
                                            key="bm_p_circle_r",
                                            disabled=bm_general_disabled,
                                            help="Radius of the circular partition centered at the specimen origin. Not used by W200.")
        with pcols[3]:
            bm_p_xzplane_1 = st.number_input("XZ plane y", min_value=0.1, step=0.5,
                                             key="bm_p_xzplane_1",
                                             disabled=bm_general_disabled,
                                             help="Horizontal partition below y = 12.5 mm. Not used by W200.")

        st.caption("W200 partition geometry")
        wcols = st.columns(3)
        with wcols[0]:
            bm_w200_section1_y = st.number_input("W200 section 1 y", min_value=0.1, step=1.0,
                                                 key="bm_w200_section1_y",
                                                 disabled=not bm_mesh_manual)
        with wcols[1]:
            bm_w200_section2_r = st.number_input("W200 section 2 r", min_value=0.1, step=1.0,
                                                 key="bm_w200_section2_r",
                                                 disabled=not bm_mesh_manual)
        with wcols[2]:
            bm_w200_section3_r = st.number_input("W200 section 3 r", min_value=0.1, step=1.0,
                                                 key="bm_w200_section3_r",
                                                 disabled=not bm_mesh_manual)

        st.caption("Target element sizes for W20-W120")
        mcols = st.columns(4)
        with mcols[0]:
            bm_mesh_section1_x = st.number_input("S1 x", min_value=0.01, step=0.05,
                                                 key="bm_mesh_section1_x",
                                                 disabled=not bm_mesh_manual)
        with mcols[1]:
            bm_mesh_section1_y = st.number_input("S1 y", min_value=0.01, step=0.05,
                                                 key="bm_mesh_section1_y",
                                                 disabled=not bm_mesh_manual)
        with mcols[2]:
            bm_mesh_section2_x = st.number_input("S2 x", min_value=0.01, step=0.05,
                                                 key="bm_mesh_section2_x",
                                                 disabled=not bm_mesh_manual)
        with mcols[3]:
            bm_mesh_section2_y = st.number_input("S2 y", min_value=0.01, step=0.05,
                                                 key="bm_mesh_section2_y",
                                                 disabled=not bm_mesh_manual)

        mcols2 = st.columns(4)
        with mcols2[0]:
            bm_mesh_section3_y = st.number_input("S3 y", min_value=0.01, step=0.05,
                                                 key="bm_mesh_section3_y",
                                                 disabled=not bm_mesh_manual)
        with mcols2[1]:
            bm_mesh_section3_1_y = st.number_input("S3_1 y", min_value=0.01, step=0.05,
                                                   key="bm_mesh_section3_1_y",
                                                   disabled=not bm_mesh_manual)
        with mcols2[2]:
            bm_mesh_section4_y = st.number_input("S4 y", min_value=0.01, step=0.05,
                                                 key="bm_mesh_section4_y",
                                                 disabled=not bm_mesh_manual)

        st.caption("Target element sizes for W200")
        wmesh_cols = st.columns(4)
        with wmesh_cols[0]:
            bm_mesh_w200_section1 = st.number_input("W200 S1", min_value=0.01, step=0.05,
                                                    key="bm_mesh_w200_section1",
                                                    disabled=not bm_mesh_manual)
        with wmesh_cols[1]:
            bm_mesh_w200_section2 = st.number_input("W200 S2", min_value=0.01, step=0.05,
                                                    key="bm_mesh_w200_section2",
                                                    disabled=not bm_mesh_manual)
        with wmesh_cols[2]:
            bm_mesh_w200_section3 = st.number_input("W200 S3", min_value=0.01, step=0.05,
                                                    key="bm_mesh_w200_section3",
                                                    disabled=not bm_mesh_manual)
        with wmesh_cols[3]:
            bm_mesh_w200_section4 = st.number_input("W200 S4", min_value=0.01, step=0.05,
                                                    key="bm_mesh_w200_section4",
                                                    disabled=not bm_mesh_manual)

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
            st.image(_png_path, width="stretch")

        if os.path.exists(_step_path):
            with open(_step_path, "rb") as _f:
                st.download_button(
                    f"Download {pip_id}.step (CAD)",
                    _f, file_name=f"{pip_id}.step",
                    mime="application/step", key=f"step_{pip_id}",
                )

    base_cfg = dict(
        test_type=test_type,
        width=width,
        thickness=thickness,
        angle=angle,
        punch_diam=punch_diam,
        mesh_factor=mesh_factor,
        thickness_seeds=thickness_seeds,
        mass_scaling=mass_scaling,
        punch_speed=punch_speed,
        punch_displacement=punch_displacement,
        punch_velocity_profile=punch_velocity_profile,
        fr_punch=fr_punch,
        pip_id=pip_id,
        enable_symmetries=enable_symmetries,
        bm_mesh_manual=bm_mesh_manual,
        bm_mesh_tag=bm_mesh_tag,
        bm_p_inner_x=bm_p_inner_x,
        bm_p_inner_r=bm_p_inner_r,
        bm_p_circle_r=bm_p_circle_r,
        bm_p_xzplane_1=bm_p_xzplane_1,
        bm_w200_section1_y=bm_w200_section1_y,
        bm_w200_section2_r=bm_w200_section2_r,
        bm_w200_section3_r=bm_w200_section3_r,
        bm_mesh_section1_x=bm_mesh_section1_x,
        bm_mesh_section1_y=bm_mesh_section1_y,
        bm_mesh_section2_x=bm_mesh_section2_x,
        bm_mesh_section2_y=bm_mesh_section2_y,
        bm_mesh_section3_y=bm_mesh_section3_y,
        bm_mesh_section3_1_y=bm_mesh_section3_1_y,
        bm_mesh_section4_y=bm_mesh_section4_y,
        bm_mesh_w200_section1=bm_mesh_w200_section1,
        bm_mesh_w200_section2=bm_mesh_w200_section2,
        bm_mesh_w200_section3=bm_mesh_w200_section3,
        bm_mesh_w200_section4=bm_mesh_w200_section4,
    )

    estimate_rows, estimate_total = _bm_mesh_estimates(base_cfg, [base_cfg["width"]])
    resource_basis = estimate_rows[0]["solid"]
    resource_hint = _bm_suggest_resources(resource_basis)

    st.subheader("Computational settings")
    st.caption(
        "Suggested from the current mesh estimate: "
        f"{resource_hint['num_cpus']} CPUs, {resource_hint['slurm_time_limit']} wall time."
    )
    if st.button("Use suggested resources", key="apply_compute_hint"):
        st.session_state["solver_cpus"] = resource_hint["num_cpus"]
        st.session_state["slurm_mem_per_cpu_gb"] = resource_hint["slurm_mem_per_cpu_gb"]
        st.session_state["slurm_time_hours"] = resource_hint["slurm_time_hours"]
        st.session_state["abaqus_memory_percent"] = resource_hint["abaqus_memory_percent"]

    if "solver_cpus" not in st.session_state:
        st.session_state["solver_cpus"] = resource_hint["num_cpus"]
    if "slurm_mem_per_cpu_gb" not in st.session_state:
        st.session_state["slurm_mem_per_cpu_gb"] = resource_hint["slurm_mem_per_cpu_gb"]
    if "slurm_time_hours" not in st.session_state:
        st.session_state["slurm_time_hours"] = resource_hint["slurm_time_hours"]
    if "abaqus_memory_percent" not in st.session_state:
        st.session_state["abaqus_memory_percent"] = resource_hint["abaqus_memory_percent"]

    ccomp1, ccomp2 = st.columns(2)
    with ccomp1:
        # No value= here: state is seeded above, and passing both triggers
        # Streamlit's yellow "default value + Session State" warning in-app.
        solver_cpus = st.number_input(
            "Solver CPUs",
            min_value=1,
            max_value=64,
            step=1,
            key="solver_cpus",
            help="Used both for Abaqus/Explicit threads and SLURM cpus-per-task.",
        )
        abaqus_memory_percent = st.slider(
            "Abaqus memory (%)",
            min_value=50,
            max_value=95,
            step=1,
            key="abaqus_memory_percent",
        )
    with ccomp2:
        slurm_mem_per_cpu_gb = st.number_input(
            "SLURM memory per CPU (GB)",
            min_value=1.0,
            step=1.0,
            key="slurm_mem_per_cpu_gb",
        )
        slurm_time_hours = st.number_input(
            "SLURM wall time (h)",
            min_value=1,
            max_value=168,
            step=1,
            key="slurm_time_hours",
        )

    cfg = dict(
        **base_cfg,
        num_cpus=int(solver_cpus),
        abaqus_memory_percent=int(abaqus_memory_percent),
        slurm_mem_per_cpu_gb=float(slurm_mem_per_cpu_gb),
        slurm_time_hours=int(slurm_time_hours),
        slurm_time_limit=f"{int(slurm_time_hours):02d}:00:00",
    )

    st.markdown("---")

    # ── Job preview ──────────────────────────────────────────────────────────
    job_name = make_job_name(
        test_type=cfg["test_type"],
        specimen_width=cfg["width"],
        blank_thickness=cfg["thickness"],
        angle=cfg["angle"],
        punch_diameter=cfg["punch_diam"],
        mesh_factor=cfg["mesh_factor"],
        thickness_seeds=cfg["thickness_seeds"],
        mass_scaling_dt=cfg["mass_scaling"],
        pip_punch2_id=cfg["pip_id"],
        punch_speed=cfg["punch_speed"],
        punch_displacement=cfg["punch_displacement"],
        bm_mesh_manual=cfg["bm_mesh_manual"],
        bm_mesh_tag=cfg["bm_mesh_tag"],
        punch_velocity_profile=cfg["punch_velocity_profile"],
        fr_punch=cfg["fr_punch"],
    )

    study_root = make_study_root_name(
        test_type=cfg["test_type"],
        blank_thickness=cfg["thickness"],
        angle=cfg["angle"],
        punch_diameter=cfg["punch_diam"],
        mesh_factor=cfg["mesh_factor"],
        thickness_seeds=cfg["thickness_seeds"],
        mass_scaling_dt=cfg["mass_scaling"],
        pip_punch2_id=cfg["pip_id"],
        punch_speed=cfg["punch_speed"],
        punch_displacement=cfg["punch_displacement"],
        bm_mesh_manual=cfg["bm_mesh_manual"],
        bm_mesh_tag=cfg["bm_mesh_tag"],
        punch_velocity_profile=cfg["punch_velocity_profile"],
        fr_punch=cfg["fr_punch"],
    )

    st.code(job_name)
    st.caption(f"Study root: {study_root}")
    estimate_rows, estimate_total = _bm_mesh_estimates(cfg, [cfg["width"]])
    est = estimate_rows[0]
    st.metric("Estimated mesh cells", f"{estimate_total:,}")
    sym_desc = "quarter-model" if cfg.get("enable_symmetries", True) else "full-model (no symmetry)"
    st.caption(
        f"Approximate C3D8R elements for {sym_desc} "
        f"({est['in_plane']:,} in-plane x {int(cfg['thickness_seeds'])} thickness seeds)."
    )

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

    # ── Submit ───────────────────────────────────────────────────────────────
    submit_col, default_col, _ = st.columns([1.0, 1.25, 4.0])
    with default_col:
        if st.button("Set current as default", key="set_job_defaults"):
            default_payload = {k: st.session_state.get(k, defaults.get(k)) for k in DEFAULT_KEYS}
            default_payload.update(
                test_type=test_type,
                width=st.session_state.get("width", width),
                thickness=float(thickness),
                angle=float(angle),
                punch_diam=st.session_state.get("punch_diam", defaults["punch_diam"]),
                mesh_factor=float(mesh_factor),
                thickness_seeds=int(thickness_seeds),
                mass_scaling=float(mass_scaling),
                punch_speed=float(st.session_state.get("punch_speed", punch_speed)),
                punch_displacement=float(st.session_state.get("punch_displacement", punch_displacement)),
                fr_punch=float(st.session_state.get("fr_punch", 0.0)),
                pip_id=st.session_state.get("pip_id", defaults["pip_id"]),
                enable_symmetries=bool(enable_symmetries),
                bm_mesh_manual=bool(bm_mesh_manual),
                bm_mesh_tag=str(bm_mesh_tag),
                solver_cpus=int(solver_cpus),
                abaqus_memory_percent=int(abaqus_memory_percent),
                slurm_mem_per_cpu_gb=float(slurm_mem_per_cpu_gb),
                slurm_time_hours=int(slurm_time_hours),
            )
            _save_user_job_defaults(default_payload)
            st.success("Saved as default for future app runs.")

    with submit_col:
        euler_verified = _euler_access_verified()
        submit_clicked = st.button(
            "Submit",
            type="primary",
            disabled=not euler_verified,
            help=(
                "Verify Euler access from the account menu first."
                if not euler_verified else
                "Submit this job to Euler."
            ),
        )
    if not _euler_access_verified():
        st.caption("Submit is disabled until Euler access is verified from the account menu.")

    if submit_clicked:
        normal_login = _current_ssh_auth_mode() == SSH_AUTH_NORMAL
        with st.spinner("Submitting..."):
            if normal_login:
                log_dir = os.path.join(PROJECT_DIR, ".streamlit", "logs")
                os.makedirs(log_dir, exist_ok=True)
                submit_log = os.path.join(log_dir, f"submit_{int(time.time())}.log")
                with open(submit_log, "w", encoding="utf-8") as log_fh:
                    result = subprocess.run(
                        cmd,
                        env=build_env(cfg),
                        stdout=log_fh,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
            else:
                submit_log = None
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=build_env(cfg),
                )

        if result.returncode == 0:
            st.success("Submitted")
            if normal_login:
                st.caption(f"Submission output was written to `{submit_log}`.")
            else:
                st.code(result.stdout)
        else:
            if normal_login:
                st.error(f"Submit failed. Check `{submit_log}`.")
            else:
                st.error(result.stderr or "Submit failed.")


# ══════════════════════════════════════════════════════════════════════════════
# Job Status
# ══════════════════════════════════════════════════════════════════════════════
def _page_job_status():

    st.subheader("Euler Queue")
    if not _euler_access_verified():
        st.info("Verify Euler access from the account menu before fetching the queue.")
        return

    user = _current_user()

    auto_refresh = st.checkbox("Auto-refresh (30s)", value=True)
    if auto_refresh:
        st_autorefresh(interval=30000, key="squeue_refresh")


    if user:
        with st.spinner("Fetching queue..."):
            try:
                result = _run_ssh_command(
                    _ssh_command(
                        f"{user}@{_current_host()}",
                        'squeue --me --format="%.18i %.10P %.60j %.8u %.2t %.10M %.10l %.6D %R" --noheader',
                        connect_timeout=8,
                    ),
                    timeout=_ssh_timeout(default_normal=30, default_key_only=30),
                )
            except subprocess.TimeoutExpired:
                st.error("Queue request timed out. Re-verify Euler access from the account menu.")
                return

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

                st.dataframe(styled_df, width="stretch", hide_index=True)

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
                            data = _fetch_progress(user, _current_host(), sta_rows)
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
                            # Solver job is running but Abaqus hasn't written a
                            # .sta increment table yet — it's still compiling the
                            # VUMAT / packaging the input (pre-solve).  Show a
                            # placeholder so the row isn't silently blank, which
                            # otherwise looks like the panel is broken.
                            st.write(f"**{jn}**  `{slurm_time}` elapsed")
                            st.caption("packaging / pre-solve… (no .sta yet)")
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
            st.error(result.stderr or "Could not fetch the Euler queue. Re-verify Euler access from the account menu.")
# ══════════════════════════════════════════════════════════════════════════════
# Results
# ══════════════════════════════════════════════════════════════════════════════
def _page_results():

    # Deep-linking: restore view/job/panel from the URL once per session, so a
    # copied link (or an app restart with the same URL) reopens the same spot.
    if not st.session_state.get("_results_qp_restored"):
        st.session_state["_results_qp_restored"] = True
        _qp = st.query_params
        if _qp.get("view"):
            view = _qp["view"]
            st.session_state["results_view_mode"] = "FLD" if view == "FLC" else view
        if _qp.get("job"):
            st.session_state["results_single_job"] = _qp["job"]
        if _qp.get("panel"):
            st.session_state["results_panel_single"] = _qp["panel"]

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

    def _vh_fit_start_time(t_start, t_fit_end):
        if VH_FIT_WINDOW_SECONDS > 0.0:
            return max(float(t_start), float(t_fit_end) - VH_FIT_WINDOW_SECONDS)
        return float(t_start) + (1.0 - VH_FIT_WINDOW_FRAC) * (float(t_fit_end) - float(t_start))

    def _vh_unstable_fit_start_time(t_start, t_fit_end):
        if VH_UNSTABLE_FIT_WINDOW_SECONDS > 0.0:
            return max(float(t_start), float(t_fit_end) - VH_UNSTABLE_FIT_WINDOW_SECONDS)
        return _vh_fit_start_time(t_start, t_fit_end)

    def _vh_fit_window_label():
        if VH_FIT_WINDOW_SECONDS > 0.0:
            if VH_UNSTABLE_TAIL_POINTS > 0:
                return "Stable %.3g s, unstable last %d points" % (
                    VH_FIT_WINDOW_SECONDS,
                    VH_UNSTABLE_TAIL_POINTS,
                )
            return "Stable %.3g s, unstable %.3g s" % (
                VH_FIT_WINDOW_SECONDS,
                VH_UNSTABLE_FIT_WINDOW_SECONDS,
            )
        return "Last %.0f%% of pre-fracture signal" % (VH_FIT_WINDOW_FRAC * 100.0)

    def _dic_instable_index(t_values, t_cross):
        if not math.isfinite(t_cross):
            return None
        upper = next((idx for idx, value in enumerate(t_values) if value > t_cross), None)
        if upper is None or upper <= 0:
            return None
        dt = t_values[upper] - t_values[upper - 1]
        if dt <= 0:
            return None
        threshold = t_cross + 0.5 * dt
        index = None
        for idx, value in enumerate(t_values):
            if value < threshold:
                index = idx
        if index is None or index <= 0:
            return None
        return index

    def _volk_hora_fit(t, rate, fit_end_time=None):
        t_fit_end = t[-1] if fit_end_time is None else float(fit_end_time)
        t_min_fit = _vh_fit_start_time(t[0], t_fit_end)
        stable_indices = [
            i for i in range(1, len(t) - 1)
            if t[i] >= t_min_fit and t[i] <= t_fit_end
        ]
        if VH_UNSTABLE_TAIL_POINTS > 0:
            unstable_indices = list(range(1, len(t) - 1))[-VH_UNSTABLE_TAIL_POINTS:]
        else:
            t_min_unstable = _vh_unstable_fit_start_time(t[0], t_fit_end)
            unstable_indices = [
                i for i in range(1, len(t) - 1)
                if t[i] >= t_min_unstable and t[i] <= t_fit_end
            ]
        if len(stable_indices) <= VH_MIN_STABLE_POINTS or len(unstable_indices) < VH_MIN_UNSTABLE_POINTS:
            return None

        xs = [t[i] for i in stable_indices]
        ys = [rate[i] for i in stable_indices]
        xu = [t[i] for i in unstable_indices]
        yu = [rate[i] for i in unstable_indices]
        ns = len(xs)
        nu = len(xu)
        min_stable = VH_MIN_STABLE_POINTS
        min_unstable = VH_MIN_UNSTABLE_POINTS
        if ns <= min_stable or nu < min_unstable:
            return None

        best_stable = None
        for count in range(min_stable, ns):
            fit = _line_fit(xs[:count], ys[:count])
            if fit is None:
                continue
            score = fit[2] * float(count) / float(max(count - 1, 1))
            if best_stable is None or score < best_stable["mse"]:
                best_stable = {
                    "count": count,
                    "slope": fit[0],
                    "intercept": fit[1],
                    "mse": score,
                }

        best_unstable = None
        if VH_UNSTABLE_TAIL_POINTS > 0:
            unstable_candidates = [(0, nu)]
        else:
            unstable_candidates = [(start, nu - start) for start in range(1, nu - min_unstable + 1)]
        for start, count in unstable_candidates:
            fit = _line_fit(xu[start:], yu[start:])
            if fit is None:
                continue
            score = fit[2]
            if best_unstable is None or score < best_unstable["mse"]:
                best_unstable = {
                    "count": count,
                    "slope": fit[0],
                    "intercept": fit[1],
                    "mse": score,
                }

        if best_stable is None or best_unstable is None:
            return None

        denom = best_stable["slope"] - best_unstable["slope"]
        if abs(denom) < 1e-20:
            return None

        t_cross = (best_unstable["intercept"] - best_stable["intercept"]) / denom
        kcrit_pos = _dic_instable_index(t, t_cross)
        if kcrit_pos is None or kcrit_pos <= 0:
            return None
        k_stable = kcrit_pos - 1

        return {
            "t_fit_start": xs[0],
            "t_fit_end": t_fit_end,
            "t_cross": t_cross,
            "y_cross": best_stable["slope"] * t_cross + best_stable["intercept"],
            "kcrit": kcrit_pos,
            "kstable": k_stable,
            "stable": best_stable,
            "unstable": best_unstable,
            "stable_range": (xs[0], xs[best_stable["count"] - 1]),
            "unstable_range": (xu[nu - best_unstable["count"]], xu[-1]),
        }

    def _strip_plot_descriptions(fig):
        fig.update_layout(annotations=[])
        return fig

    def _plotly_chart(fig, *args, **kwargs):
        kwargs.setdefault("theme", None)
        st.plotly_chart(_strip_plot_descriptions(fig), *args, **kwargs)

    def _figure_memo(name, job_dir, files, builder, params=()):
        """Session-scoped memo for built figures.

        Keyed by the source-file mtimes and the active theme, so a re-synced
        CSV or a theme switch rebuilds the figure while plain reruns reuse it.
        """
        sig = []
        for fname in files:
            fp = _resolve_job_file(job_dir, fname)
            try:
                sig.append((fname, os.path.getmtime(fp)))
            except OSError:
                sig.append((fname, None))
        memo = st.session_state.setdefault("_results_fig_memo", {})
        key = (
            name,
            os.path.abspath(job_dir),
            tuple(sig),
            _plot_theme()["base"],
            tuple(params),
        )
        if key not in memo:
            if len(memo) >= 48:
                memo.clear()
            memo[key] = builder()
        return memo[key]

    def _volk_hora_rate_fig(job_dir, smoothing_window=20, override_stable_range=None, override_unstable_range=None):
        fp = os.path.join(job_dir, "strain_path.csv")
        if not os.path.exists(fp):
            return None, "strain_path.csv not found", None

        df = _load_csv(fp)
        required = {"time_s", "eps1_major", "eps2_minor"}
        if not required <= set(df.columns):
            return None, "strain_path.csv is missing time_s / eps1_major / eps2_minor", None

        if "fracture_type" in df.columns:
            fracture_types = {
                str(v).strip().lower()
                for v in df["fracture_type"].dropna().unique()
                if str(v).strip()
            }
            if fracture_types and "dome" not in fracture_types:
                return None, "Volk-Hora rate is only shown for dome-zone fracture runs", None

        cols = ["time_s", "eps1_major", "eps2_minor"]
        if "thinning_rate" in df.columns:
            cols.append("thinning_rate")
        if "EQPS" in df.columns:
            cols.append("EQPS")
        if "D" in df.columns:
            cols.append("D")
        data = df[cols].apply(pd.to_numeric, errors="coerce")
        data = data.dropna(subset=["time_s", "eps1_major", "eps2_minor"])
        data = data.drop_duplicates(subset=["time_s"]).sort_values("time_s")
        if len(data) < 3:
            return None, "not enough pre-fracture frames", None

        t = data["time_s"].tolist()
        if "thinning_rate" in data.columns and data["thinning_rate"].notna().all():
            rate = data["thinning_rate"].tolist()
        else:
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
        if override_stable_range is not None and override_unstable_range is not None:
            ts0, ts1 = override_stable_range
            tu0, tu1 = override_unstable_range
            _si_idx = [i for i in range(len(t)) if ts0 <= t[i] <= ts1]
            _ui_idx = [i for i in range(len(t)) if tu0 <= t[i] <= tu1]
            fit = None
            if len(_si_idx) >= VH_MIN_STABLE_POINTS and len(_ui_idx) >= VH_MIN_UNSTABLE_POINTS:
                _xs = [t[i] for i in _si_idx]; _ys = [rate_for_fit[i] for i in _si_idx]
                _xu = [t[i] for i in _ui_idx]; _yu = [rate_for_fit[i] for i in _ui_idx]
                _sf = _line_fit(_xs, _ys)
                _uf = _line_fit(_xu, _yu)
                if _sf and _uf:
                    _ss, _si, _ = _sf
                    _us, _ui, _ = _uf
                    _dn = _ss - _us
                    if abs(_dn) >= 1e-20:
                        _tc = (_ui - _si) / _dn
                        _kc = _dic_instable_index(t, _tc)
                        if _kc and _kc > 0:
                            fit = {
                                "t_fit_start": min(ts0, tu0), "t_fit_end": max(ts1, tu1),
                                "t_cross": _tc, "y_cross": _ss * _tc + _si,
                                "kcrit": _kc, "kstable": _kc - 1,
                                "stable":   {"slope": _ss, "intercept": _si, "count": len(_si_idx), "mse": 0},
                                "unstable": {"slope": _us, "intercept": _ui, "count": len(_ui_idx), "mse": 0},
                                "stable_range": (ts0, ts1),
                                "unstable_range": (tu0, tu1),
                            }
        else:
            fit = _volk_hora_fit(t, rate_for_fit)
        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        point_color = "#2563eb"
        stable_color = "seagreen"
        unstable_color = "firebrick"
        axis_color = plot_style["axis"]
        grid_color = plot_style["grid"]
        text = axis_color
        template = theme["template"]

        y_min = min(rate_for_fit) if rate_for_fit else 0.0
        y_max = max(rate_for_fit) if rate_for_fit else 0.0
        y_pad = max(0.01, 0.08 * (y_max - min(0.0, y_min) + 1e-9))
        y_range = [min(0.0, y_min) - y_pad, y_max + y_pad]

        if fit is not None:
            x_fit0 = float(fit["t_fit_start"])
            x_fit1 = float(fit["t_fit_end"])
        else:
            x_fit0 = t[0]
            x_fit1 = t[-1]
        if x_fit1 <= x_fit0:
            x_fit1 = x_fit0 + 1e-3

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Volk-Hora", "Volk-Hora - last 2 seconds"),
            horizontal_spacing=0.08,
        )

        signal_name = f"smoothed signal ({smoothing_window} pts)"
        fig.add_trace(go.Scatter(
            x=t,
            y=rate_for_fit,
            mode="lines+markers",
            name=signal_name,
            line=dict(width=2.5, color=point_color),
            marker=dict(size=5, color=point_color),
            hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=t,
            y=rate_for_fit,
            mode="lines+markers",
            name=signal_name,
            showlegend=False,
            line=dict(width=2.5, color=point_color),
            marker=dict(size=5, color=point_color),
            hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra></extra>",
        ), row=1, col=2)

        if fit is not None:
            stable = fit["stable"]
            unstable = fit["unstable"]
            left_x = [t[0], t[-1]]
            right_x = [x_fit0, x_fit1]
            stable_left = [stable["slope"] * tv + stable["intercept"] for tv in left_x]
            unstable_left = [unstable["slope"] * tv + unstable["intercept"] for tv in left_x]

            stable_right_x = right_x
            unstable_right_x = right_x
            stable_right = [stable["slope"] * tv + stable["intercept"] for tv in stable_right_x]
            unstable_right = [unstable["slope"] * tv + unstable["intercept"] for tv in unstable_right_x]

            # shaded windows (right subplot only to avoid noise on overview)
            if "stable_range" in fit:
                fig.add_vrect(x0=fit["stable_range"][0], x1=fit["stable_range"][1],
                              fillcolor=stable_color, opacity=0.10, line_width=0, row=1, col=2)
                fig.add_vrect(x0=fit["unstable_range"][0], x1=fit["unstable_range"][1],
                              fillcolor=unstable_color, opacity=0.10, line_width=0, row=1, col=2)

            fig.add_trace(go.Scatter(
                x=left_x, y=stable_left, mode="lines", name="stable fit",
                line=dict(width=2.5, color=stable_color, dash="dashdot"),
                hoverinfo="skip",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=left_x, y=unstable_left, mode="lines", name="unstable fit",
                line=dict(width=2.5, color=unstable_color, dash="dashdot"),
                hoverinfo="skip",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=stable_right_x, y=stable_right, mode="lines", name="stable fit",
                line=dict(width=2.5, color=stable_color, dash="dashdot"),
                hoverinfo="skip",
                showlegend=False,
            ), row=1, col=2)
            fig.add_trace(go.Scatter(
                x=unstable_right_x, y=unstable_right, mode="lines", name="unstable fit",
                line=dict(width=2.5, color=unstable_color, dash="dashdot"),
                hoverinfo="skip",
                showlegend=False,
            ), row=1, col=2)

            for col in (1, 2):
                fig.add_trace(go.Scatter(
                    x=[fit["t_cross"]],
                    y=[fit["y_cross"]],
                    mode="markers",
                    name="intersection" if col == 1 else None,
                    showlegend=(col == 1),
                    marker=dict(size=11, color="#facc15", symbol="x", line=dict(width=2, color=axis_color)),
                    hovertemplate="t=%{x:.4f} s<br>rate=%{y:.5g} 1/s<extra>intersection</extra>",
                ), row=1, col=col)

            e1_vh = float(data.iloc[fit["kstable"]]["eps1_major"])
            e2_vh = float(data.iloc[fit["kstable"]]["eps2_minor"])
            fig.add_annotation(
                xref="x2 domain",
                yref="y2 domain",
                x=0.03,
                y=0.99,
                text="e1 = %.4f&nbsp;&nbsp; e2 = %.4f&nbsp;&nbsp; t_necking = %.4f s" % (
                    e1_vh,
                    e2_vh,
                    t[fit["kstable"]],
                ),
                showarrow=False,
                align="left",
                font=dict(family="monospace", size=11, color=text),
                bgcolor=plot_style["annotation_bg"],
                borderpad=4,
                row=1,
                col=2,
            )
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

        fig.update_xaxes(title_text="Time [s]", range=[t[0], t[-1]], row=1, col=1)
        fig.update_xaxes(title_text="Time [s]", range=[x_fit0, x_fit1], row=1, col=2)
        fig.update_yaxes(title_text="Thinning strain rate d(ε₁+ε₂)/dt [1/s]", range=y_range, row=1, col=1)
        fig.update_yaxes(range=y_range, row=1, col=2)
        for col in (1, 2):
            fig.update_xaxes(
                row=1, col=col,
                title_font=dict(color=axis_color),
                tickfont=dict(color=axis_color),
                linecolor=axis_color,
                mirror=True,
                gridcolor=grid_color,
                zerolinecolor=grid_color,
            )
            fig.update_yaxes(
                row=1, col=col,
                title_font=dict(color=axis_color),
                tickfont=dict(color=axis_color),
                linecolor=axis_color,
                mirror=True,
                gridcolor=grid_color,
                zerolinecolor=grid_color,
            )
        fig.update_layout(
            title=dict(text="Volk-Hora", font=dict(color=axis_color)),
            template=template,
            height=520,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=0.98,
                xanchor="left",
                x=0.01,
                bgcolor=plot_style["annotation_bg"],
                bordercolor=axis_color,
                borderwidth=1,
                font=dict(color=axis_color),
            ),
            margin=dict(t=85, r=30, b=55, l=55),
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=axis_color),
            hoverlabel=dict(bgcolor=plot_style["hover_bg"], font=dict(color=axis_color)),
        )
        return _strip_plot_descriptions(fig), None, {
            "t": t, "rate": rate_for_fit, "data": data, "fit": fit,
        }

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
        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        axis_color = plot_style["axis"]
        grid_color = plot_style["grid"]
        text = axis_color
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

        k_eval = _vh_eval_index(len(times))
        rates_eval = sorted([path_data[p]["rate"][k_eval] for p in admissible], reverse=True)
        top_n = min(VH_SEED_COUNT, len(rates_eval))
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
                font=dict(family="monospace", size=11, color=text),
                bgcolor=plot_style["annotation_bg"],
                borderpad=4,
            )
        else:
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.98,
                text="Fit unavailable for connected V&H zone",
                showarrow=False,
                font=dict(color="firebrick"),
            )

        fig.update_xaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_yaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_layout(
            title=dict(text=title, font=dict(color=axis_color)),
            xaxis_title="Time [s]",
            yaxis_title="Mean thinning rate d(ε₁+ε₂)/dt [1/s]",
            template=theme["template"],
            height=450,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1.0, title=None,
                itemclick="toggleothers",
                bgcolor=plot_style["transparent"], bordercolor=plot_style["transparent"], borderwidth=0,
                font=dict(color=axis_color),
            ),
            margin=dict(t=70, r=20),
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=axis_color),
            hoverlabel=dict(bgcolor=plot_style["hover_bg"], font=dict(color=axis_color)),
        )
        return _strip_plot_descriptions(fig), None

    def _volk_hora_fracture_neighborhood_fig(job_dir, smoothing_window=20):
        csv_path = os.path.join(job_dir, "strain_neighborhood.csv")
        if not os.path.exists(csv_path):
            return None, "strain_neighborhood.csv not found"
        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        axis_color = plot_style["axis"]
        grid_color = plot_style["grid"]
        text = axis_color
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
                font=dict(family="monospace", size=11, color=text),
                bgcolor=plot_style["annotation_bg"],
                borderpad=4,
            )
        else:
            fig.add_annotation(
                xref="paper", yref="paper", x=0.01, y=0.98,
                text="Fit unavailable for fracture-cluster neighborhood",
                showarrow=False,
                font=dict(color="firebrick"),
            )

        fig.update_xaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_yaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_layout(
            title=dict(text="Volk-Hora Signal from Fracture-Element Cluster Neighborhood", font=dict(color=axis_color)),
            xaxis_title="Time [s]",
            yaxis_title="Mean thinning rate d(ε₁+ε₂)/dt [1/s]",
            template=theme["template"],
            height=450,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1.0, title=None,
                itemclick="toggleothers",
                bgcolor=plot_style["transparent"], bordercolor=plot_style["transparent"], borderwidth=0,
                font=dict(color=axis_color),
            ),
            margin=dict(t=70, r=20),
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=axis_color),
            hoverlabel=dict(bgcolor=plot_style["hover_bg"], font=dict(color=axis_color)),
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

            k_eval = _vh_eval_index(len(times))
            rates_eval = sorted([v["rate"][k_eval] for v in path_data.values()], reverse=True)
            if not rates_eval:
                return None, "no thinning-rate values available"
            top_n = min(VH_SEED_COUNT, len(rates_eval))
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

            theme = _plot_theme()
            plot_style = _streamlit_plot_style(theme)
            axis_color = plot_style["axis"]
            grid_color = plot_style["grid"]
            text = axis_color
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
                    font=dict(family="monospace", size=11, color=text),
                    bgcolor=plot_style["annotation_bg"],
                    borderpad=4,
                )
            else:
                fig.add_annotation(
                    xref="paper", yref="paper", x=0.01, y=0.98,
                    text="Fit unavailable for connected V&H zone",
                    showarrow=False,
                    font=dict(color="firebrick"),
                )

            fig.update_xaxes(
                title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
                linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
            )
            fig.update_yaxes(
                title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
                linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
            )
            fig.update_layout(
                title=dict(text="Volk-Hora Signal from Connected High-Thinning-Rate Zone", font=dict(color=axis_color)),
                xaxis_title="Time [s]",
                yaxis_title="Mean thinning rate d(ε₁+ε₂)/dt [1/s]",
                template=theme["template"],
                height=450,
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1.0, title=None,
                    itemclick="toggleothers",
                    bgcolor=plot_style["transparent"], bordercolor=plot_style["transparent"], borderwidth=0,
                    font=dict(color=axis_color),
                ),
                margin=dict(t=70, r=20),
                paper_bgcolor=plot_style["transparent"],
                plot_bgcolor=plot_style["transparent"],
                font=dict(color=axis_color),
                hoverlabel=dict(bgcolor=plot_style["hover_bg"], font=dict(color=axis_color)),
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

        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        axis_color = plot_style["axis"]
        grid_color = plot_style["grid"]
        text = axis_color
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
                font=dict(family="monospace", size=11, color=text),
                bgcolor=plot_style["annotation_bg"],
                borderpad=4,
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

        fig.update_xaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_yaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_layout(
            title=dict(text="Volk-Hora Signal from " + VH_SEED_LABEL + " Fracture-Neighborhood Median", font=dict(color=axis_color)),
            xaxis_title="Time [s]",
            yaxis_title="d(ε₁+ε₂)/dt [1/s]",
            template=theme["template"],
            height=450,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1.0,
                title=None,
                itemclick="toggleothers",
                bgcolor=plot_style["transparent"], bordercolor=plot_style["transparent"], borderwidth=0,
                font=dict(color=axis_color),
            ),
            margin=dict(t=70, r=20),
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=axis_color),
            hoverlabel=dict(bgcolor=plot_style["hover_bg"], font=dict(color=axis_color)),
        )
        return _strip_plot_descriptions(fig), None

    def _volk_hora_path(job_dir, smoothing_window=1, constrained=True):
        path_csv = os.path.join(job_dir, "strain_path.csv")
        if os.path.exists(path_csv):
            df = _load_csv(path_csv)
            required = {"time_s", "eps1_major", "eps2_minor"}
            if required <= set(df.columns):
                cols = ["time_s", "eps1_major", "eps2_minor"]
                if "thinning_rate" in df.columns:
                    cols.append("thinning_rate")
                if "selected_n" in df.columns:
                    cols.append("selected_n")
                data = df[cols].apply(pd.to_numeric, errors="coerce")
                data = data.dropna(subset=["time_s", "eps1_major", "eps2_minor"])
                data = data.drop_duplicates(subset=["time_s"]).sort_values("time_s")
                if len(data) >= 3:
                    times = data["time_s"].tolist()
                    e1 = data["eps1_major"].tolist()
                    e2 = data["eps2_minor"].tolist()
                    if "thinning_rate" in data.columns and data["thinning_rate"].notna().all():
                        rate = data["thinning_rate"].tolist()
                    else:
                        strain_sum = (data["eps1_major"] + data["eps2_minor"]).tolist()
                        rate = [0.0] * len(times)
                        for i in range(len(times)):
                            if i == 0:
                                dt = times[1] - times[0]
                                rate[i] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
                            elif i == len(times) - 1:
                                dt = times[i] - times[i - 1]
                                rate[i] = (strain_sum[i] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                            else:
                                dt = times[i + 1] - times[i - 1]
                                rate[i] = (strain_sum[i + 1] - strain_sum[i - 1]) / dt if dt > 1e-12 else 0.0
                    fit = _volk_hora_fit(times, _moving_average(rate, smoothing_window))
                    k_stable = fit["kstable"] if fit is not None else len(times) - 1
                    zone_n = int(data["selected_n"].dropna().iloc[-1]) if "selected_n" in data.columns and data["selected_n"].notna().any() else 1
                    return {
                        "time": times,
                        "e1": e1,
                        "e2": e2,
                        "rate": rate,
                        "end_e1": float(e1[k_stable]),
                        "end_e2": float(e2[k_stable]),
                        "end_time": float(times[k_stable]),
                        "zone_n": zone_n,
                        "constraint_n": zone_n,
                        "constrained": bool(constrained),
                        "top_n": VH_SEED_COUNT,
                        "alpha": VH_ALPHA,
                    }

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
            admissible &= {
                pid for pid in pids
                if min(
                    math.hypot(centroids[pid][0] - ax, centroids[pid][1] - ay)
                    for ax, ay in anchor_points
                ) <= VH_FRACTURE_RADIUS_MM
            }
            if not admissible:
                return None

        k_eval = _vh_eval_index(len(times))
        rates_eval = sorted([path_data[p]["rate"][k_eval] for p in admissible], reverse=True)
        top_n = min(VH_SEED_COUNT, len(rates_eval))
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


    def _volk_hora_dome_rate_fig(job_dir, smoothing_window=20, override_stable_range=None, override_unstable_range=None):
        return _volk_hora_rate_fig(job_dir, smoothing_window=smoothing_window,
                                   override_stable_range=override_stable_range,
                                   override_unstable_range=override_unstable_range)

    def _volk_hora_zone_location_fig(csv_path, title, prefer_fracture_center,
                                     weight_by_area=False, anchor_points=None,
                                     anchor_name=None, anchor_radius=None,
                                     allowed_labels=None, anchor_hops=None):
        if not os.path.exists(csv_path):
            return None, os.path.basename(csv_path) + " not found"
        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        axis_color = plot_style["axis"]
        grid_color = plot_style["grid"]
        text = axis_color
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

        k_eval = _vh_eval_index(len(times))
        rates_eval = sorted([path_data[p]["rate"][k_eval] for p in admissible], reverse=True)
        top_n = min(VH_SEED_COUNT, len(rates_eval))
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
        top_seed_set = set(sorted(admissible, key=lambda p: path_data[p]["rate"][k_eval], reverse=True)[:top_n])
        hot_list = sorted(hot, key=lambda p: path_data[p]["rate"][k_eval], reverse=True)
        top_seed_list = sorted(top_seed_set, key=lambda p: path_data[p]["rate"][k_eval], reverse=True)
        admissible_list = sorted(admissible - set(hot), key=lambda p: path_data[p]["rate"][k_eval], reverse=True)

        fig = go.Figure()
        outline_xs = []
        outline_ys = []
        outline_fp = os.path.join(os.path.dirname(csv_path), "specimen_outline.csv")
        if os.path.exists(outline_fp):
            outline = _load_csv(outline_fp)
            needed = {"x1", "y1", "x2", "y2"}
            if needed <= set(outline.columns):
                outline = outline.copy()
                for col in needed:
                    outline[col] = pd.to_numeric(outline[col], errors="coerce")
                outline = outline.dropna(subset=list(needed))
                for _, row in outline.iterrows():
                    outline_xs.extend([row["x1"], row["x2"], None])
                    outline_ys.extend([row["y1"], row["y2"], None])
                if len(outline) < 8:
                    outline_xs = []
                    outline_ys = []
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
        if top_seed_list:
            fig.add_trace(go.Scattergl(
                x=[centroids[p][0] for p in top_seed_list],
                y=[centroids[p][1] for p in top_seed_list],
                mode="markers",
                name=VH_SEED_LABEL + " max set",
                marker=dict(size=10, color="#2563eb", symbol="diamond", line=dict(width=1, color="white")),
                customdata=[path_data[p]["rate"][k_eval] for p in top_seed_list],
                hovertemplate=(
                    "x=%{x:.3f} mm<br>y=%{y:.3f} mm<br>rate=%{customdata:.5g}"
                    "<extra>" + VH_SEED_LABEL + " max set</extra>"
                ),
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
        if outline_xs and outline_ys:
            fig.add_trace(go.Scatter(
                x=outline_xs,
                y=outline_ys,
                mode="lines",
                name="specimen contour",
                line=dict(color=axis_color, width=3),
                hoverinfo="skip",
            ))

        fig.update_xaxes(
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_yaxes(
            scaleanchor="x", scaleratio=1,
            title_font=dict(color=axis_color), tickfont=dict(color=axis_color),
            linecolor=axis_color, mirror=True, gridcolor=grid_color, zerolinecolor=grid_color,
        )
        fig.update_layout(
            title=dict(text=title, font=dict(color=axis_color)),
            xaxis_title="X [mm]",
            yaxis_title="Y [mm]",
            template=theme["template"],
            height=430,
            hovermode="closest",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.18,
                xanchor="center",
                x=0.5,
                title=None,
                bgcolor=plot_style["transparent"], bordercolor=plot_style["transparent"], borderwidth=0,
                font=dict(color=axis_color),
            ),
            margin=dict(t=65, r=20, b=95),
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=axis_color),
            hoverlabel=dict(bgcolor=plot_style["hover_bg"], font=dict(color=axis_color)),
        )
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
            font=dict(family="monospace", size=11, color=text),
            bgcolor=plot_style["annotation_bg"],
            borderpad=4,
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

        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        path_col = "rgba(255,255,255,0.20)" if theme["base"] == "dark" else "rgba(0,0,0,0.15)"

        fig = go.Figure()
        path_groups = list(data.groupby("path_id", sort=False))
        n_paths = len(path_groups)
        # Display a REPRESENTATIVE sample of the zone, not the top-ranked cells.
        # path_groups is ordered by selection_rank (highest thinning rate first);
        # taking the top-N biases the grey cloud to the most-necked cells, so the
        # cluster median / V&H mean (computed over ALL cells) sit below it.  An
        # even stride across the rank order spans the full distribution, so the
        # representative lines land inside the grey cloud.
        if n_paths <= CLUSTER_PATH_DISPLAY_MAX:
            display_paths = path_groups
        else:
            stride = (n_paths + CLUSTER_PATH_DISPLAY_MAX - 1) // CLUSTER_PATH_DISPLAY_MAX
            display_paths = path_groups[::stride]
        for path_id, grp in display_paths:
            rank = int(grp["selection_rank"].iloc[0])
            fig.add_trace(go.Scatter(
                x=grp["eps2_minor"],
                y=grp["eps1_major"],
                mode="lines",
                name=path_id,
                legendgroup="cluster",
                showlegend=False,
                line=dict(color=path_col, width=1),
                hovertemplate=(
                    path_id + "<br>rank=" + str(rank) +
                "<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>" + VH_SEED_LABEL + " cluster</extra>"
                ),
            ))

        grouped = data.groupby("time_s", dropna=True) if "time_s" in data.columns else None
        if grouped is not None and data["time_s"].notna().any():
            med = grouped[["eps1_major", "eps2_minor"]].median().reset_index()
            med = med.sort_values("time_s")
            fig.add_trace(go.Scatter(
                x=med["eps2_minor"],
                y=med["eps1_major"],
                mode="lines",
                name="Cluster median",
                line=dict(color="#FF0000", width=2.5),
                hovertemplate="ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>Cluster median</extra>",
            ))

        n_display = len(display_paths)
        fig.update_xaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                         linecolor=plot_style["axis"], gridcolor=plot_style["grid"], zerolinecolor=plot_style["grid"])
        fig.update_yaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                         linecolor=plot_style["axis"], gridcolor=plot_style["grid"], zerolinecolor=plot_style["grid"])
        subtitle = "%d paths · %d shown · cluster median" % (n_paths, n_display)
        fig.update_layout(
            title=dict(
                text="Strain Path<br><sup>%s</sup>" % subtitle,
                font=dict(size=16),
            ),
            xaxis_title="ε₂ minor strain (-)",
            yaxis_title="ε₁ major strain (-)",
            template=theme["template"],
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
            margin=dict(t=95, r=20),
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=plot_style["axis"]),
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
            return None, "V&H representative path unavailable; rerun postprocessing to generate strain_path.csv"
        vh_col = "#0072BD"   # MATLAB blue
        fig.add_trace(go.Scatter(
            x=vh["e2"],
            y=vh["e1"],
            mode="lines",
            name="V&H zone average",
            line=dict(color=vh_col, width=2.5),
            hovertemplate="ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra>V&H zone average</extra>",
        ))
        fig.update_layout(
            title=dict(
                text="Strain Path<br><sup>cluster median (red) · V&H zone average (blue)</sup>",
                font=dict(size=16),
            ),
        )
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

        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
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
                outline = outline.copy()
                for col in needed:
                    outline[col] = pd.to_numeric(outline[col], errors="coerce")
                outline = outline.dropna(subset=list(needed))
                if len(outline) >= 8:
                    # Chain unsorted boundary edges into a continuous polygon
                    edges = [
                        ((row["x1"], row["y1"]), (row["x2"], row["y2"]))
                        for _, row in outline.iterrows()
                    ]
                    # Build adjacency: endpoint → list of edge indices
                    def _pt_key(p, tol=1e-4):
                        return (round(p[0] / tol), round(p[1] / tol))
                    adj = {}
                    for ei, (a, b) in enumerate(edges):
                        adj.setdefault(_pt_key(a), []).append(ei)
                        adj.setdefault(_pt_key(b), []).append(ei)
                    used = [False] * len(edges)
                    chains = []
                    for start in range(len(edges)):
                        if used[start]:
                            continue
                        chain = [edges[start][0], edges[start][1]]
                        used[start] = True
                        while True:
                            tip = chain[-1]
                            tip_key = _pt_key(tip)
                            found = False
                            for ei in adj.get(tip_key, []):
                                if used[ei]:
                                    continue
                                a, b = edges[ei]
                                next_pt = b if _pt_key(a) == tip_key else a
                                chain.append(next_pt)
                                used[ei] = True
                                found = True
                                break
                            if not found:
                                break
                        chains.append(chain)
                    # Keep only the outer specimen contour: interior partition
                    # or symmetry edges form shorter chains with smaller extent.
                    def _chain_extent(chain):
                        cxs = [p[0] for p in chain]
                        cys = [p[1] for p in chain]
                        return (max(cxs) - min(cxs)) * (max(cys) - min(cys))

                    outer = max(chains, key=_chain_extent) if chains else []
                    xs = [p[0] for p in outer]
                    ys = [p[1] for p in outer]
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
        band_face_count = 0
        threshold_face_count = 0
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
                band_face_count = int(faces[
                    role_text == "band"
                ]["element_label"].nunique())
                threshold_face_count = int(faces[
                    role_text == "threshold_zone"
                ]["element_label"].nunique())
                # Draw one centroid dot per element, one trace per role, from
                # the band (bottom) to the fracture line (top).
                cent = (
                    faces[~role_text.isin(["first_deleted"])]
                    .groupby(["role", "element_label"], sort=False)[["x", "y"]]
                    .mean()
                    .reset_index()
                )
                cent["role"] = cent["role"].astype(str)
                role_styles = [
                    ("band", "3 mm analysis band", "#94a3b8", 5),
                    ("threshold_zone", "threshold zone", "#facc15", 6),
                    ("cluster", "V&H zone cells", "#2563eb", 7),
                    ("fracture_deleted", "crack line", "#dc2626", 7),
                    ("crack_deleted", "crack line", "#dc2626", 7),
                ]
                shown = set()
                for role_s, name, color, size in role_styles:
                    sub = cent[cent["role"] == role_s]
                    if sub.empty:
                        continue
                    _add_trace_both(go.Scatter(
                        x=sub["x"],
                        y=sub["y"],
                        mode="markers",
                        name=name,
                        legendgroup=name,
                        showlegend=name not in shown,
                        marker=dict(
                            size=size,
                            color=color,
                            line=dict(width=0.5, color="white"),
                        ),
                        customdata=sub[["element_label"]],
                        hovertemplate=(
                            "element=%{customdata[0]}<br>x=%{x:.3f} mm"
                            "<br>y=%{y:.3f} mm<extra>" + name + "</extra>"
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
                pass

        if center_xy is not None:
            x0, y0 = center_xy
            zoom_radius = 7.0
            fig.update_xaxes(range=[x0 - zoom_radius, x0 + zoom_radius], row=1, col=2)
            fig.update_yaxes(range=[y0 - zoom_radius, y0 + zoom_radius], row=1, col=2)

        fig.update_layout(
            title=VH_SEED_LABEL + " Zone Location",
            xaxis_title="X [mm]",
            yaxis_title="Y [mm]",
            template=theme["template"],
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
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=plot_style["axis"]),
        )
        for _r, _c in [(1, 1), (1, 2)]:
            fig.update_xaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"],
                             zerolinecolor=plot_style["grid"], row=_r, col=_c)
            fig.update_yaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"],
                             zerolinecolor=plot_style["grid"], row=_r, col=_c)
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
                "fracture=%d, band=%d, threshold=%d, selected=%d"
                % (fracture_face_count, band_face_count,
                   threshold_face_count, strain_face_count)
                if fracture_face_count else
                "selected cells=%d" % data_last["element_label"].nunique()
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
            theme = _plot_theme()
            plot_style = _streamlit_plot_style(theme)
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
            fig.update_xaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"], zerolinecolor=plot_style["grid"])
            fig.update_yaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"], zerolinecolor=plot_style["grid"])
            fig.update_layout(
                title=f"Punch Force–Displacement{title_suffix}",
                xaxis_title="Displacement [mm]",
                yaxis_title="Force [N]",
                template=theme["template"],
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
                paper_bgcolor=plot_style["transparent"],
                plot_bgcolor=plot_style["transparent"],
                font=dict(color=plot_style["axis"]),
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

        has_triax = "TRIAX" in g.columns
        panels = [
            ("Strain ratio  β = ε₂/ε₁",      "β  [–]",         "beta",     "#ff7f0e", "β = ε₂/ε₁  (strain ratio)"),
        ]
        if has_triax:
            panels.append(("Stress triaxiality  η", "η  [–]", "TRIAX", "#e377c2", "η = σ_m / σ_eq  (triaxiality)"))

        n_rows = len(panels)
        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
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
        for _r in range(1, n_rows + 1):
            fig.update_xaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"],
                             zerolinecolor=plot_style["grid"], row=_r, col=1)
            fig.update_yaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"],
                             zerolinecolor=plot_style["grid"], row=_r, col=1)
        fig.update_layout(
            height=190 * n_rows,
            template=theme["template"],
            margin=dict(t=60),
            showlegend=False,
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=plot_style["axis"]),
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

            theme = _plot_theme()
            plot_style = _streamlit_plot_style(theme)
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
            fig.update_xaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"], zerolinecolor=plot_style["grid"])
            fig.update_yaxes(tickfont=dict(color=plot_style["axis"]), title_font=dict(color=plot_style["axis"]),
                             linecolor=plot_style["axis"], gridcolor=plot_style["grid"], zerolinecolor=plot_style["grid"])
            fig.update_layout(
                title="KE / IE — quasi-static check",
                xaxis_title=x_label,
                yaxis_title="ALLKE / ALLIE",
                template=theme["template"],
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            xanchor="right", x=1),
                paper_bgcolor=plot_style["transparent"],
                plot_bgcolor=plot_style["transparent"],
                font=dict(color=plot_style["axis"]),
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
            st.dataframe(df_fl, width="stretch", hide_index=True)

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
                    _tx_theme = _plot_theme()
                    _tx_ps = _streamlit_plot_style(_tx_theme)
                    fig_tx.update_xaxes(tickfont=dict(color=_tx_ps["axis"]), title_font=dict(color=_tx_ps["axis"]),
                                        linecolor=_tx_ps["axis"], gridcolor=_tx_ps["grid"], zerolinecolor=_tx_ps["grid"])
                    fig_tx.update_yaxes(tickfont=dict(color=_tx_ps["axis"]), title_font=dict(color=_tx_ps["axis"]),
                                        linecolor=_tx_ps["axis"], gridcolor=_tx_ps["grid"], zerolinecolor=_tx_ps["grid"])
                    fig_tx.update_layout(
                        title="Stress-state path: η vs EQPS",
                        xaxis_title="Equivalent plastic strain (EQPS)",
                        yaxis_title="Triaxiality η = σ_m / σ_eq",
                        template=_tx_theme["template"],
                        showlegend=False,
                        height=360,
                        paper_bgcolor=_tx_ps["transparent"],
                        plot_bgcolor=_tx_ps["transparent"],
                        font=dict(color=_tx_ps["axis"]),
                    )
                    _plotly_chart(fig_tx, width="stretch")

    def _job_strain_path(job_dir):
        for fname, c1, c2 in [
            ("strain_path.csv", "eps1_major", "eps2_minor"),
            ("elout.csv", "eps1_le", "eps2_le"),
        ]:
            fp = os.path.join(job_dir, fname)
            if not os.path.exists(fp):
                continue
            try:
                df = _load_csv(fp)
            except Exception:
                continue
            if c1 in df.columns and c2 in df.columns:
                return df[c1].tolist(), df[c2].tolist()
        return None, None

    def _strain_path_quick_fig(job_dir):
        e1_path, e2_path = _job_strain_path(job_dir)
        if not e1_path or not e2_path:
            return None, "strain_path.csv not found"
        theme = _plot_theme()
        plot_style = _streamlit_plot_style(theme)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=e2_path,
            y=e1_path,
            mode="lines",
            name="Strain path",
            line=dict(color="#0072BD", width=2.2),
            hovertemplate="ε₂=%{x:.4f}<br>ε₁=%{y:.4f}<extra></extra>",
        ))
        fig.update_xaxes(
            tickfont=dict(color=plot_style["axis"]),
            title_font=dict(color=plot_style["axis"]),
            linecolor=plot_style["axis"],
            gridcolor=plot_style["grid"],
            zerolinecolor=plot_style["grid"],
        )
        fig.update_yaxes(
            tickfont=dict(color=plot_style["axis"]),
            title_font=dict(color=plot_style["axis"]),
            linecolor=plot_style["axis"],
            gridcolor=plot_style["grid"],
            zerolinecolor=plot_style["grid"],
        )
        fig.update_layout(
            title="Strain Path",
            xaxis_title="ε₂ minor strain (-)",
            yaxis_title="ε₁ major strain (-)",
            template=theme["template"],
            height=470,
            paper_bgcolor=plot_style["transparent"],
            plot_bgcolor=plot_style["transparent"],
            font=dict(color=plot_style["axis"]),
        )
        fig.add_vline(x=0, line_width=0.6, line_dash="dot", line_color=plot_style["guide"])
        fig.add_hline(y=0, line_width=0.6, line_dash="dot", line_color=plot_style["guide"])
        return _strip_plot_descriptions(fig), None

    # ── Downloadable Matlab-style graph files ────────────────────────────────

    _MATLAB_COLORS = [
        "#0072BD", "#D95319", "#EDB120", "#7E2F8E",
        "#77AC30", "#4DBEEE", "#A2142F",
    ]

    def _safe_filename(name):
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("._")
        return cleaned or "plot"

    def _short_plot_label(label, max_len=64):
        label = str(label)
        return label if len(label) <= max_len else label[:max_len - 3] + "..."

    def _read_export_csv(job_dir, filenames, required=()):
        for fname in filenames:
            fp = _resolve_job_file(job_dir, fname)
            if not os.path.exists(fp):
                continue
            try:
                df = _load_csv(fp).copy()
            except Exception:
                continue
            if all(col in df.columns for col in required):
                return df, fname
        return None, None

    def _numeric_columns(df, columns):
        out = df.copy()
        for col in columns:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        return out

    def _new_export_figure(nrows=1, figsize=(6.9, 4.4), sharex=False):
        plt.rcParams.update({
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.edgecolor": "black",
            "axes.linewidth": 0.8,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 8,
            "savefig.facecolor": "white",
        })
        fig, axes = plt.subplots(nrows=nrows, ncols=1, figsize=figsize, sharex=sharex)
        fig.patch.set_facecolor("white")
        if nrows == 1:
            axes = [axes]
        return fig, axes

    def _style_export_axis(ax, xlabel=None, ylabel=None, title=None):
        ax.set_facecolor("white")
        ax.grid(
            which="major",
            axis="both",
            linestyle="--",
            color="gray",
            linewidth=0.5,
            alpha=0.5,
            zorder=0,
        )
        for spine in ax.spines.values():
            spine.set_color("black")
            spine.set_linewidth(0.8)
        ax.tick_params(axis="both", colors="black", direction="out")
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        if title:
            ax.set_title(title, pad=8)

    def _style_export_legend(ax, loc="best", ncol=1, bbox_to_anchor=None):
        handles, labels = ax.get_legend_handles_labels()
        labels = [label for label in labels if not label.startswith("_")]
        if not labels:
            return
        legend = ax.legend(
            loc=loc,
            ncol=ncol,
            bbox_to_anchor=bbox_to_anchor,
            frameon=True,
            edgecolor="black",
            fancybox=False,
        )
        if legend:
            legend.get_frame().set_facecolor("white")

    def _write_figure_pair(zf, fig, stem):
        stem = _safe_filename(stem)
        written = []
        for fmt in ("png", "pdf"):
            buf = io.BytesIO()
            save_kwargs = {
                "format": fmt,
                "bbox_inches": "tight",
                "facecolor": "white",
            }
            if fmt == "png":
                save_kwargs["dpi"] = 300
            fig.savefig(buf, **save_kwargs)
            zf.writestr(f"{stem}.{fmt}", buf.getvalue())
            written.append(f"{stem}.{fmt}")
        plt.close(fig)
        return written

    def _forming_limit_point(job_name, job_dir, method):
        fp = _resolve_job_file(job_dir, "forming_limits.csv")
        if not os.path.exists(fp):
            return None
        try:
            df = _load_csv(fp).copy()
        except Exception:
            return None
        if "method" not in df.columns:
            return None
        rows = df[df["method"].astype(str) == method]
        if rows.empty:
            return None
        r = rows.iloc[0]
        e1 = pd.to_numeric(r.get("eps1_major"), errors="coerce")
        e2 = pd.to_numeric(r.get("eps2_minor"), errors="coerce")
        if pd.isna(e1) or pd.isna(e2):
            return None
        fracture_type = r.get("fracture_type", "dome")
        fracture_type = "dome" if pd.isna(fracture_type) else str(fracture_type)
        time_s = pd.to_numeric(r.get("time_s"), errors="coerce")
        u3_mm = pd.to_numeric(r.get("U3_mm"), errors="coerce")
        return {
            "name": job_name,
            "dir": job_dir,
            "method": method,
            "e1": float(e1),
            "e2": float(e2),
            "time": float(time_s) if pd.notna(time_s) else None,
            "u3": float(u3_mm) if pd.notna(u3_mm) else None,
            "fracture_type": fracture_type,
            "valid": fracture_type == "dome",
        }

    def _forming_limit_points(jobs, method):
        points = []
        for job_name, job_dir in jobs.items():
            point = _forming_limit_point(job_name, job_dir, method)
            if point is not None:
                points.append(point)
        points.sort(key=lambda p: (p["e2"], _width_from_job(p["name"]) or 0, p["name"]))
        return points

    def _export_force_displacement_fig(job_name, job_dir):
        df, _ = _read_export_csv(job_dir, ("global.csv", "punch_fd.csv"), required=("U3_mm", "RF3_N"))
        if df is None:
            return None
        df = _numeric_columns(df, ("U3_mm", "RF3_N")).dropna(subset=["U3_mm", "RF3_N"])
        if df.empty:
            return None
        df = df.sort_values("U3_mm")

        fig, axes = _new_export_figure(figsize=(6.9, 4.2))
        ax = axes[0]
        ax.plot(df["U3_mm"], df["RF3_N"], color=_MATLAB_COLORS[0], linewidth=1.7, label="Punch force")
        u3_frac, fracture_type = _fracture_u3(job_dir)
        if u3_frac is not None:
            label = f"Fracture ({fracture_type})" if fracture_type else "Fracture"
            ax.axvline(float(u3_frac), color="#A2142F", linestyle="--", linewidth=1.1, label=label)
        _style_export_axis(
            ax,
            xlabel="Punch displacement U3 [mm]",
            ylabel="Punch force RF3 [N]",
            title=f"Force-displacement - {_short_plot_label(os.path.basename(str(job_name)))}",
        )
        _style_export_legend(ax)
        fig.tight_layout()
        return fig

    def _time_or_displacement_axis(df, job_dir):
        if "U3_mm" in df.columns and df["U3_mm"].notna().any():
            return df["U3_mm"], "Punch displacement U3 [mm]", "u3"
        time_col = "total_time_s" if "total_time_s" in df.columns else "time_s"
        if time_col not in df.columns:
            return None, None, None
        if time_col == "total_time_s":
            fd, _ = _read_export_csv(job_dir, ("punch_fd.csv", "global.csv"), required=("total_time_s", "U3_mm"))
            if fd is not None:
                fd = _numeric_columns(fd, ("total_time_s", "U3_mm")).dropna(subset=["total_time_s", "U3_mm"])
                if len(fd) >= 2:
                    fd = fd.sort_values("total_time_s")
                    u3 = np.interp(df[time_col].to_numpy(), fd["total_time_s"].to_numpy(), fd["U3_mm"].to_numpy())
                    return pd.Series(u3, index=df.index), "Punch displacement U3 [mm]", "u3"
        return df[time_col], "Time [s]", "time"

    def _export_energy_history_fig(job_name, job_dir):
        df, _ = _read_export_csv(job_dir, ("global.csv", "energy_data.csv"), required=("ALLKE", "ALLIE"))
        if df is None:
            return None
        numeric = [c for c in ("time_s", "total_time_s", "U3_mm", "ALLKE", "ALLIE") if c in df.columns]
        df = _numeric_columns(df, numeric).dropna(subset=["ALLKE", "ALLIE"])
        df = df[df["ALLIE"].abs() > 1e-12].copy()
        if df.empty:
            return None
        if len(df) > 10:
            df = df.iloc[max(1, int(0.02 * len(df))):].copy()
        x, xlabel, axis_kind = _time_or_displacement_axis(df, job_dir)
        if x is None:
            return None
        ratio_pct = 100.0 * df["ALLKE"] / df["ALLIE"]

        fig, axes = _new_export_figure(nrows=2, figsize=(6.9, 5.4), sharex=True)
        axes[0].plot(x, df["ALLKE"], color=_MATLAB_COLORS[0], linewidth=1.5, label="ALLKE")
        axes[0].plot(x, df["ALLIE"], color=_MATLAB_COLORS[1], linewidth=1.5, label="ALLIE")
        _style_export_axis(
            axes[0],
            ylabel="Energy",
            title=f"Energy history - {_short_plot_label(os.path.basename(str(job_name)))}",
        )
        _style_export_legend(axes[0])

        axes[1].plot(x, ratio_pct, color=_MATLAB_COLORS[2], linewidth=1.5, label="ALLKE / ALLIE")
        axes[1].axhline(5.0, color="black", linestyle="--", linewidth=1.0, label="5% limit")
        if axis_kind == "u3":
            u3_frac, _ = _fracture_u3(job_dir)
            if u3_frac is not None:
                axes[1].axvline(float(u3_frac), color="#A2142F", linestyle="--", linewidth=1.0, label="Fracture")
        _style_export_axis(axes[1], xlabel=xlabel, ylabel="ALLKE / ALLIE [%]")
        _style_export_legend(axes[1])
        fig.tight_layout()
        return fig

    def _strain_path_frame(job_dir):
        df, _ = _read_export_csv(
            job_dir,
            ("strain_path.csv",),
            required=("time_s", "eps1_major", "eps2_minor"),
        )
        if df is None:
            return None
        cols = [c for c in ("time_s", "eps1_major", "eps2_minor", "EQPS", "TRIAX", "D", "thinning_rate") if c in df.columns]
        df = _numeric_columns(df, cols).dropna(subset=["time_s", "eps1_major", "eps2_minor"])
        if df.empty:
            return None
        group_cols = [c for c in cols if c in df.columns and c != "time_s"]
        df = df.groupby("time_s", as_index=False)[group_cols].mean().sort_values("time_s")
        return df

    def _thinning_rate(df):
        if "thinning_rate" in df.columns and df["thinning_rate"].notna().any():
            return df["thinning_rate"].to_numpy()
        thinning = (df["eps1_major"] + df["eps2_minor"]).to_numpy()
        time_s = df["time_s"].to_numpy()
        if len(df) < 2:
            return np.zeros(len(df))
        return np.gradient(thinning, time_s, edge_order=1)

    def _nearest_index(values, target):
        return min(range(len(values)), key=lambda i: abs(float(values[i]) - float(target)))

    def _vh_fit_from_ranges(t, rate_for_fit, stable_range, unstable_range):
        ts0, ts1 = stable_range
        tu0, tu1 = unstable_range
        stable_idx = [i for i in range(len(t)) if ts0 <= t[i] <= ts1]
        unstable_idx = [i for i in range(len(t)) if tu0 <= t[i] <= tu1]
        if len(stable_idx) < VH_MIN_STABLE_POINTS or len(unstable_idx) < VH_MIN_UNSTABLE_POINTS:
            return None
        xs = [t[i] for i in stable_idx]
        ys = [rate_for_fit[i] for i in stable_idx]
        xu = [t[i] for i in unstable_idx]
        yu = [rate_for_fit[i] for i in unstable_idx]
        stable_fit = _line_fit(xs, ys)
        unstable_fit = _line_fit(xu, yu)
        if not stable_fit or not unstable_fit:
            return None
        ss, si, _ = stable_fit
        us, ui, _ = unstable_fit
        denom = ss - us
        if abs(denom) < 1e-20:
            return None
        tc = (ui - si) / denom
        kc = _dic_instable_index(t, tc)
        if kc is None or kc <= 0:
            return None
        return {
            "t_fit_start": min(ts0, tu0),
            "t_fit_end": max(ts1, tu1),
            "t_cross": tc,
            "y_cross": ss * tc + si,
            "kcrit": kc,
            "kstable": kc - 1,
            "stable": {"slope": ss, "intercept": si, "count": len(stable_idx), "mse": 0},
            "unstable": {"slope": us, "intercept": ui, "count": len(unstable_idx), "mse": 0},
            "stable_range": (float(ts0), float(ts1)),
            "unstable_range": (float(tu0), float(tu1)),
        }

    def _vh_ranges_from_fit(fit, t_values):
        if not fit:
            return None, None
        if "stable_range" in fit and "unstable_range" in fit:
            return fit["stable_range"], fit["unstable_range"]
        window = [float(tv) for tv in t_values if fit["t_fit_start"] <= float(tv) <= fit["t_fit_end"]]
        if not window:
            return None, None
        stable_count = int(fit.get("stable", {}).get("count", 0))
        unstable_count = int(fit.get("unstable", {}).get("count", 0))
        if stable_count <= 0 or unstable_count <= 0:
            return None, None
        stable_end = min(stable_count - 1, len(window) - 1)
        unstable_start = max(0, len(window) - unstable_count)
        return (window[0], window[stable_end]), (window[unstable_start], window[-1])

    def _stored_vh_settings(job_dir):
        fp = _resolve_job_file(job_dir, "forming_limits.csv")
        if not os.path.exists(fp):
            return {}
        try:
            df = _load_csv(fp)
        except Exception:
            return {}
        if "method" not in df.columns:
            return {}
        rows = df[df["method"].astype(str) == "volk_hora"]
        if rows.empty:
            return {}
        row = rows.iloc[0]

        def _num(col):
            if col not in row.index:
                return None
            val = pd.to_numeric(row.get(col), errors="coerce")
            return float(val) if pd.notna(val) else None

        settings = {
            "time_s": _num("time_s"),
            "vh_smoothing_window": _num("vh_smoothing_window"),
        }
        stable = (_num("vh_stable_t0"), _num("vh_stable_t1"))
        unstable = (_num("vh_unstable_t0"), _num("vh_unstable_t1"))
        if all(v is not None for v in stable + unstable):
            settings["stable_range"] = stable
            settings["unstable_range"] = unstable
        return settings

    def _export_vh_curves_fig(job_name, job_dir):
        df = _strain_path_frame(job_dir)
        if df is None or len(df) < 2:
            return None
        t = df["time_s"].to_numpy(dtype=float)
        raw_rate = _thinning_rate(df)
        rate = raw_rate
        fit = None
        smoothing_used = 1
        stored_vh = _stored_vh_settings(job_dir)
        if "stable_range" in stored_vh and "unstable_range" in stored_vh:
            smoothing_used = int(stored_vh.get("vh_smoothing_window") or 1)
            candidate = _moving_average(raw_rate.tolist(), smoothing_used)
            fit = _vh_fit_from_ranges(
                t.tolist(),
                candidate,
                stored_vh["stable_range"],
                stored_vh["unstable_range"],
            )
            rate = np.asarray(candidate, dtype=float)
        if fit is None:
            for smoothing_window in (1, 5, 11, 21):
                candidate = _moving_average(raw_rate.tolist(), smoothing_window)
                fit = _volk_hora_fit(t.tolist(), candidate)
                if fit is not None:
                    rate = np.asarray(candidate, dtype=float)
                    smoothing_used = smoothing_window
                    break

        fig, axes = _new_export_figure(figsize=(6.9, 4.2))
        ax = axes[0]
        rate_label = "Thinning rate" if smoothing_used == 1 else f"Thinning rate ({smoothing_used} pt mean)"
        ax.plot(t, rate, color=_MATLAB_COLORS[0], linewidth=1.5, label=rate_label)
        if fit is not None:
            stable = fit["stable"]
            unstable = fit["unstable"]
            ts = [fit["t_fit_start"], fit["t_cross"]]
            ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
            tu = [fit["t_cross"], fit["t_fit_end"]]
            yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
            ax.plot(ts, ys, color="#77AC30", linewidth=1.4, label="Stable fit")
            ax.plot(tu, yu, color="#A2142F", linewidth=1.4, label="Unstable fit")
        _style_export_axis(
            ax,
            xlabel="Time [s]",
            ylabel=r"$d(e_1+e_2)/dt$ [1/s]",
            title=f"V&H thinning rate - {_short_plot_label(os.path.basename(str(job_name)))}",
        )
        _style_export_legend(ax)
        fig.tight_layout()
        return fig

    def _export_triaxiality_fig(job_name, job_dir):
        df = _strain_path_frame(job_dir)
        if df is None or "TRIAX" not in df.columns:
            return None
        if "EQPS" in df.columns and df["EQPS"].notna().any():
            df = df.dropna(subset=["EQPS", "TRIAX"])
            x = df["EQPS"]
            xlabel = "Equivalent plastic strain EQPS [-]"
        else:
            df = df.dropna(subset=["time_s", "TRIAX"])
            x = df["time_s"]
            xlabel = "Time [s]"
        if df.empty:
            return None
        fig, axes = _new_export_figure(figsize=(6.9, 4.2))
        ax = axes[0]
        ax.plot(x, df["TRIAX"], color=_MATLAB_COLORS[0], linewidth=1.5, label=r"Triaxiality $\eta$")
        for eta, label in [
            (1.0 / 3.0, r"Uniaxial $\eta=1/3$"),
            (0.577, r"Plane strain $\eta\approx0.577$"),
            (2.0 / 3.0, r"Equibiaxial $\eta=2/3$"),
        ]:
            ax.axhline(eta, color="gray", linestyle="--", linewidth=0.8, alpha=0.7, label=label)
        _style_export_axis(
            ax,
            xlabel=xlabel,
            ylabel=r"Triaxiality $\eta$ [$-$]",
            title=f"Stress-state path - {_short_plot_label(os.path.basename(str(job_name)))}",
        )
        _style_export_legend(ax)
        fig.tight_layout()
        return fig

    def _campaign_key(job_name):
        return _job_campaign_key(job_name)

    def _matching_campaign_jobs(selected_name, selected_dir, all_job_dirs):
        target = _campaign_key(selected_name or selected_dir)
        matches = {}

        def _add_match(label, path):
            if not _is_job_dir(path):
                return
            if _campaign_key(label) != target and _campaign_key(path) != target:
                return
            display = os.path.basename(os.path.normpath(path))
            if display in matches and os.path.abspath(matches[display]) != os.path.abspath(path):
                display = os.path.relpath(path, results_dir)
            matches[display] = path

        def _scan_job_tree(root, max_depth=3):
            root = os.path.abspath(root)
            stack = [(root, 0)]
            seen = set()
            while stack:
                path, depth = stack.pop()
                if path in seen:
                    continue
                seen.add(path)
                if _is_job_dir(path):
                    _add_match(os.path.basename(os.path.normpath(path)), path)
                    continue
                if depth >= max_depth:
                    continue
                try:
                    entries = list(os.scandir(path))
                except (OSError, PermissionError):
                    continue
                for entry in entries:
                    if entry.is_dir():
                        stack.append((entry.path, depth + 1))

        parent = os.path.dirname(os.path.abspath(selected_dir))
        try:
            for entry in os.scandir(parent):
                if entry.is_dir():
                    _add_match(entry.name, entry.path)
        except (OSError, PermissionError):
            pass

        for label, path in all_job_dirs.items():
            _add_match(label, path)

        try:
            _scan_job_tree(results_dir)
        except NameError:
            pass

        if not matches:
            matches[os.path.basename(os.path.normpath(selected_dir))] = selected_dir

        matches = _dedupe_jobs_by_parameters(matches)
        return dict(sorted(
            matches.items(),
            key=lambda kv: (_width_from_job(kv[0]) if _width_from_job(kv[0]) is not None else 10**9, kv[0]),
        ))

    def _plot_test_type_label(text):
        text = str(text).lower()
        if "marc" in text:
            return "Marciniak"
        if "pip" in text:
            return "PiP"
        if "naka" in text or "nakazima" in text:
            return "Nakazima"
        return "Test"

    def _plot_separator_meta(text, assume_default_mr=False, assume_default_ps=False):
        text = os.path.basename(os.path.normpath(str(text)))
        text = text[4:] if text.startswith("FLC_") else text
        test_type = _plot_test_type_label(text)
        punch_match = re.search(r"(?:^|_)(?:Naka|Marc)(\d+)", text, flags=re.I)
        if not punch_match:
            punch_match = re.search(r"_pdia([\dp]+)", text, flags=re.I)
        mass_match = re.search(r"_ms(\d+e\d+)(?=_|$)", text, flags=re.I)
        mesh_match = re.search(r"_mr([\dp]+)(?=_|$)", text, flags=re.I)
        nt_match = re.search(r"_nt(\d+)(?=_|$)", text, flags=re.I)
        ps_match = re.search(r"(?:^|_)ps([\dp]+)(?=_|$)", text, flags=re.I)
        return {
            "test_type": test_type,
            "punch": f"P{punch_match.group(1)}" if punch_match else "",
            "ms": f"ms{mass_match.group(1)}" if mass_match else "",
            "mr": f"mr{mesh_match.group(1)}" if mesh_match else ("mr1" if assume_default_mr else ""),
            "nt": f"nt{nt_match.group(1)}" if nt_match else "",
            "ps": f"ps{ps_match.group(1)}" if ps_match else ("ps5" if assume_default_ps else ""),
        }

    def _plot_separator_key(text):
        meta = _plot_separator_meta(text, assume_default_mr=True, assume_default_ps=True)
        return "|".join(meta[k] for k in ("test_type", "punch", "ms", "mr", "nt", "ps") if meta[k])

    def _plot_separator_label(text, assume_default_mr=False, assume_default_ps=False):
        meta = _plot_separator_meta(text, assume_default_mr=assume_default_mr, assume_default_ps=assume_default_ps)
        parts = [meta[k] for k in ("punch", "ms", "mr", "nt", "ps") if meta[k]]
        return " > ".join(parts)

    def _fld_export_title(source_jobs):
        names = []
        for source_label, jobs in source_jobs:
            if source_label and source_label != "matching geometries":
                names.append(source_label)
            names.extend(jobs.keys())
        joined = " ".join(names)
        test_type = _plot_test_type_label(joined)
        separators = []
        for name in names:
            separator = _plot_separator_label(name)
            if separator and separator not in separators:
                separators.append(separator)
        title = f"FLD - {test_type}"
        if separators:
            title += " > " + ", ".join(separators[:3])
            if len(separators) > 3:
                title += f", +{len(separators) - 3}"
        return title

    def _export_fld_fig(source_jobs, include_vh=True, title=None, show_paths=True):
        fig, axes = _new_export_figure(figsize=(7.2, 4.8))
        ax = axes[0]
        all_e1 = []
        all_e2 = []
        plotted = False

        for i, (source_label, jobs) in enumerate(source_jobs):
            color = _MATLAB_COLORS[i % len(_MATLAB_COLORS)]
            if show_paths:
                for job_name, job_dir in jobs.items():
                    e1_path, e2_path = _job_strain_path(job_dir)
                    if e1_path and e2_path:
                        all_e1.extend(e1_path)
                        all_e2.extend(e2_path)
                        ax.plot(
                            e2_path,
                            e1_path,
                            linestyle=":",
                            color=color,
                            linewidth=0.7,
                            alpha=0.35,
                            label="_strain_path",
                        )

            fflc_points = _forming_limit_points(jobs, "fracture")
            valid_fflc = [p for p in fflc_points if p["valid"]]
            invalid_fflc = [p for p in fflc_points if not p["valid"]]
            if valid_fflc:
                all_e1.extend(p["e1"] for p in valid_fflc)
                all_e2.extend(p["e2"] for p in valid_fflc)
                label = "FFLC" if len(source_jobs) == 1 else f"{_short_plot_label(source_label)} FFLC"
                ax.plot(
                    [p["e2"] for p in valid_fflc],
                    [p["e1"] for p in valid_fflc],
                    "-o",
                    color=color,
                    linewidth=1.6,
                    markersize=4.5,
                    label=label,
                )
                plotted = True
            if invalid_fflc:
                all_e1.extend(p["e1"] for p in invalid_fflc)
                all_e2.extend(p["e2"] for p in invalid_fflc)
                label = "FFLC diagnostics" if len(source_jobs) == 1 else f"{_short_plot_label(source_label)} diagnostics"
                ax.plot(
                    [p["e2"] for p in invalid_fflc],
                    [p["e1"] for p in invalid_fflc],
                    linestyle="None",
                    marker="x",
                    color=color,
                    markersize=6,
                    label=label,
                )
                plotted = True

            if include_vh:
                vh_points = [p for p in _forming_limit_points(jobs, "volk_hora") if p["valid"]]
                if vh_points:
                    all_e1.extend(p["e1"] for p in vh_points)
                    all_e2.extend(p["e2"] for p in vh_points)
                    label = "FLC V&H" if len(source_jobs) == 1 else f"{_short_plot_label(source_label)} V&H"
                    ax.plot(
                        [p["e2"] for p in vh_points],
                        [p["e1"] for p in vh_points],
                        "--D",
                        color=color,
                        linewidth=1.2,
                        markersize=4,
                        label=label,
                    )
                    plotted = True

        if not plotted:
            plt.close(fig)
            return None

        x_min = min(all_e2)
        x_max = max(all_e2)
        y_min = min(all_e1)
        y_max = max(all_e1)
        x_span = max(x_max - x_min, 0.15)
        y_span = max(y_max - y_min, 0.15)
        x0 = min(x_min - 0.18 * x_span, -0.05)
        x1 = max(x_max + 0.18 * x_span, 0.05)
        y0 = min(0.0, y_min - 0.18 * y_span)
        y1 = y_max + 0.18 * y_span

        ax.plot([x0, 0.0], [-2.0 * x0, 0.0], color="silver", linestyle="-.", linewidth=0.9, label="_uniaxial")
        ax.plot([0.0, x1], [0.0, x1], color="silver", linestyle="--", linewidth=0.9, label="_equibiaxial")
        ax.axvline(0, linewidth=0.8, color="silver", zorder=0)
        ax.axhline(0, linewidth=0.8, color="silver", zorder=0)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        _style_export_axis(
            ax,
            xlabel=r"Minor strain $e_2$ [$-$]",
            ylabel=r"Major strain $e_1$ [$-$]",
            title=title or _fld_export_title(source_jobs),
        )
        legend_cols = min(4, max(1, len(source_jobs) * (2 if include_vh else 1)))
        _style_export_legend(ax, loc="lower center", ncol=legend_cols, bbox_to_anchor=(0.5, -0.33))
        fig.subplots_adjust(bottom=0.28)
        return fig

    def _bundle_single_job_graphs(job_name, job_dir, all_job_dirs):
        job_stem = _safe_filename(os.path.basename(os.path.normpath(str(job_name))))
        generated = []
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            plot_specs = [
                ("force displacement", f"{job_stem}_force_displacement", _export_force_displacement_fig(job_name, job_dir)),
                ("energy history", f"{job_stem}_energy_history", _export_energy_history_fig(job_name, job_dir)),
                ("V_and_H curves", f"{job_stem}_VH_curves", _export_vh_curves_fig(job_name, job_dir)),
                ("triaxiality", f"{job_stem}_triaxiality", _export_triaxiality_fig(job_name, job_dir)),
            ]
            for label, stem, fig in plot_specs:
                if fig is None:
                    continue
                _write_figure_pair(zf, fig, stem)
                generated.append(label)

            campaign_jobs = _matching_campaign_jobs(job_name, job_dir, all_job_dirs)
            fld_fig = _export_fld_fig(
                [("matching geometries", campaign_jobs)],
                include_vh=True,
            )
            if fld_fig is not None:
                _write_figure_pair(zf, fld_fig, f"{job_stem}_FLD_matching_geometries")
                generated.append("FLD")

        if not generated:
            return None, []
        return buf.getvalue(), generated

    def _bundle_fld_graphs(selected_sources, source_options):
        source_jobs = [
            (source_label, source_options[source_label]["jobs"])
            for source_label in selected_sources
            if source_label in source_options
        ]
        if not source_jobs:
            return None, []
        stem = "FLD_" + _safe_filename("_".join(selected_sources[:3]))
        if len(selected_sources) > 3:
            stem += f"_plus_{len(selected_sources) - 3}"

        buf = io.BytesIO()
        generated = []
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            fig = _export_fld_fig(source_jobs, include_vh=True)
            if fig is not None:
                _write_figure_pair(zf, fig, stem)
                generated.append("FLD")
        if not generated:
            return None, []
        return buf.getvalue(), generated

    def _downloads_directory():
        return os.path.join(os.path.expanduser("~"), "Downloads")

    def _unique_download_path(file_name):
        downloads_dir = _downloads_directory()
        os.makedirs(downloads_dir, exist_ok=True)
        root, ext = os.path.splitext(_safe_filename(file_name))
        candidate = os.path.join(downloads_dir, root + ext)
        idx = 2
        while os.path.exists(candidate):
            candidate = os.path.join(downloads_dir, f"{root}_{idx}{ext}")
            idx += 1
        return candidate

    def _write_post_processing_plots_to_downloads(data, file_name):
        target = _unique_download_path(file_name)
        with open(target, "wb") as fh:
            fh.write(data)
        return target

    def _render_single_graph_download(job_name, job_dir, all_job_dirs, key_prefix):
        export_key = f"{key_prefix}_graph_bundle"
        if st.button("Download Post-processing plots", type="primary", key=f"{export_key}_btn"):
            data, _generated = _bundle_single_job_graphs(job_name, job_dir, all_job_dirs)
            if data is None:
                st.warning("No graph CSV data found for this job.")
                st.session_state.pop(export_key, None)
            else:
                file_name = f"{_safe_filename(os.path.basename(os.path.normpath(str(job_name))))}_post_processing_plots.zip"
                try:
                    target = _write_post_processing_plots_to_downloads(data, file_name)
                except OSError as exc:
                    st.error(f"Could not write to Downloads: {exc}")
                    st.session_state.pop(export_key, None)
                    return
                st.session_state[export_key] = {"target": target}
                st.toast(f"Saved to {target}", icon="💾")

    def _render_fld_graph_download(selected_sources, source_options, key_prefix):
        export_key = f"{key_prefix}_fld_bundle"
        if st.button("Download Post-processing plots", type="primary", key=f"{export_key}_btn"):
            data, _generated = _bundle_fld_graphs(selected_sources, source_options)
            if data is None:
                st.warning("No forming-limit CSV data found for the selected source.")
                st.session_state.pop(export_key, None)
            else:
                file_name = f"{_safe_filename('_'.join(selected_sources[:2]))}_post_processing_plots.zip"
                try:
                    target = _write_post_processing_plots_to_downloads(data, file_name)
                except OSError as exc:
                    st.error(f"Could not write to Downloads: {exc}")
                    st.session_state.pop(export_key, None)
                    return
                st.session_state[export_key] = {"target": target}
                st.toast(f"Saved to {target}", icon="💾")

    # Sync UI (paths, scope, profile) lives in one collapsed expander further
    # down; results_dir/euler_src are assigned there before anything uses them.

    core_csv_files = [
        "global.csv",
        "punch_fd.csv",
        "energy_data.csv",
        "forming_limits.csv",
        "strain_path.csv",
        "specimen_outline.csv",
        "strain_cluster_faces.csv",
        "flc_points.csv",
    ]
    sync_profiles = {
        "Post-processing plots (fast)": core_csv_files + ["*.pdf", "*.png"],
        "Core CSV only (fastest)": core_csv_files,
        "Diagnostics CSVs (slower)": core_csv_files + ["strain_cluster.csv", "elout.csv"],
        "Full raw results incl. movies": ["*.csv", "*.pdf", "*.png", "*.webm", "*.mp4"],
    }
    _SYNC_SCOPES = [
        "Latest jobs only",
        "Selected jobs only",
        "Current FLD/source only",
        "Full results directory",
    ]

    def _parse_remote_src(src):
        """Split 'user@host:/path/' into ('user@host', '/path')."""
        spec, sep, path = str(src).partition(":")
        path = path.rstrip("/")
        if not sep or not spec or not path:
            return None, None
        return spec, path

    _JOB_INDEX_MARKERS = ("global.csv", "forming_limits.csv")

    def _fmt_bytes(n):
        for unit in ("B", "kB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.0f} {unit}" if unit in ("B", "kB") else f"{n:.1f} {unit}"
            n /= 1024.0
        return f"{n:.1f} GB"

    def _fetch_remote_job_index(spec, base):
        """List remote job dirs via one ssh find call — metadata only.

        Returns [(rel_dir, newest_marker_mtime, total_bytes), ...] newest
        first. total_bytes counts every file in the dir (all profiles), so the
        preview size is an upper bound before profile filtering.
        """
        find_cmd = (
            f"find {shlex.quote(base)} -mindepth 2 -maxdepth 3 -type f -printf '%T@\\t%s\\t%P\\n'"
        )
        result = _run_ssh_command(
            _ssh_command(spec, find_cmd, connect_timeout=10),
            timeout=_ssh_timeout(default_normal=180, default_key_only=90),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ssh find failed")
        newest, sizes, job_rel_dirs = {}, {}, set()
        for line in result.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            try:
                ts = float(parts[0])
                size = int(parts[1])
            except ValueError:
                continue
            rel_dir, _, fname = parts[2].rpartition("/")
            if not rel_dir:
                continue
            sizes[rel_dir] = sizes.get(rel_dir, 0) + size
            if fname in _JOB_INDEX_MARKERS:
                job_rel_dirs.add(rel_dir)
                if ts > newest.get(rel_dir, 0.0):
                    newest[rel_dir] = ts
        return sorted(
            ((rel, newest[rel], sizes.get(rel, 0)) for rel in job_rel_dirs),
            key=lambda item: item[1], reverse=True,
        )

    _LAST_SYNC_PATH = os.path.join(PROJECT_DIR, ".streamlit", "last_sync.json")

    def _read_last_sync():
        try:
            with open(_LAST_SYNC_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _write_last_sync(info):
        try:
            os.makedirs(os.path.dirname(_LAST_SYNC_PATH), exist_ok=True)
            with open(_LAST_SYNC_PATH, "w", encoding="utf-8") as fh:
                json.dump(info, fh)
        except OSError:
            pass

    @st.fragment
    def _euler_sync_controls():
        _toast = st.session_state.pop("_results_last_sync_toast", None)
        if _toast:
            st.toast(_toast, icon="✅")
        ssh_verified = _euler_access_verified()
        if st.session_state.get("results_sync_scope") == "Current FLC/source only":
            st.session_state["results_sync_scope"] = "Current FLD/source only"

        c_scope, c_n, c_profile = st.columns([1.8, 0.8, 2.4])
        with c_scope:
            sync_scope = st.selectbox(
                "Sync scope", _SYNC_SCOPES, index=0, key="results_sync_scope",
                help="Latest/Selected pull only the chosen job folders. Only "
                     "'Full results directory' walks the whole Euler tree.",
            )
        with c_n:
            n_latest = st.selectbox(
                "Jobs", [5, 10, 20, 50], index=0, key="results_sync_n_latest",
                disabled=sync_scope != "Latest jobs only",
            )
        with c_profile:
            sync_profile = st.selectbox(
                "Sync profile",
                list(sync_profiles.keys()),
                index=0,
                key="results_sync_profile",
                help=(
                    "Default skips raw extraction CSVs such as strain_dome.csv and "
                    "strain_neighborhood.csv, which dominate transfer time. Use Full only "
                    "when you explicitly need every raw CSV or movie."
                ),
            )

        remote_spec, remote_base = _parse_remote_src(euler_src)
        scope_rel_dirs = None      # None → full remote tree
        scope_problem = None
        if not ssh_verified:
            scope_problem = "Verify Euler access from the account menu before syncing."

        need_remote_index = sync_scope in ("Latest jobs only", "Selected jobs only")
        remote_index = st.session_state.get("_remote_job_index")
        if need_remote_index and not scope_problem:
            if remote_spec is None:
                scope_problem = "Euler source must look like user@host:/path for scoped syncs."
            else:
                c_list, c_age = st.columns([1.4, 3.6], vertical_alignment="center")
                list_label = "Refresh remote job list" if remote_index else "List remote jobs"
                if c_list.button(list_label, key="results_sync_list_remote"):
                    try:
                        with st.spinner("Listing remote job directories (ssh, metadata only)…"):
                            jobs = _fetch_remote_job_index(remote_spec, remote_base)
                        st.session_state["_remote_job_index"] = (time.time(), jobs)
                        remote_index = st.session_state["_remote_job_index"]
                    except Exception as exc:
                        st.error(f"Could not list remote jobs: {exc}")
                if remote_index:
                    c_age.caption(
                        f"{len(remote_index[1])} remote job folders · listed at "
                        f"{time.strftime('%H:%M:%S', time.localtime(remote_index[0]))}"
                    )
                elif scope_problem is None:
                    scope_problem = "List remote jobs first — one ssh call, nothing is downloaded."

        if sync_scope == "Latest jobs only" and remote_index and not scope_problem:
            scope_rel_dirs = [rel for rel, _ts, _sz in remote_index[1][:int(n_latest)]]
            if not scope_rel_dirs:
                scope_problem = "No job directories found on Euler."

        elif sync_scope == "Selected jobs only" and remote_index and not scope_problem:
            rel_by_label = {}
            for rel, ts, sz in remote_index[1]:
                stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
                rel_by_label[f"{rel}   ({stamp} · {_fmt_bytes(sz)})"] = rel
            # Drop stale selections whose labels changed with a fresh listing.
            _ms_key = "results_sync_selected_jobs"
            if st.session_state.get(_ms_key):
                st.session_state[_ms_key] = [
                    v for v in st.session_state[_ms_key] if v in rel_by_label
                ]
            chosen = st.multiselect(
                "Remote jobs to pull",
                list(rel_by_label.keys()),
                key="results_sync_selected_jobs",
            )
            include_siblings = st.checkbox(
                "Include sibling specimens (pull the whole FLD source folder)",
                value=True,
                key="results_sync_include_siblings",
                help="FLD plots need the sibling widths of the same campaign, "
                     "so pulling the parent FLD source folder is the safe default.",
            )
            rels = [rel_by_label[c] for c in chosen]
            if include_siblings:
                rels = [rel.split("/", 1)[0] for rel in rels]
            scope_rel_dirs = sorted(set(rels))
            if not scope_rel_dirs:
                scope_problem = "Select at least one remote job."

        elif sync_scope == "Current FLD/source only":
            if remote_spec is None:
                scope_problem = "Euler source must look like user@host:/path for scoped syncs."
            else:
                scope_rel_dirs = sorted(set(st.session_state.get("_results_sync_scope_dirs") or []))
                if not scope_rel_dirs:
                    scope_problem = ("No current selection — open a job or an FLD source "
                                     "below first, then sync it here.")

        def _scope_size_bytes(rel_dirs):
            """Upper-bound size from the remote index (all file types)."""
            if not remote_index:
                return None
            targets = set(rel_dirs)
            total = 0
            for rel, _ts, sz in remote_index[1]:
                if rel in targets or rel.split("/", 1)[0] in targets:
                    total += sz
            return total

        if scope_problem:
            st.caption(f"⚠️ {scope_problem}")
        elif scope_rel_dirs is None:
            st.caption(f"Full mirror of `{euler_src}` → `{results_dir}` · {sync_profile}")
        else:
            n_dirs = len(scope_rel_dirs)
            size_est = _scope_size_bytes(scope_rel_dirs)
            size_txt = (
                f" · ≤ {_fmt_bytes(size_est)} before profile filtering"
                if size_est else ""
            )
            st.caption(
                f"Will pull {n_dirs} director{'y' if n_dirs == 1 else 'ies'} "
                f"→ `{results_dir}` · {sync_profile}{size_txt}"
            )
            with st.expander("Directories to pull"):
                st.code("\n".join(scope_rel_dirs))

        c_sync, c_rescan, c_extra = st.columns([1.2, 1.2, 2.6], vertical_alignment="center")
        do_sync = c_sync.button(
            "Sync from Euler", type="primary", width="stretch",
            disabled=bool(scope_problem),
        )
        if c_rescan.button("Rescan local results", width="stretch",
                           key="results_rescan_local",
                           help="Re-read the local results directory without syncing."):
            _invalidate_results_caches()
            st.rerun(scope="app")
        delete_stale = False
        if sync_scope == "Full results directory":
            delete_stale = c_extra.checkbox(
                "Delete local files removed on Euler", value=False,
                key="results_sync_delete_stale",
                help="Only offered for full syncs so a scoped pull can never "
                     "delete other local jobs.",
            )

        _last = _read_last_sync()
        if _last:
            st.caption(
                f"Last sync: {_last.get('when', '?')} · {_last.get('desc', '')}"
            )

        if not do_sync:
            return

        os.makedirs(results_dir, exist_ok=True)
        filter_args = ["--include=*/"]
        for pattern in sync_profiles[sync_profile]:
            filter_args.append(f"--include={pattern}")
        filter_args.append("--exclude=*")

        # Use the selected SSH mode. Normal mode reuses the Terminal-created
        # control socket, so rsync stays non-interactive here.
        _ssh_opt = ["-e", _ssh_transport(connect_timeout=8)]

        if scope_rel_dirs is None:
            sync_cmd = ["rsync", "-av", *_ssh_opt,
                        "--whole-file", "--prune-empty-dirs", *filter_args]
            if delete_stale:
                sync_cmd.append("--delete")
            sync_cmd += [euler_src, results_dir + "/"]
            scope_desc = "full directory"
        else:
            # -R keeps the path after each /./ pivot, so FLC_x/job lands in
            # FLC_x/job locally; the space-separated sources are expanded by
            # the remote shell, giving one connection for all directories.
            sources = " ".join(f"{remote_base}/./{rel}" for rel in scope_rel_dirs)
            sync_cmd = [
                "rsync", "-av", *_ssh_opt,
                "--whole-file", "--prune-empty-dirs", "--relative",
                *filter_args, f"{remote_spec}:{sources}", results_dir + "/",
            ]
            scope_desc = f"{len(scope_rel_dirs)} director{'y' if len(scope_rel_dirs) == 1 else 'ies'}"

        # Stream rsync output into a live status box, so long syncs show
        # progress (current file, running count) instead of a frozen spinner.
        _skip_prefixes = ("sending ", "receiving ", "sent ", "total ", "building ")
        n_files = 0
        with st.status(f"Syncing from Euler — {scope_desc}, {sync_profile}",
                       expanded=False) as status:
            tail = collections.deque(maxlen=30)
            # stderr is merged into stdout so a flood of errors cannot fill the
            # stderr pipe and deadlock the stdout read loop.
            proc = subprocess.Popen(
                sync_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tail.append(line)
                if line.endswith("/") or line.startswith(_skip_prefixes):
                    continue
                n_files += 1
                if n_files % 5 == 1:
                    status.update(
                        label=f"Syncing — {n_files} files · {line[-70:]}"
                    )
            rc = proc.wait()
            if rc != 0:
                status.update(label="Sync failed", state="error")
                st.error("rsync failed")
                if tail:
                    st.code("\n".join(tail))
                return
            status.update(
                label=f"Sync complete — {n_files} files updated", state="complete"
            )

        _invalidate_results_caches()
        desc = f"{n_files} files · {scope_desc} · {sync_profile}"
        _write_last_sync({
            "when": time.strftime("%Y-%m-%d %H:%M"),
            "desc": desc,
        })
        st.session_state["_results_last_sync_toast"] = f"Sync complete — {desc}"
        st.rerun(scope="app")

    _last_sync_info = _read_last_sync()
    _sync_label = "🔄 Euler sync"
    if _last_sync_info:
        _sync_label += f" · last: {_last_sync_info.get('when', '?')}"
    with st.expander(_sync_label, expanded=False):
        # Seed-first (no value=): _switch_user rewrites these via the API, and
        # value= together with API-set state triggers the yellow warning.
        st.session_state.setdefault("results_local_dir", _default_results_dir())
        st.session_state.setdefault("results_euler_src", _default_euler_src())
        c_dir, c_src = st.columns([2, 3])
        with c_dir:
            results_dir = st.text_input(
                "Local results directory",
                key="results_local_dir",
            )
        with c_src:
            euler_src = st.text_input(
                "Euler source path",
                key="results_euler_src",
                help="Narrowing this to FLC_output avoids walking the whole remote AbaqusProject tree.",
            )
        _euler_sync_controls()

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
        modes.append("FLD")
    elif job_dirs:
        modes.append("FLD")

    def _persisted_choice(label, options, key, default=None, **kwargs):
        options = list(options)
        if not options:
            return None
        fallback = default if default in options else options[0]
        if st.session_state.get(key) not in options:
            st.session_state[key] = fallback
        return st.selectbox(label, options, key=key, **kwargs)

    if st.session_state.get("results_view_mode") == "FLC":
        st.session_state["results_view_mode"] = "FLD"
    if st.session_state.get("results_view_mode") not in modes:
        st.session_state["results_view_mode"] = modes[0]
    view_mode = st.segmented_control(
        "View",
        modes,
        key="results_view_mode",
    )
    if view_mode and st.query_params.get("view") != view_mode:
        st.query_params["view"] = view_mode

    if job_dirs:
        _sort_col, _ = st.columns([3, 5])
        with _sort_col:
            _job_sort = st.radio(
                "Sort jobs by",
                ["Newest first", "Oldest first", "Name (A→Z)"],
                horizontal=True,
                index=0,
                key="results_job_sort",
            )
        if _job_sort == "Newest first":
            job_dirs = dict(sorted(job_dirs.items(), key=lambda kv: _job_mtime(kv[1]), reverse=True))
        elif _job_sort == "Oldest first":
            job_dirs = dict(sorted(job_dirs.items(), key=lambda kv: _job_mtime(kv[1]), reverse=False))

    st.markdown("---")

    # ── Shared rendering helpers ──────────────────────────────────────────────

    def _render_job_media(job_dir):
        pngs = sorted(f for f in os.listdir(job_dir) if f.endswith(".png"))
        if pngs:
            img_cols = st.columns(min(len(pngs), 3))
            for i, png in enumerate(pngs):
                img_cols[i % 3].image(os.path.join(job_dir, png), width="stretch")
        _display_job_videos(job_dir)

    def _render_pdf_downloads(job_dir, key_prefix):
        pdfs = sorted(
            f for f in os.listdir(job_dir)
            if f.endswith(".pdf") and f != "postproc_plots.pdf"
        )
        if not pdfs:
            return
        st.markdown("---")
        dl_cols = st.columns(len(pdfs))
        for i, pdf in enumerate(pdfs):
            with open(os.path.join(job_dir, pdf), "rb") as fh:
                dl_cols[i].download_button(
                    f"Download {pdf}", fh, file_name=pdf,
                    mime="application/pdf", key=f"{key_prefix}_dl_{pdf}",
                )

    def _push_job_files_to_euler(job_dir, file_paths):
        """Mirror edited job files back to the matching Euler job dir.

        Keeps local and remote copies identical after an override save, so
        cluster-side re-plots and future sync-downs agree with the saved fit.
        Returns (ok, message).
        """
        src = st.session_state.get("results_euler_src") or euler_src
        local_root = st.session_state.get("results_local_dir") or results_dir
        remote_spec, remote_base = _parse_remote_src(src)
        if remote_spec is None:
            return False, "Euler source must look like user@host:/path — override saved locally only."
        if not _euler_access_verified():
            return False, "Euler access not verified — override saved locally only."
        rel = os.path.relpath(os.path.abspath(job_dir), os.path.abspath(local_root))
        if rel.startswith(".."):
            return False, f"Job dir is outside {local_root} — override saved locally only."
        push_cmd = [
            "rsync", "-a", "--whole-file",
            "-e", _ssh_transport(connect_timeout=8),
            *file_paths, f"{remote_spec}:{remote_base}/{rel}/",
        ]
        try:
            result = subprocess.run(
                push_cmd, capture_output=True, text=True,
                timeout=_ssh_timeout(default_normal=120, default_key_only=60),
            )
        except subprocess.TimeoutExpired:
            return False, "rsync to Euler timed out — override saved locally only."
        if result.returncode != 0:
            reason = result.stderr.strip() or "rsync to Euler failed"
            return False, f"{reason} — override saved locally only."
        return True, f"{remote_base}/{rel}"

    @st.fragment
    def _render_job_tabs(job_dir, key_prefix, panel_state_key="results_panel"):
        sections = [
            "Force-Disp.", "Energy", "Strain Path", "V&H",
            "Cluster Loc.", "Forming Limits",
        ]
        # One shared panel key per view: the selected panel stays put when the
        # user switches jobs, and switching panels reruns only this fragment.
        panel_key = panel_state_key
        if st.session_state.get(panel_key) not in sections:
            st.session_state[panel_key] = sections[0]
        # No scroll scripting here on purpose: fragment reruns keep the
        # viewport exactly where it is, which beats any auto-scroll attempt.
        panel = st.segmented_control(
            "Result panel",
            sections,
            key=panel_key,
        )
        if (panel and panel_state_key == "results_panel_single"
                and st.query_params.get("panel") != panel):
            st.query_params["panel"] = panel

        if panel == "Force-Disp.":
            fig_fd = _figure_memo(
                "fd", job_dir,
                ("global.csv", "punch_fd.csv", "forming_limits.csv", "strain_path.csv"),
                lambda: _fd_with_fracture_fig(job_dir),
            )
            if fig_fd is not None:
                _plotly_chart(fig_fd, width="stretch", key=f"{key_prefix}_fd")
            else:
                st.info("Force–displacement data unavailable")

        elif panel == "Energy":
            fig_en = _figure_memo(
                "energy", job_dir,
                ("global.csv", "energy_data.csv", "punch_fd.csv", "forming_limits.csv"),
                lambda: _energy_fig_v2(job_dir),
            )
            if fig_en is not None:
                _plotly_chart(fig_en, width="stretch", key=f"{key_prefix}_en")
            else:
                st.info("Energy data unavailable")

        elif panel == "Strain Path":
            fig, reason = _figure_memo(
                "sp_quick", job_dir,
                ("strain_path.csv", "elout.csv"),
                lambda: _strain_path_quick_fig(job_dir),
            )
            if fig is not None:
                _plotly_chart(fig, width="stretch", key=f"{key_prefix}_sp_quick")
            else:
                st.info(reason or "Strain-path data unavailable")
            fig_extras = _figure_memo(
                "sp_extras", job_dir,
                ("strain_path.csv",),
                lambda: _strain_path_extras_fig(job_dir),
            )
            if fig_extras is not None:
                _plotly_chart(fig_extras, width="stretch", key=f"{key_prefix}_sp_extras")
            if st.checkbox(
                "Load cluster strain paths (large diagnostics CSV)",
                value=False,
                key=f"{key_prefix}_load_cluster_paths",
                help="Reads strain_cluster.csv. This can be slow for large jobs.",
            ):
                cluster_fig, cluster_reason = _strain_path_compare_fig(job_dir)
                if cluster_fig is None:
                    cluster_fig, cluster_reason = _strain_cluster_fig(job_dir)
                if cluster_fig is not None:
                    _plotly_chart(cluster_fig, width="stretch", key=f"{key_prefix}_sp_cluster")
                else:
                    st.info(cluster_reason or "Cluster strain-path data unavailable")

        elif panel == "V&H":
            @st.fragment
            def _vh_content(_job_dir=job_dir, _kp=key_prefix):
                _stored_vh = _stored_vh_settings(_job_dir)
                _sw_default = int(_stored_vh.get("vh_smoothing_window") or 1)
                sw = st.number_input(
                    "V&H fit smoothing", min_value=1, max_value=101, value=_sw_default, step=2,
                    key=f"{_kp}_vh_smoothing",
                )

                fig_auto, reason_auto, _vh_data_auto = _volk_hora_dome_rate_fig(
                    _job_dir, smoothing_window=int(sw),
                )

                _stable_range = None
                _unstable_range = None
                _def_stable = _def_unstable = None
                if _vh_data_auto is not None:
                    _t_all = _vh_data_auto["t"]
                    _n = len(_t_all)
                    _fit_end = _vh_data_auto["fit"]["t_fit_end"] if _vh_data_auto.get("fit") else _t_all[-1]
                    _t_min = _vh_fit_start_time(_t_all[0], _fit_end)
                    _win = [i for i in range(1, _n - 1) if _t_all[i] >= _t_min]
                    if len(_win) > max(VH_MIN_STABLE_POINTS, VH_MIN_UNSTABLE_POINTS):
                        _fit_auto = _vh_data_auto["fit"]
                        _nsc = _fit_auto["stable"]["count"] if _fit_auto else max(VH_MIN_STABLE_POINTS, len(_win) // 2)
                        _nuc = _fit_auto["unstable"]["count"] if _fit_auto else max(VH_MIN_UNSTABLE_POINTS, len(_win) // 2)
                        _nsc = min(max(_nsc, VH_MIN_STABLE_POINTS), len(_win) - 1)
                        _nuc = min(max(_nuc, VH_MIN_UNSTABLE_POINTS), len(_win) - 1)
                        _def_stable = (_win[0], _win[_nsc - 1])
                        _def_unstable = (_win[len(_win) - _nuc], _win[-1])
                        _stable_key = f"{_kp}_vh_stable_range"
                        _unstable_key = f"{_kp}_vh_unstable_range"
                        if "stable_range" in _stored_vh and _stable_key not in st.session_state:
                            _s0, _s1 = _stored_vh["stable_range"]
                            st.session_state[_stable_key] = (
                                _nearest_index(_t_all, _s0),
                                _nearest_index(_t_all, _s1),
                            )
                        if "unstable_range" in _stored_vh and _unstable_key not in st.session_state:
                            _u0, _u1 = _stored_vh["unstable_range"]
                            st.session_state[_unstable_key] = (
                                _nearest_index(_t_all, _u0),
                                _nearest_index(_t_all, _u1),
                            )

                        # Seed state, then create the sliders without value=
                        # (both together trigger the yellow Streamlit warning).
                        st.session_state.setdefault(_stable_key, _def_stable)
                        st.session_state.setdefault(_unstable_key, _def_unstable)
                        _c1, _c2 = st.columns(2)
                        with _c1:
                            _is0, _is1 = st.slider(
                                "Stable fit window",
                                min_value=0, max_value=_n - 1,
                                key=_stable_key,
                                help="Green region — data used for the stable (pre-necking) line.",
                            )
                            _stable_range = (_t_all[_is0], _t_all[_is1])
                        with _c2:
                            _iu0, _iu1 = st.slider(
                                "Unstable fit window",
                                min_value=0, max_value=_n - 1,
                                key=_unstable_key,
                                help="Red region — data used for the unstable (post-necking) line.",
                            )
                            _unstable_range = (_t_all[_iu0], _t_all[_iu1])

                _using_auto = (
                    _stable_range is None
                    or (
                        _def_stable is not None and _def_unstable is not None
                        and (_is0, _is1) == _def_stable
                        and (_iu0, _iu1) == _def_unstable
                    )
                )
                if _using_auto:
                    fig, reason, _vh_data = fig_auto, reason_auto, _vh_data_auto
                else:
                    fig, reason, _vh_data = _volk_hora_dome_rate_fig(
                        _job_dir, smoothing_window=int(sw),
                        override_stable_range=_stable_range,
                        override_unstable_range=_unstable_range,
                    )
                if fig is not None:
                    _plotly_chart(fig, width="stretch", key=f"{_kp}_vh_rate")
                else:
                    st.info(reason or "V&H dome rate unavailable")

                with st.expander("Overwrite VH forming limit"):
                    fl_path = os.path.join(_job_dir, "forming_limits.csv")
                    if _vh_data is None or _vh_data["fit"] is None or not os.path.exists(fl_path):
                        st.info("No valid intersection — adjust the sliders above.")
                    else:
                        _fit = _vh_data["fit"]
                        _data = _vh_data["data"]
                        _tc = _fit["t_cross"]
                        _ks = _fit["kstable"]
                        _rr = _data.iloc[_ks]
                        _e1 = float(_rr["eps1_major"])
                        _e2 = float(_rr["eps2_minor"])
                        _eqps = float(_rr["EQPS"]) if "EQPS" in _rr.index else float("nan")
                        _d = float(_rr["D"]) if "D" in _rr.index else float("nan")

                        fl_df = _load_csv(fl_path).copy()
                        fl_df["time_s"] = pd.to_numeric(fl_df["time_s"], errors="coerce")
                        _vh_row = fl_df[fl_df["method"] == "volk_hora"]
                        if not _vh_row.empty:
                            _st = float(_vh_row["time_s"].iloc[0])
                            _se1 = float(pd.to_numeric(_vh_row["eps1_major"].iloc[0], errors="coerce"))
                            _se2 = float(pd.to_numeric(_vh_row["eps2_minor"].iloc[0], errors="coerce"))
                            st.caption(f"Stored: t = {_st:.4f} s  ε₁ = {_se1:.4f}  ε₂ = {_se2:.4f}")

                        _oc1, _oc2, _oc3 = st.columns(3)
                        _oc1.metric("t_cross (s)", f"{_tc:.4f}")
                        _oc2.metric("ε₁", f"{_e1:.4f}")
                        _oc3.metric("ε₂", f"{_e2:.4f}")

                        _u3 = float("nan")
                        _gl = _resolve_job_file(_job_dir, "global.csv")
                        if os.path.exists(_gl):
                            _gdf = _load_csv(_gl).copy()
                            _gdf["time_s"] = pd.to_numeric(_gdf["time_s"], errors="coerce")
                            _gdf["U3_mm"] = pd.to_numeric(_gdf["U3_mm"], errors="coerce")
                            _gdf = _gdf.dropna(subset=["time_s"])
                            if not _gdf.empty:
                                _u3 = float(_gdf.iloc[(_gdf["time_s"] - _tc).abs().argmin()]["U3_mm"])
                                st.caption(f"U3 = {_u3:.4f} mm")

                        if st.button("Overwrite", type="primary", key=f"{_kp}_vh_override_btn"):
                            _fw = _load_csv(fl_path).copy()
                            _mask = _fw["method"] == "volk_hora"
                            _upd = {"time_s": _tc, "eps1_major": _e1, "eps2_minor": _e2}
                            _saved_stable, _saved_unstable = _vh_ranges_from_fit(_fit, _vh_data["t"])
                            _upd["vh_smoothing_window"] = int(sw)
                            if _saved_stable is not None:
                                _upd["vh_stable_t0"] = float(_saved_stable[0])
                                _upd["vh_stable_t1"] = float(_saved_stable[1])
                            if _saved_unstable is not None:
                                _upd["vh_unstable_t0"] = float(_saved_unstable[0])
                                _upd["vh_unstable_t1"] = float(_saved_unstable[1])
                            if not math.isnan(_u3):
                                _upd["U3_mm"] = _u3
                            if not math.isnan(_eqps) and "EQPS" in _fw.columns:
                                _upd["EQPS"] = _eqps
                            if not math.isnan(_d) and "D" in _fw.columns:
                                _upd["D"] = _d
                            for _col in _upd:
                                if _col not in _fw.columns:
                                    _fw[_col] = ""
                            if _mask.any():
                                for _col, _val in _upd.items():
                                    if _col in _fw.columns:
                                        _fw.loc[_mask, _col] = _val
                            else:
                                _nr = {c: "" for c in _fw.columns}
                                _nr.update({"method": "volk_hora", "fracture_type": "dome"})
                                _nr.update(_upd)
                                _fw = pd.concat([_fw, pd.DataFrame([_nr])], ignore_index=True)
                            _fw.to_csv(fl_path, index=False)
                            _load_csv.clear()
                            st.success(f"Written → t = {_tc:.4f} s  ε₁ = {_e1:.4f}  ε₂ = {_e2:.4f}")

                            # Keep the static PDF and the Euler copy in step
                            # with the saved fit, so cluster-side re-plots and
                            # future sync-downs cannot clobber the override.
                            _push_files = [fl_path]
                            try:
                                with st.spinner("Regenerating postproc_plots.pdf…"):
                                    _n_pages = static_postproc_plots.write_job_pdf(_job_dir)
                                if _n_pages:
                                    _push_files.append(
                                        os.path.join(_job_dir, "postproc_plots.pdf"))
                            except Exception as _pdf_exc:
                                st.warning(f"postproc_plots.pdf not regenerated: {_pdf_exc}")
                            with st.spinner("Pushing override to Euler…"):
                                _pushed, _push_msg = _push_job_files_to_euler(
                                    _job_dir, _push_files)
                            if _pushed:
                                st.success(f"Pushed {len(_push_files)} file"
                                           f"{'s' if len(_push_files) > 1 else ''}"
                                           f" to Euler → {_push_msg}")
                            else:
                                st.warning(_push_msg)
            _vh_content()

        elif panel == "Forming Limits":
            fp = os.path.join(job_dir, "forming_limits.csv")
            if not os.path.exists(fp):
                st.info("forming_limits.csv not found")
            else:
                raw = _load_csv(fp)
                _METHOD_LABEL = {
                    "fracture": "Fracture",
                    "volk_hora": "Volk-Hora",
                    "sdv6": "SDV6/damage",
                }
                _PATH_LABEL = {
                    "critical_element": "Single element",
                    "volk_hora_selected_region": "V&H zone",
                    "fracture_neighborhood_selected_region": "Fracture neighbourhood",
                }
                rows = []
                for _, r in raw.iterrows():
                    method = str(r.get("method", ""))
                    ft = str(r.get("fracture_type", "—"))
                    ps_raw = str(r.get("path_source", ""))
                    ps = next((v for k, v in _PATH_LABEL.items() if ps_raw.startswith(k)), ps_raw)
                    valid = ft == "dome"
                    e1 = pd.to_numeric(r.get("eps1_major"), errors="coerce")
                    e2 = pd.to_numeric(r.get("eps2_minor"), errors="coerce")
                    t = pd.to_numeric(r.get("time_s"), errors="coerce")
                    u3 = pd.to_numeric(r.get("U3_mm"), errors="coerce")
                    rows.append({
                        "Criterion": _METHOD_LABEL.get(method, method),
                        "ε₁ major": round(float(e1), 4) if pd.notna(e1) else "—",
                        "ε₂ minor": round(float(e2), 4) if pd.notna(e2) else "—",
                        "Time [s]": round(float(t), 4) if pd.notna(t) else "—",
                        "U3 [mm]": round(float(u3), 2) if pd.notna(u3) else "—",
                        "Fracture zone": ft,
                        "Path source": ps,
                        "Valid": "✓" if valid else "✗",
                    })
                summary = pd.DataFrame(rows)

                def _style_row(row):
                    color = ("#14532d" if row["Valid"] == "✓" else "#7c2d12")
                    return [f"background-color: {color}; color: white"] * len(row)

                st.dataframe(
                    summary.style.apply(_style_row, axis=1),
                    width="stretch",
                    hide_index=True,
                )

        elif panel == "Cluster Loc.":
            st.caption("This diagnostic reads strain_cluster.csv and can be slow for large jobs.")
            fig, reason = _cluster_location_fig(job_dir)
            if fig is not None:
                _plotly_chart(fig, width="stretch", key=f"{key_prefix}_loc")
            else:
                st.info(reason or "Cluster location unavailable")


    # ══════════════════════════════════════════════════════════════════════════
    # Single Job view
    # ══════════════════════════════════════════════════════════════════════════
    if view_mode == "Single Job":

        @st.cache_data(show_spinner=False)
        def _job_table_df(job_items, token):
            """Overview table: one row per job with validity and media flags."""
            rows = []
            for name, path in job_items:
                ft, valid = "", ""
                fl = os.path.join(path, "forming_limits.csv")
                if os.path.exists(fl):
                    try:
                        df = pd.read_csv(fl)
                        r = df[df["method"] == "fracture"]
                        if not r.empty:
                            ft = str(r.iloc[0].get("fracture_type", "") or "")
                            valid = "✓" if ft == "dome" else "✗"
                    except Exception:
                        pass
                try:
                    has_movies = any(f.endswith(".webm") for f in os.listdir(path))
                except OSError:
                    has_movies = False
                rows.append({
                    "Job": name,
                    "Modified": time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(_job_mtime(path))),
                    "Fracture": ft or "—",
                    "Valid": valid or "—",
                    "Movies": "🎬" if has_movies else "",
                })
            return pd.DataFrame(rows)

        def _job_badges(job_dir):
            """Validity chips: fracture zone, quasi-static check, stored V&H."""
            badges = []
            _u3, ft = _fracture_u3(job_dir)
            if ft:
                badges.append(
                    ":green-badge[dome fracture]" if ft == "dome"
                    else f":red-badge[⚠ {ft} fracture]"
                )
            for fname in ("global.csv", "energy_data.csv"):
                fp = os.path.join(job_dir, fname)
                if not os.path.exists(fp):
                    continue
                try:
                    df = _load_csv(fp)
                except Exception:
                    break
                if "ALLKE" not in df.columns or "ALLIE" not in df.columns:
                    continue
                d = df[df["ALLIE"] > 0]
                d = d.iloc[max(1, int(len(d) * 0.02)):]
                if not d.empty:
                    peak = float((d["ALLKE"] / d["ALLIE"]).max())
                    badges.append(
                        f":green-badge[KE/IE {peak:.3f}]" if peak <= 0.05
                        else f":orange-badge[KE/IE {peak:.3f} > 5%]"
                    )
                break
            fl = os.path.join(job_dir, "forming_limits.csv")
            if os.path.exists(fl):
                try:
                    df = _load_csv(fl)
                    if "method" in df.columns and (df["method"] == "volk_hora").any():
                        badges.append(":blue-badge[V&H stored]")
                except Exception:
                    pass
            return badges

        @st.fragment
        def _single_job_view():
            job_options = list(job_dirs.keys())

            # Optional sortable table browser. It sits above the selectbox so a
            # row click can still set the selectbox state in the same run.
            if st.toggle(
                "Browse jobs as table",
                key="results_job_table_toggle",
                help="Sortable overview with modification date, fracture validity "
                     "and movie availability. Click a row to open the job.",
            ):
                tbl = _job_table_df(
                    tuple(sorted(job_dirs.items())),
                    st.session_state.get("results_scan_token", 0),
                )
                ev = st.dataframe(
                    tbl, width="stretch", hide_index=True, height=300,
                    on_select="rerun", selection_mode="single-row",
                    key="results_job_table",
                )
                rows = ev.selection.rows if ev is not None else []
                if rows:
                    picked = str(tbl.iloc[rows[0]]["Job"])
                    # Apply only when the row pick changed, so a stale table
                    # selection cannot fight the prev/next arrows.
                    if picked in job_dirs and \
                            st.session_state.get("_job_table_last_pick") != picked:
                        st.session_state["_job_table_last_pick"] = picked
                        st.session_state["results_single_job"] = picked

            def _shift_job(delta):
                cur = st.session_state.get("results_single_job")
                if cur in job_options:
                    idx = (job_options.index(cur) + delta) % len(job_options)
                    st.session_state["results_single_job"] = job_options[idx]

            c_prev, c_sel, c_next = st.columns([0.6, 8, 0.6], vertical_alignment="bottom")
            c_prev.button("◀", key="results_job_prev", width="stretch",
                          help="Previous job", on_click=_shift_job, args=(-1,))
            c_next.button("▶", key="results_job_next", width="stretch",
                          help="Next job", on_click=_shift_job, args=(1,))
            with c_sel:
                sel = _persisted_choice("Job", job_options, "results_single_job")
            if sel is None:
                return
            job_dir = job_dirs[sel]
            if st.query_params.get("job") != sel:
                st.query_params["job"] = sel

            badges = _job_badges(job_dir)
            if badges:
                st.markdown(" ".join(badges))

            # Remember the enclosing top-level folder for scoped Euler sync.
            _rel = os.path.relpath(os.path.abspath(job_dir), os.path.abspath(results_dir))
            if not _rel.startswith(".."):
                st.session_state["_results_sync_scope_dirs"] = [_rel.split(os.sep)[0]]

            _render_single_graph_download(sel, job_dir, job_dirs, key_prefix=f"single_{_safe_filename(sel)}")
            _render_job_media(job_dir)
            _render_job_tabs(job_dir, key_prefix=f"single_{sel}",
                             panel_state_key="results_panel_single")
            _render_pdf_downloads(job_dir, key_prefix=f"single_{sel}")

        _single_job_view()

    # ══════════════════════════════════════════════════════════════════════════
    # Unified FLD view
    # ══════════════════════════════════════════════════════════════════════════
    elif view_mode == "FLD":

        _FLC_COLORS = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
            "#9467bd", "#8c564b", "#e377c2", "#17becf",
        ]
        _FLC_DASHES = ["solid", "dash", "dashdot", "dot", "longdash", "longdashdot"]
        _FLC_MARKER_SYMBOLS = [
            "circle", "square", "diamond", "triangle-up",
            "cross", "star", "pentagon", "hexagram",
        ]

        def _flc_w(s):
            m = re.search(r"W(\d+)", str(s))
            return int(m.group(1)) if m else 0

        def _flc_set_label(dirname):
            m = re.match(r"(?:FLC_)?(\w+?)_t([\dp]+)_ang(\d+)(.*)", dirname)
            if not m:
                return dirname
            test = m.group(1).capitalize()
            thickness = m.group(2).replace("p", ".")
            angle = m.group(3)
            label = f"{test}  t = {thickness} mm"
            if angle != "0":
                label += f"  {angle}°"
            return label

        def _job_variant_name(name):
            return _plot_separator_key(name)

        def _job_variant_label(variant_key):
            parts = str(variant_key).split("|")
            if parts and parts[0] in ("Nakazima", "Marciniak", "PiP", "Test"):
                parts = parts[1:]
            return " > ".join(p for p in parts if p)

        def _sub_jobs_for_flc_dir(flc_dir, variant=None):
            out = {}
            try:
                entries = sorted(os.scandir(flc_dir), key=lambda e: e.name)
            except PermissionError:
                return out
            for entry in entries:
                if not entry.is_dir() or not _is_job_dir(entry.path):
                    continue
                if variant is not None and _job_variant_name(entry.name) != variant:
                    continue
                out[entry.name] = entry.path
            return _dedupe_jobs_by_parameters(out)

        def _has_forming_limits(jobs):
            return any(os.path.exists(os.path.join(path, "forming_limits.csv"))
                       for path in jobs.values())

        def _flc_source_options():
            options = {}

            def _is_under_flc_dir(path):
                abs_path = os.path.abspath(path)
                for flc_path in flc_dirs.values():
                    abs_flc = os.path.abspath(flc_path)
                    if abs_path == abs_flc:
                        continue
                    try:
                        if os.path.commonpath([abs_path, abs_flc]) == abs_flc:
                            return True
                    except ValueError:
                        continue
                return False

            def _sort_flc_jobs(jobs):
                deduped = _dedupe_jobs_by_parameters(jobs)
                return dict(sorted(deduped.items(), key=lambda kv: (_flc_w(kv[0]), kv[0])))

            def _merge_jobs(existing_jobs, new_jobs):
                merged = dict(existing_jobs)
                for job_label, job_path in new_jobs.items():
                    label = job_label
                    if label in merged and os.path.abspath(merged[label]) != os.path.abspath(job_path):
                        label = os.path.relpath(job_path, results_dir)
                    merged[label] = job_path
                return _sort_flc_jobs(merged)

            def _source_mtime(option):
                mtimes = [_job_mtime(path) for path in option.get("jobs", {}).values()]
                if mtimes:
                    return max(mtimes)
                return _job_mtime(option.get("path", ""))

            def _put_source(label, option):
                option = dict(option)
                option["jobs"] = _sort_flc_jobs(option.get("jobs", {}))
                if label in options:
                    existing = dict(options[label])
                    existing["jobs"] = _merge_jobs(existing.get("jobs", {}), option["jobs"])
                    if _source_mtime(option) >= _source_mtime(existing):
                        for key in ("kind", "path", "variant"):
                            if key in option:
                                existing[key] = option[key]
                    options[label] = existing
                else:
                    options[label] = option

            if job_dirs:
                direct_jobs = {
                    name: path
                    for name, path in job_dirs.items()
                    if _is_job_dir(path) and not _is_under_flc_dir(path)
                }
                if direct_jobs:
                    _put_source("Direct completed jobs", {
                        "kind": "direct",
                        "jobs": direct_jobs,
                    })

            for name, path in flc_dirs.items():
                jobs_all = _sub_jobs_for_flc_dir(path)
                if not jobs_all:
                    continue
                variants = sorted(set(_job_variant_name(n) for n in jobs_all))
                base_label = _flc_set_label(name)
                if len(variants) > 1:
                    for variant in variants:
                        jobs = _sub_jobs_for_flc_dir(path, variant=variant)
                        if not _has_forming_limits(jobs):
                            continue
                        variant_label = _job_variant_label(variant)
                        label = f"{base_label}  ({variant_label})" if variant_label else base_label
                        _put_source(label, {
                            "kind": "set",
                            "path": path,
                            "variant": variant,
                            "jobs": jobs,
                        })
                else:
                    variant = variants[0] if variants else None
                    if not _has_forming_limits(jobs_all):
                        continue
                    variant_label = _job_variant_label(variant) if variant else ""
                    label = f"{base_label}  ({variant_label})" if variant_label else base_label
                    _put_source(label, {
                        "kind": "set",
                        "path": path,
                        "variant": variant,
                        "jobs": jobs_all,
                    })
            return options

        def _limit_point(job_name, job_dir, method):
            fp = os.path.join(job_dir, "forming_limits.csv")
            if not os.path.exists(fp):
                return None
            try:
                df = _load_csv(fp)
            except Exception:
                return None
            if "method" not in df.columns:
                return None
            rows = df[df["method"] == method]
            if rows.empty:
                return None
            r = rows.iloc[0]
            e1 = pd.to_numeric(r.get("eps1_major"), errors="coerce")
            e2 = pd.to_numeric(r.get("eps2_minor"), errors="coerce")
            if pd.isna(e1) or pd.isna(e2):
                return None
            fracture_type = r.get("fracture_type", "dome")
            fracture_type = "dome" if pd.isna(fracture_type) else str(fracture_type)
            return {
                "name": job_name,
                "dir": job_dir,
                "method": method,
                "e1": float(e1),
                "e2": float(e2),
                "fracture_type": fracture_type,
                "valid": fracture_type == "dome",
                "time": pd.to_numeric(r.get("time_s"), errors="coerce"),
                "zone_n": pd.to_numeric(r.get("vh_zone_n"), errors="coerce"),
            }

        def _limit_points(jobs, method):
            points = []
            for name, path in jobs.items():
                point = _limit_point(name, path, method)
                if point is not None:
                    points.append(point)
            points.sort(key=lambda p: p["e2"])
            return points

        def _job_label(job_name):
            m = re.search(r"W\d+", job_name)
            return m.group(0) if m else job_name

        def _add_fld_reference_lines(fig, x0, x1):
            fig.add_trace(go.Scatter(
                x=[x0, 0], y=[-2 * x0, 0], mode="lines",
                name="Uniaxial tension",
                legendgroup="_guides", legendgrouptitle_text="Reference",
                line=dict(color="lightgray", width=1.2, dash="dashdot"),
                hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=[0, x1], y=[0, x1], mode="lines",
                name="Equibiaxial",
                legendgroup="_guides",
                line=dict(color="lightgray", width=1.2, dash="dash"),
                hoverinfo="skip",
            ))

        def _build_unified_flc_fig(selected_sources, source_options, show_vh_flc,
                                   show_paths):
            fig = go.Figure()
            all_e1, all_e2 = [], []
            path_indices = []
            no_data = []
            no_optional = []

            for source_idx, source_label in enumerate(selected_sources):
                source = source_options[source_label]
                jobs = source["jobs"]
                color = _FLC_COLORS[source_idx % len(_FLC_COLORS)]
                marker = _FLC_MARKER_SYMBOLS[source_idx % len(_FLC_MARKER_SYMBOLS)]
                source_has_data = False

                if show_paths:
                    for job_name, job_dir in jobs.items():
                        e1_path, e2_path = _job_strain_path(job_dir)
                        if e1_path:
                            all_e1.extend(e1_path)
                            all_e2.extend(e2_path)
                            path_indices.append(len(fig.data))
                            fig.add_trace(go.Scatter(
                                x=e2_path, y=e1_path, mode="lines",
                                visible=True, showlegend=False, hoverinfo="skip",
                                line=dict(color=color, width=1, dash="dot"),
                                opacity=0.35,
                            ))

                fflc_points = _limit_points(jobs, "fracture")
                if fflc_points:
                    source_has_data = True
                    all_e1.extend(p["e1"] for p in fflc_points)
                    all_e2.extend(p["e2"] for p in fflc_points)
                    valid_fflc = [p for p in fflc_points if p["valid"]]
                    invalid_fflc = [p for p in fflc_points if not p["valid"]]
                    trace_name = (
                        f"{source_label} (FFLC)"
                        if len(selected_sources) > 1 else "FFLC"
                    )
                    if valid_fflc:
                        fig.add_trace(go.Scatter(
                            x=[p["e2"] for p in valid_fflc],
                            y=[p["e1"] for p in valid_fflc],
                            mode="lines+markers",
                            name=trace_name,
                            legendgroup=f"{source_label}_fflc",
                            text=[_job_label(p["name"]) for p in valid_fflc],
                            hovertemplate=(
                                "%{text}<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}"
                                "<extra>FFLC</extra>"
                            ),
                            line=dict(color=color, width=2.5, dash="solid"),
                            marker=dict(size=8, color=color, symbol=marker),
                            opacity=0.9,
                        ))
                    if invalid_fflc:
                        fig.add_trace(go.Scatter(
                            x=[p["e2"] for p in invalid_fflc],
                            y=[p["e1"] for p in invalid_fflc],
                            mode="markers",
                            name=f"{trace_name} diagnostics",
                            legendgroup=f"{source_label}_fflc",
                            text=[
                                f"{_job_label(p['name'])}<br>{p['fracture_type']}"
                                for p in invalid_fflc
                            ],
                            hovertemplate=(
                                "%{text}<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}"
                                "<extra>excluded from FLC</extra>"
                            ),
                            marker=dict(size=10, color=color, symbol="x", line=dict(width=2)),
                            opacity=0.9,
                        ))

                optional = _limit_points(jobs, "volk_hora") if show_vh_flc else []
                if optional:
                    source_has_data = True
                    all_e1.extend(p["e1"] for p in optional)
                    all_e2.extend(p["e2"] for p in optional)
                    valid_optional = [p for p in optional if p["valid"]]
                    invalid_optional = [p for p in optional if not p["valid"]]
                    if show_paths:
                        for p in optional:
                            if "path_e1" not in p:
                                continue
                            path_indices.append(len(fig.data))
                            fig.add_trace(go.Scatter(
                                x=p["path_e2"], y=p["path_e1"], mode="lines",
                                visible=True, showlegend=False, hoverinfo="skip",
                                line=dict(color=color, width=1.2),
                                opacity=0.35,
                            ))
                    trace_name = (
                        f"{source_label} (FLC)"
                        if len(selected_sources) > 1 else "FLC"
                    )
                    if valid_optional:
                        fig.add_trace(go.Scatter(
                            x=[p["e2"] for p in valid_optional],
                            y=[p["e1"] for p in valid_optional],
                            mode="lines+markers",
                            name=trace_name,
                            legendgroup=f"{source_label}_flc",
                            text=[_job_label(p["name"]) for p in valid_optional],
                            hovertemplate=(
                                "%{text}<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}"
                                "<extra>FLC: V&H tab source</extra>"
                            ),
                            line=dict(
                                color=color,
                                width=2.1,
                                dash=_FLC_DASHES[(source_idx + 1) % len(_FLC_DASHES)],
                            ),
                            marker=dict(size=7, color=color, symbol="diamond"),
                        ))
                    if invalid_optional:
                        fig.add_trace(go.Scatter(
                            x=[p["e2"] for p in invalid_optional],
                            y=[p["e1"] for p in invalid_optional],
                            mode="markers",
                            name=f"{trace_name} diagnostics",
                            legendgroup=f"{source_label}_flc",
                            text=[
                                f"{_job_label(p['name'])}<br>{p['fracture_type']}"
                                for p in invalid_optional
                            ],
                            hovertemplate=(
                                "%{text}<br>ε₂=%{x:.4f}<br>ε₁=%{y:.4f}"
                                "<extra>excluded from FLC</extra>"
                            ),
                            marker=dict(size=9, color=color, symbol="x", line=dict(width=2)),
                        ))
                elif show_vh_flc:
                    no_optional.append(source_label)

                if not source_has_data:
                    no_data.append(source_label)

            if all_e1 and all_e2:
                pad = 0.18
                xr = max(abs(min(all_e2)), abs(max(all_e2)), 1e-6)
                x0, x1 = -(1 + pad) * xr, (1 + pad) * xr
                y0 = min(0.0, min(all_e1)) - pad * (max(all_e1) - min(all_e1) + 1e-6)
                y1 = max(all_e1) + pad * (max(all_e1) - min(all_e1) + 1e-6)
            else:
                x0, x1, y0, y1 = -0.5, 0.5, 0.0, 1.0

            _add_fld_reference_lines(fig, x0, x1)
            theme = _plot_theme()
            style = _streamlit_plot_style(theme)
            fig.update_xaxes(
                tickfont=dict(color=style["axis"]),
                title_font=dict(color=style["axis"]),
                linecolor=style["axis"],
                gridcolor=style["grid"],
                zerolinecolor=style["grid"],
            )
            fig.update_yaxes(
                tickfont=dict(color=style["axis"]),
                title_font=dict(color=style["axis"]),
                linecolor=style["axis"],
                gridcolor=style["grid"],
                zerolinecolor=style["grid"],
            )
            fig.update_layout(
                xaxis=dict(title="ε₂  minor strain  (-)", range=[x0, x1]),
                yaxis=dict(title="ε₁  major strain  (-)", range=[y0, y1]),
                title="Forming Limit Diagram",
                legend_title="Source / method",
                hovermode="closest",
                template=theme["template"],
                height=550,
                paper_bgcolor=style["transparent"],
                plot_bgcolor=style["transparent"],
                font=dict(color=style["axis"]),
            )
            fig.add_vline(x=0, line_width=0.6, line_dash="dot", line_color=style["guide"])
            fig.add_hline(y=0, line_width=0.6, line_dash="dot", line_color=style["guide"])
            return fig, path_indices, no_data, no_optional

        def _flc_source_options_cached():
            """Memoize the source scan — it does one scandir/listdir per FLC dir
            and per job, which is too slow to repeat on every widget rerun."""
            key = (
                results_dir,
                st.session_state.get("results_scan_token", 0),
                tuple(sorted(flc_dirs.items())),
                tuple(sorted(job_dirs.items())),
            )
            cached = st.session_state.get("_flc_source_options_memo")
            if cached is not None and cached[0] == key:
                return cached[1]
            options = _flc_source_options()
            st.session_state["_flc_source_options_memo"] = (key, options)
            return options

        @st.fragment
        def _flc_view():
            source_options = _flc_source_options_cached()
            if not source_options:
                st.info("No FLD data found. Sync from Euler or run post-processing first.")
                return

            selected_sources = st.multiselect(
                "FLD source",
                list(source_options.keys()),
                default=[],
                key="results_flc_sources_empty_default",
            )
            if not selected_sources:
                st.info("Select at least one FLD source.")
                return

            # Remember the FLC folders behind the current selection for scoped sync.
            _scope_dirs = []
            for _lbl in selected_sources:
                _src = source_options[_lbl]
                if _src.get("kind") == "set" and _src.get("path"):
                    _rel = os.path.relpath(os.path.abspath(_src["path"]),
                                           os.path.abspath(results_dir))
                else:
                    _rel = None
                if _rel and not _rel.startswith(".."):
                    _scope_dirs.append(_rel.split(os.sep)[0])
                else:
                    for _jd in _src.get("jobs", {}).values():
                        _jrel = os.path.relpath(os.path.abspath(_jd),
                                                os.path.abspath(results_dir))
                        if not _jrel.startswith(".."):
                            _scope_dirs.append(_jrel.split(os.sep)[0])
            if _scope_dirs:
                st.session_state["_results_sync_scope_dirs"] = sorted(set(_scope_dirs))

            c_flc, c_paths = st.columns([3, 1])
            with c_flc:
                show_vh_flc = st.checkbox(
                    "Show optional FLD from V&H tab source",
                    value=True,
                    help="Uses the stored method='volk_hora' row in forming_limits.csv. "
                         "The V&H tab's Overwrite button updates this exact source.",
                    key="results_flc_show_vh_overlay",
                )
            with c_paths:
                show_paths = st.checkbox(
                    "Show strain paths",
                    value=False,
                    help="Add strain paths directly to the FLD plot.",
                    key="results_flc_show_paths",
                )

            # Memoize the unified FLD figure on the underlying CSV mtimes.
            _sig = []
            for _lbl in selected_sources:
                for _jd in source_options[_lbl]["jobs"].values():
                    for _f in ("forming_limits.csv", "strain_path.csv", "elout.csv"):
                        _fp = os.path.join(_jd, _f)
                        try:
                            _sig.append((_fp, os.path.getmtime(_fp)))
                        except OSError:
                            _sig.append((_fp, None))
            _memo = st.session_state.setdefault("_results_fig_memo", {})
            _key = (
                "fld_unified", tuple(selected_sources), bool(show_vh_flc),
                bool(show_paths), tuple(_sig), _plot_theme()["base"],
            )
            if _key not in _memo:
                if len(_memo) >= 48:
                    _memo.clear()
                _memo[_key] = _build_unified_flc_fig(
                    selected_sources, source_options, show_vh_flc, show_paths,
                )
            flc_fig, path_indices, no_data, no_optional = _memo[_key]
            _plotly_chart(flc_fig, width="stretch")
            if no_data:
                st.caption("No usable forming-limit CSV data for: " + ", ".join(no_data))
            if no_optional and show_vh_flc:
                st.caption("No optional FLD overlay data for: " + ", ".join(no_optional))

            _render_fld_graph_download(selected_sources, source_options, key_prefix="flc_unified")

            if len(selected_sources) == 1:
                source_label = selected_sources[0]
                source = source_options[source_label]
                jobs = source["jobs"]
                if jobs:
                    st.markdown("---")
                    st.subheader("Individual Job")
                    selected_job = _persisted_choice(
                        "Job",
                        list(jobs.keys()),
                        "results_flc_job",
                    )
                    if selected_job:
                        job_dir = jobs[selected_job]
                        _render_single_graph_download(
                            selected_job,
                            job_dir,
                            jobs,
                            key_prefix=f"flc_single_{_safe_filename(source_label)}_{_safe_filename(selected_job)}",
                        )
                        _render_job_media(job_dir)
                        _render_job_tabs(
                            job_dir,
                            key_prefix=f"flc_unified_{source_label}_{selected_job}",
                            panel_state_key="results_panel_flc",
                        )
                        _render_pdf_downloads(
                            job_dir,
                            key_prefix=f"flc_unified_{source_label}_{selected_job}",
                        )

        _flc_view()

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
                    remote_cmd = (
                        f"sacct --format=JobName%100,Elapsed,State --noheader "
                        f"--parsable2 -S 2026-01-01 -u {shlex.quote(_current_user())} "
                        "| grep -v '\\.batch' | grep -v '\\.extern'"
                    )
                    result = _run_ssh_command(
                        _ssh_command(f"{_current_user()}@{_current_host()}", remote_cmd, connect_timeout=8),
                        timeout=_ssh_timeout(default_normal=120, default_key_only=30),
                    )
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
                width="stretch", hide_index=True,
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
                _s_theme = _plot_theme()
                _s_ps = _streamlit_plot_style(_s_theme)
                fig.update_xaxes(tickfont=dict(color=_s_ps["axis"]), title_font=dict(color=_s_ps["axis"]),
                                 linecolor=_s_ps["axis"], gridcolor=_s_ps["grid"], zerolinecolor=_s_ps["grid"])
                fig.update_yaxes(tickfont=dict(color=_s_ps["axis"]), title_font=dict(color=_s_ps["axis"]),
                                 linecolor=_s_ps["axis"], gridcolor=_s_ps["grid"], zerolinecolor=_s_ps["grid"])
                fig.update_layout(
                    xaxis_title="Punch displacement U3 [mm]",
                    yaxis_title="Thinning strain ε₁ + ε₂",
                    title=title, template=_s_theme["template"],
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    paper_bgcolor=_s_ps["transparent"],
                    plot_bgcolor=_s_ps["transparent"],
                    font=dict(color=_s_ps["axis"]),
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
                ), width="stretch")

            # ── Mass-scaling sensitivity: fix mr, vary ms_dt ─────────────────
            if len(all_ms) > 1:
                st.markdown(f"#### Thinning vs U3 — mass-scaling  (mr = {sel_mr_str})")
                _plotly_chart(_thinning_curve_fig(
                    "mr", sel_mr, "ms", all_ms,
                    f"Mass-scaling sensitivity (mr = {sel_mr_str})",
                ), width="stretch")

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
                _ke_theme = _plot_theme()
                _ke_ps = _streamlit_plot_style(_ke_theme)
                fig_ke.update_xaxes(tickfont=dict(color=_ke_ps["axis"]), title_font=dict(color=_ke_ps["axis"]),
                                    linecolor=_ke_ps["axis"], gridcolor=_ke_ps["grid"], zerolinecolor=_ke_ps["grid"])
                fig_ke.update_yaxes(tickfont=dict(color=_ke_ps["axis"]), title_font=dict(color=_ke_ps["axis"]),
                                    linecolor=_ke_ps["axis"], gridcolor=_ke_ps["grid"], zerolinecolor=_ke_ps["grid"])
                fig_ke.update_layout(
                    xaxis_title="Punch displacement U3 [mm]",
                    yaxis_title="ALLKE / ALLIE [%]",
                    title=f"Quasi-staticity check (mr = {sel_mr_str})",
                    template=_ke_theme["template"],
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    paper_bgcolor=_ke_ps["transparent"],
                    plot_bgcolor=_ke_ps["transparent"],
                    font=dict(color=_ke_ps["axis"]),
                )
                _plotly_chart(fig_ke, width="stretch")

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
                st.dataframe(df_map, width="stretch")
                st.caption(
                    f"Δthin = max thinning deviation from reference "
                    f"(mr={int(ref_mr)}, dt={ref_ms:.0e}).  ○ = partial run."
                )


# ══════════════════════════════════════════════════════════════════════════════
# Navigation (top bar)
# ══════════════════════════════════════════════════════════════════════════════
_nav = st.navigation(
    [
        st.Page(_page_submit_job, title="Submit Job", icon="🚀",
                url_path="submit", default=True),
        st.Page(_page_job_status, title="Job Status", icon="📊",
                url_path="status"),
        st.Page(_page_results, title="Results", icon="📈",
                url_path="results"),
    ],
    position="top",
)
_nav.run()
