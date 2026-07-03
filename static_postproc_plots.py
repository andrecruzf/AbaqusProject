# -*- coding: utf-8 -*-
"""Static post-processing plots for the Euler pipeline.

This module intentionally avoids Streamlit and pandas. It is used by the
batch-side plotting scripts to create reproducible PDF figures from CSV output.
"""
from __future__ import annotations

import csv
import math
import os
import re
from typing import Iterable

os.environ.setdefault("MPLCONFIGDIR", os.path.join("/tmp", "abaqusproject-matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

try:
    from config import POSTPROC_THRESHOLDS
except Exception:
    POSTPROC_THRESHOLDS = {}


MATLAB_COLORS = [
    "#0072BD", "#D95319", "#EDB120", "#7E2F8E",
    "#77AC30", "#4DBEEE", "#A2142F",
]

METHOD_STYLE = {
    "fracture": ("X", 8, "Fracture"),
    "volk_hora": ("D", 6, "V&H"),
    "sdv6": ("s", 6, "SDV6"),
}


def _cfg_float(key: str, default: float) -> float:
    try:
        return float(POSTPROC_THRESHOLDS.get(key, default))
    except Exception:
        return float(default)


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(POSTPROC_THRESHOLDS.get(key, default))
    except Exception:
        return int(default)


def _safe_label(label: object, max_len: int = 64) -> str:
    text = str(label)
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


def _width_from_name(name: object) -> int:
    m = re.search(r"W(\d+)", str(name), flags=re.I)
    return int(m.group(1)) if m else 0


def _plot_test_type_label(text: object) -> str:
    s = str(text).lower()
    if "marc" in s:
        return "Marciniak"
    if "pip" in s:
        return "PiP"
    if "naka" in s or "nakazima" in s:
        return "Nakazima"
    return "Test"


def _plot_separator_meta(text: object, assume_default_mr: bool = False,
                         assume_default_ps: bool = False) -> dict[str, str]:
    base = os.path.basename(os.path.normpath(str(text)))
    base = base[4:] if base.startswith("FLC_") else base
    punch_match = re.search(r"(?:^|_)(?:Naka|Marc)(\d+)", base, flags=re.I)
    if not punch_match:
        punch_match = re.search(r"_pdia([\dp]+)", base, flags=re.I)
    mass_match = re.search(r"_ms(\d+e\d+)(?=_|$)", base, flags=re.I)
    mesh_match = re.search(r"_mr([\dp]+)(?=_|$)", base, flags=re.I)
    nt_match = re.search(r"_nt(\d+)(?=_|$)", base, flags=re.I)
    ps_match = re.search(r"(?:^|_)ps([\dp]+)(?=_|$)", base, flags=re.I)
    return {
        "test_type": _plot_test_type_label(base),
        "punch": "P%s" % punch_match.group(1) if punch_match else "",
        "ms": "ms%s" % mass_match.group(1) if mass_match else "",
        "mr": "mr%s" % mesh_match.group(1) if mesh_match else ("mr1" if assume_default_mr else ""),
        "nt": "nt%s" % nt_match.group(1) if nt_match else "",
        "ps": "ps%s" % ps_match.group(1) if ps_match else ("ps5" if assume_default_ps else ""),
    }


def _plot_separator_label(text: object, assume_default_mr: bool = False,
                          assume_default_ps: bool = False) -> str:
    meta = _plot_separator_meta(
        text,
        assume_default_mr=assume_default_mr,
        assume_default_ps=assume_default_ps,
    )
    return " > ".join(meta[k] for k in ("punch", "ms", "mr", "nt", "ps") if meta[k])


def _fld_title(source_names: Iterable[object]) -> str:
    names = [str(n) for n in source_names if str(n)]
    joined = " ".join(names)
    title = "FLD - " + _plot_test_type_label(joined)
    separators: list[str] = []
    for name in names:
        sep = _plot_separator_label(name)
        if sep and sep not in separators:
            separators.append(sep)
    if separators:
        title += " > " + ", ".join(separators[:3])
        if len(separators) > 3:
            title += ", +%d" % (len(separators) - 3)
    return title


def _read_rows(path: str) -> list[dict[str, str]]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", newline="") as fh:
        return list(csv.DictReader(fh))


def _to_float(value: object, default: float = math.nan) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _column(rows: list[dict[str, str]], name: str) -> list[float]:
    return [_to_float(row.get(name)) for row in rows]


def _clean_xy(x: Iterable[float], y: Iterable[float]) -> tuple[list[float], list[float]]:
    xs: list[float] = []
    ys: list[float] = []
    for xv, yv in zip(x, y):
        if math.isfinite(xv) and math.isfinite(yv):
            xs.append(float(xv))
            ys.append(float(yv))
    return xs, ys


def _read_csv_with_required(job_dir: str, names: Iterable[str],
                            required: Iterable[str]) -> tuple[list[dict[str, str]], str | None]:
    required = tuple(required)
    for name in names:
        path = os.path.join(job_dir, name)
        rows = _read_rows(path)
        if not rows:
            continue
        if all(col in rows[0] for col in required):
            return rows, name
    return [], None


def _limits(job_dir: str) -> dict[str, dict[str, object]]:
    rows = _read_rows(os.path.join(job_dir, "forming_limits.csv"))
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        method = str(row.get("method", "")).strip()
        if not method:
            continue
        out[method] = {
            "e1": _to_float(row.get("eps1_major")),
            "e2": _to_float(row.get("eps2_minor")),
            "eqps": _to_float(row.get("EQPS")),
            "time_s": _to_float(row.get("time_s")),
            "u3": _to_float(row.get("U3_mm")),
            "fracture_type": str(row.get("fracture_type", "") or ""),
        }
    return out


def _interpolate(xs: list[float], ys: list[float], x0: float) -> float:
    clean_x, clean_y = _clean_xy(xs, ys)
    if not clean_x or len(clean_x) != len(clean_y):
        return math.nan
    pairs = sorted(zip(clean_x, clean_y), key=lambda p: p[0])
    if x0 <= pairs[0][0]:
        return pairs[0][1]
    if x0 >= pairs[-1][0]:
        return pairs[-1][1]
    for (xa, ya), (xb, yb) in zip(pairs, pairs[1:]):
        if xa <= x0 <= xb:
            if abs(xb - xa) < 1e-15:
                return ya
            a = (x0 - xa) / (xb - xa)
            return ya + a * (yb - ya)
    return math.nan


def _fracture_u3(job_dir: str) -> tuple[float | None, str]:
    lims = _limits(job_dir)
    frac = lims.get("fracture")
    if not frac:
        return None, ""
    fracture_type = str(frac.get("fracture_type") or "")
    u3 = float(frac.get("u3", math.nan))
    if math.isfinite(u3):
        return u3, fracture_type
    t_frac = float(frac.get("time_s", math.nan))
    if not math.isfinite(t_frac):
        return None, fracture_type
    rows, _ = _read_csv_with_required(job_dir, ("punch_fd.csv", "global.csv"), ("U3_mm",))
    if not rows:
        return None, fracture_type
    time_col = "total_time_s" if "total_time_s" in rows[0] else "time_s"
    if time_col not in rows[0]:
        return None, fracture_type
    u3 = _interpolate(_column(rows, time_col), _column(rows, "U3_mm"), t_frac)
    return (u3 if math.isfinite(u3) else None), fracture_type


def _style_rc() -> None:
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


def _new_figure(nrows: int = 1, figsize: tuple[float, float] = (6.9, 4.4),
                sharex: bool = False):
    _style_rc()
    fig, axes = plt.subplots(nrows=nrows, ncols=1, figsize=figsize, sharex=sharex)
    fig.patch.set_facecolor("white")
    if nrows == 1:
        axes = [axes]
    return fig, axes


def _style_axis(ax, xlabel: str | None = None, ylabel: str | None = None,
                title: str | None = None) -> None:
    ax.set_facecolor("white")
    ax.grid(True, which="major", axis="both", linestyle="--",
            color="gray", linewidth=0.5, alpha=0.5, zorder=0)
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


def _style_legend(ax, loc: str = "best", ncol: int = 1, bbox_to_anchor=None) -> None:
    handles, labels = ax.get_legend_handles_labels()
    keep = [(h, label) for h, label in zip(handles, labels) if label and not label.startswith("_")]
    if not keep:
        return
    handles, labels = zip(*keep)
    legend = ax.legend(handles, labels, loc=loc, ncol=ncol,
                       bbox_to_anchor=bbox_to_anchor, frameon=True,
                       edgecolor="black", fancybox=False)
    if legend:
        legend.get_frame().set_facecolor("white")


def _data_limits(e1: list[float], e2: list[float], pad: float = 0.18):
    e1, e2 = _clean_xy(e1, e2)
    if not e1 or not e2:
        return None
    x_min, x_max = min(e2), max(e2)
    y_min, y_max = min(e1), max(e1)
    x_span = max(x_max - x_min, 0.15)
    y_span = max(y_max - y_min, 0.15)
    x0 = min(x_min - pad * x_span, -0.05)
    x1 = max(x_max + pad * x_span, 0.05)
    y0 = min(0.0, y_min - pad * y_span)
    y1 = y_max + pad * y_span
    return x0, x1, y0, y1


def _strain_path(job_dir: str) -> tuple[list[float], list[float]]:
    for fname, c1, c2 in (
        ("strain_path.csv", "eps1_major", "eps2_minor"),
        ("elout.csv", "eps1_le", "eps2_le"),
    ):
        rows = _read_rows(os.path.join(job_dir, fname))
        if rows and c1 in rows[0] and c2 in rows[0]:
            return _clean_xy(_column(rows, c1), _column(rows, c2))
    return [], []


def _strain_path_frame(job_dir: str) -> dict[str, list[float]]:
    rows = _read_rows(os.path.join(job_dir, "strain_path.csv"))
    if not rows or not {"time_s", "eps1_major", "eps2_minor"} <= set(rows[0]):
        return {}
    cols = [
        "time_s", "eps1_major", "eps2_minor", "EQPS", "TRIAX", "D",
        "thinning_rate",
    ]
    out = {col: _column(rows, col) for col in cols if col in rows[0]}
    keep = [
        i for i, (t, e1, e2) in enumerate(zip(
            out["time_s"], out["eps1_major"], out["eps2_minor"],
        ))
        if math.isfinite(t) and math.isfinite(e1) and math.isfinite(e2)
    ]
    return {col: [vals[i] for i in keep] for col, vals in out.items()}


def _thinning_rate(frame: dict[str, list[float]]) -> list[float]:
    if "thinning_rate" in frame and any(math.isfinite(v) for v in frame["thinning_rate"]):
        return frame["thinning_rate"]
    t = frame.get("time_s", [])
    thinning = [
        e1 + e2 for e1, e2 in zip(frame.get("eps1_major", []), frame.get("eps2_minor", []))
    ]
    n = len(t)
    if n < 2:
        return [0.0 for _ in thinning]
    rate: list[float] = []
    for i in range(n):
        if i == 0:
            dt = t[1] - t[0]
            dv = thinning[1] - thinning[0]
        elif i == n - 1:
            dt = t[-1] - t[-2]
            dv = thinning[-1] - thinning[-2]
        else:
            dt = t[i + 1] - t[i - 1]
            dv = thinning[i + 1] - thinning[i - 1]
        rate.append(dv / dt if abs(dt) > 1e-15 else math.nan)
    return rate


def _moving_average(values: list[float], window: int) -> list[float]:
    window = max(1, int(window))
    if window <= 1 or len(values) < 3:
        return values[:]
    half = window // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        vals = [v for v in values[lo:hi] if math.isfinite(v)]
        out.append(sum(vals) / len(vals) if vals else math.nan)
    return out


def _line_fit(xs: list[float], ys: list[float]):
    xs, ys = _clean_xy(xs, ys)
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if abs(den) < 1e-20:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    intercept = my - slope * mx
    mse = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)) / n
    return slope, intercept, mse


def _nearest_index(values: list[float], target: float) -> int | None:
    finite = [(i, v) for i, v in enumerate(values) if math.isfinite(v)]
    if not finite or not math.isfinite(target):
        return None
    return min(finite, key=lambda iv: abs(iv[1] - target))[0]


def _volk_hora_fit(t: list[float], rate: list[float]):
    if len(t) < 4 or len(t) != len(rate):
        return None
    t_fit_end = t[-1]
    fit_window_seconds = max(0.0, _cfg_float("vh_fit_window_seconds", 2.0))
    unstable_tail_points = max(0, _cfg_int("vh_unstable_tail_points", 4))
    unstable_window_seconds = max(0.0, _cfg_float("vh_unstable_fit_window_seconds", 0.6))
    fit_window_frac = max(0.1, min(1.0, _cfg_float("vh_fit_window_frac", 0.4)))
    min_stable = max(2, _cfg_int("vh_min_stable_points", 20))
    min_unstable = max(2, _cfg_int("vh_min_unstable_points", 4))

    if fit_window_seconds > 0.0:
        t_min_stable = max(t[0], t_fit_end - fit_window_seconds)
    else:
        t_min_stable = t[0] + (1.0 - fit_window_frac) * (t_fit_end - t[0])
    stable_idx = [
        i for i in range(1, len(t) - 1)
        if t[i] >= t_min_stable and t[i] <= t_fit_end and math.isfinite(rate[i])
    ]
    if unstable_tail_points > 0:
        unstable_idx = [i for i in range(1, len(t) - 1) if math.isfinite(rate[i])][-unstable_tail_points:]
    else:
        if unstable_window_seconds > 0.0:
            t_min_unstable = max(t[0], t_fit_end - unstable_window_seconds)
        else:
            t_min_unstable = t_min_stable
        unstable_idx = [
            i for i in range(1, len(t) - 1)
            if t[i] >= t_min_unstable and t[i] <= t_fit_end and math.isfinite(rate[i])
        ]
    if len(stable_idx) <= min_stable or len(unstable_idx) < min_unstable:
        return None

    stable_x = [t[i] for i in stable_idx]
    stable_y = [rate[i] for i in stable_idx]
    unstable_x = [t[i] for i in unstable_idx]
    unstable_y = [rate[i] for i in unstable_idx]

    stable_best = None
    stable_candidates = range(min_stable, len(stable_x))
    for count in stable_candidates:
        fit = _line_fit(stable_x[:count], stable_y[:count])
        if fit is None:
            continue
        score = fit[2] * count / max(count - 1, 1)
        if stable_best is None or score < stable_best[0]:
            stable_best = (score, count, fit)
    if stable_best is None:
        fit = _line_fit(stable_x, stable_y)
        if fit is None:
            return None
        stable_best = (fit[2], len(stable_x), fit)

    if unstable_tail_points > 0:
        unstable_candidates = [(0, len(unstable_x))]
    else:
        unstable_candidates = [
            (start, len(unstable_x) - start)
            for start in range(1, len(unstable_x) - min_unstable + 1)
        ]
    unstable_best = None
    for start, count in unstable_candidates:
        fit = _line_fit(unstable_x[start:start + count], unstable_y[start:start + count])
        if fit is None:
            continue
        score = fit[2] * count / max(count - 1, 1)
        if unstable_best is None or score < unstable_best[0]:
            unstable_best = (score, start, count, fit)
    if unstable_best is None:
        return None

    _, ns, (ss, si, smse) = stable_best
    _, ustart, nu, (us, ui, umse) = unstable_best
    denom = ss - us
    if abs(denom) < 1e-20:
        return None
    t_cross = (ui - si) / denom
    kcrit = _nearest_index(t, t_cross)
    if kcrit is None:
        return None
    return {
        "t_cross": t_cross,
        "kcrit": kcrit,
        "kstable": max(0, kcrit - 1),
        "stable": {"slope": ss, "intercept": si, "count": ns, "mse": smse},
        "unstable": {"slope": us, "intercept": ui, "count": nu, "mse": umse},
        "t_fit_start": min(stable_x[0], unstable_x[ustart]),
        "t_fit_end": max(stable_x[ns - 1], unstable_x[ustart + nu - 1]),
    }


def _dic_instable_index(t_values: list[float], t_cross: float) -> int | None:
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


def _stored_vh_settings(job_dir: str) -> dict[str, object]:
    """User-saved V&H fit settings from the app's Overwrite button.

    The Streamlit app persists the adjusted fit windows into the volk_hora row
    of forming_limits.csv; when present they override the automatic fit so the
    batch PDF reproduces the user-approved fit.
    """
    rows = _read_rows(os.path.join(job_dir, "forming_limits.csv"))
    for row in rows:
        if str(row.get("method", "")).strip() != "volk_hora":
            continue
        stable = (_to_float(row.get("vh_stable_t0")), _to_float(row.get("vh_stable_t1")))
        unstable = (_to_float(row.get("vh_unstable_t0")), _to_float(row.get("vh_unstable_t1")))
        if not all(math.isfinite(v) for v in stable + unstable):
            return {}
        smoothing = _to_float(row.get("vh_smoothing_window"), 1.0)
        return {
            "stable_range": stable,
            "unstable_range": unstable,
            "smoothing_window": int(smoothing) if math.isfinite(smoothing) else 1,
        }
    return {}


def _vh_fit_from_ranges(t: list[float], rate: list[float],
                        stable_range: tuple[float, float],
                        unstable_range: tuple[float, float]):
    ts0, ts1 = stable_range
    tu0, tu1 = unstable_range
    min_stable = max(2, _cfg_int("vh_min_stable_points", 20))
    min_unstable = max(2, _cfg_int("vh_min_unstable_points", 4))
    stable_idx = [i for i in range(len(t)) if ts0 <= t[i] <= ts1]
    unstable_idx = [i for i in range(len(t)) if tu0 <= t[i] <= tu1]
    if len(stable_idx) < min_stable or len(unstable_idx) < min_unstable:
        return None
    stable_fit = _line_fit([t[i] for i in stable_idx], [rate[i] for i in stable_idx])
    unstable_fit = _line_fit([t[i] for i in unstable_idx], [rate[i] for i in unstable_idx])
    if not stable_fit or not unstable_fit:
        return None
    ss, si, _ = stable_fit
    us, ui, _ = unstable_fit
    denom = ss - us
    if abs(denom) < 1e-20:
        return None
    t_cross = (ui - si) / denom
    kcrit = _dic_instable_index(t, t_cross)
    if kcrit is None or kcrit <= 0:
        return None
    return {
        "t_cross": t_cross,
        "kcrit": kcrit,
        "kstable": kcrit - 1,
        "stable": {"slope": ss, "intercept": si, "count": len(stable_idx), "mse": 0.0},
        "unstable": {"slope": us, "intercept": ui, "count": len(unstable_idx), "mse": 0.0},
        "t_fit_start": min(ts0, tu0),
        "t_fit_end": max(ts1, tu1),
    }


def build_force_displacement_figure(job_dir: str, job_name: str | None = None):
    rows, _ = _read_csv_with_required(job_dir, ("global.csv", "punch_fd.csv"), ("U3_mm", "RF3_N"))
    if not rows:
        return None
    x, y = _clean_xy(_column(rows, "U3_mm"), _column(rows, "RF3_N"))
    if not x:
        return None
    fig, axes = _new_figure(figsize=(6.9, 4.2))
    ax = axes[0]
    ax.plot(x, y, color=MATLAB_COLORS[0], linewidth=1.7, label="Punch force")
    u3_frac, fracture_type = _fracture_u3(job_dir)
    if u3_frac is not None:
        label = "Fracture (%s)" % fracture_type if fracture_type else "Fracture"
        ax.axvline(float(u3_frac), color="#A2142F", linestyle="--", linewidth=1.1, label=label)
    _style_axis(
        ax,
        xlabel="Punch displacement U3 [mm]",
        ylabel="Punch force RF3 [N]",
        title="Force-displacement - %s" % _safe_label(job_name or os.path.basename(job_dir)),
    )
    _style_legend(ax)
    fig.tight_layout()
    return fig


def _time_or_displacement_axis(rows: list[dict[str, str]], job_dir: str):
    if "U3_mm" in rows[0]:
        x = _column(rows, "U3_mm")
        if any(math.isfinite(v) for v in x):
            return x, "Punch displacement U3 [mm]", "u3"
    time_col = "total_time_s" if "total_time_s" in rows[0] else "time_s"
    if time_col in rows[0]:
        return _column(rows, time_col), "Time [s]", "time"
    return None, None, None


def build_energy_history_figure(job_dir: str, job_name: str | None = None):
    rows, _ = _read_csv_with_required(job_dir, ("global.csv", "energy_data.csv"), ("ALLKE", "ALLIE"))
    if not rows:
        return None
    x, xlabel, axis_kind = _time_or_displacement_axis(rows, job_dir)
    if x is None:
        return None
    allke = _column(rows, "ALLKE")
    allie = _column(rows, "ALLIE")
    clean = [
        (xv, ke, ie) for xv, ke, ie in zip(x, allke, allie)
        if math.isfinite(xv) and math.isfinite(ke) and math.isfinite(ie) and abs(ie) > 1e-12
    ]
    if not clean:
        return None
    if len(clean) > 10:
        clean = clean[max(1, int(0.02 * len(clean))):]
    x_vals = [v[0] for v in clean]
    ke_vals = [v[1] for v in clean]
    ie_vals = [v[2] for v in clean]
    ratio_pct = [100.0 * ke / ie for ke, ie in zip(ke_vals, ie_vals)]

    fig, axes = _new_figure(nrows=2, figsize=(6.9, 5.4), sharex=True)
    axes[0].plot(x_vals, ke_vals, color=MATLAB_COLORS[0], linewidth=1.5, label="ALLKE")
    axes[0].plot(x_vals, ie_vals, color=MATLAB_COLORS[1], linewidth=1.5, label="ALLIE")
    _style_axis(
        axes[0],
        ylabel="Energy",
        title="Energy history - %s" % _safe_label(job_name or os.path.basename(job_dir)),
    )
    _style_legend(axes[0])

    axes[1].plot(x_vals, ratio_pct, color=MATLAB_COLORS[2], linewidth=1.5, label="ALLKE / ALLIE")
    axes[1].axhline(5.0, color="black", linestyle="--", linewidth=1.0, label="5% limit")
    if axis_kind == "u3":
        u3_frac, _ = _fracture_u3(job_dir)
        if u3_frac is not None:
            axes[1].axvline(float(u3_frac), color="#A2142F", linestyle="--", linewidth=1.0, label="Fracture")
    _style_axis(axes[1], xlabel=xlabel, ylabel="ALLKE / ALLIE [%]")
    _style_legend(axes[1])
    fig.tight_layout()
    return fig


def build_strain_path_figure(job_dir: str, job_name: str | None = None):
    e1, e2 = _strain_path(job_dir)
    if not e1:
        return None
    fig, axes = _new_figure(figsize=(6.9, 4.8))
    ax = axes[0]
    limits = _limits(job_dir)
    ax.plot(e2, e1, color=MATLAB_COLORS[0], linewidth=1.5, label="Strain path")
    for method, (marker, size, label) in METHOD_STYLE.items():
        point = limits.get(method)
        if not point:
            continue
        p_e1 = float(point.get("e1", math.nan))
        p_e2 = float(point.get("e2", math.nan))
        if not (math.isfinite(p_e1) and math.isfinite(p_e2)):
            continue
        color = {"fracture": "#A2142F", "volk_hora": "#77AC30", "sdv6": "#D95319"}.get(method, "black")
        ax.plot(p_e2, p_e1, marker=marker, color=color, linestyle="None",
                markersize=size, label=label)
    lims = _data_limits(e1, e2)
    if lims:
        x0, x1, y0, y1 = lims
        ax.plot([x0, 0.0], [-2.0 * x0, 0.0], color="silver", linestyle="-.", linewidth=0.9, label="_uniaxial")
        ax.plot([0.0, x1], [0.0, x1], color="silver", linestyle="--", linewidth=0.9, label="_equibiaxial")
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
    ax.axvline(0.0, linewidth=0.8, color="silver", zorder=0)
    ax.axhline(0.0, linewidth=0.8, color="silver", zorder=0)
    _style_axis(
        ax,
        xlabel="Minor strain e2 [-]",
        ylabel="Major strain e1 [-]",
        title="Strain path - %s" % _safe_label(job_name or os.path.basename(job_dir)),
    )
    _style_legend(ax)
    fig.tight_layout()
    return fig


def build_vh_figure(job_dir: str, job_name: str | None = None):
    frame = _strain_path_frame(job_dir)
    if not frame or len(frame.get("time_s", [])) < 4:
        return None
    t = frame["time_s"]
    rate = _thinning_rate(frame)
    fit = None
    used_rate = rate
    smoothing_used = 1
    fit_saved = False
    stored = _stored_vh_settings(job_dir)
    if stored:
        smoothing_used = max(1, int(stored.get("smoothing_window", 1)))
        candidate = _moving_average(rate, smoothing_used)
        fit = _vh_fit_from_ranges(t, candidate, stored["stable_range"], stored["unstable_range"])
        if fit is not None:
            used_rate = candidate
            fit_saved = True
    if fit is None:
        smoothing_used = 1
        for window in (1, 5, 11, 21):
            candidate = _moving_average(rate, window)
            fit = _volk_hora_fit(t, candidate)
            if fit is not None:
                used_rate = candidate
                smoothing_used = window
                break
    _style_rc()
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 4.2))
    fig.patch.set_facecolor("white")
    ax = axes[0]
    ax_zoom = axes[1]
    zoom_start = max(min(t), max(t) - max(0.0, _cfg_float("vh_fit_window_seconds", 2.0)))
    label = "Thinning rate" if smoothing_used == 1 else "Thinning rate (%d pt mean)" % smoothing_used
    ax.plot(t, used_rate, color=MATLAB_COLORS[0], linewidth=1.5, label=label)
    ax_zoom.plot(t, used_rate, color=MATLAB_COLORS[0], linewidth=1.5, label="_rate")
    if fit is not None:
        stable = fit["stable"]
        unstable = fit["unstable"]
        ts = [fit["t_fit_start"], fit["t_cross"]]
        ys = [stable["slope"] * tv + stable["intercept"] for tv in ts]
        tu = [fit["t_cross"], fit["t_fit_end"]]
        yu = [unstable["slope"] * tv + unstable["intercept"] for tv in tu]
        fit_suffix = " (saved)" if fit_saved else ""
        ax.plot(ts, ys, color="#77AC30", linewidth=1.4, label="Stable fit" + fit_suffix)
        ax.plot(tu, yu, color="#A2142F", linewidth=1.4, label="Unstable fit" + fit_suffix)
        z_ts = [max(zoom_start, fit["t_fit_start"]), max(zoom_start, fit["t_cross"])]
        z_tu = [max(zoom_start, fit["t_cross"]), fit["t_fit_end"]]
        if z_ts[1] > z_ts[0]:
            ax_zoom.plot(
                z_ts,
                [stable["slope"] * tv + stable["intercept"] for tv in z_ts],
                color="#77AC30",
                linewidth=1.4,
                label="_stable",
            )
        if z_tu[1] > z_tu[0]:
            ax_zoom.plot(
                z_tu,
                [unstable["slope"] * tv + unstable["intercept"] for tv in z_tu],
                color="#A2142F",
                linewidth=1.4,
                label="_unstable",
            )
        k = fit["kstable"]
        if 0 <= k < len(t):
            ax.axvline(t[k], color="black", linestyle=":", linewidth=1.0, label="t_necking")
            ax_zoom.axvline(t[k], color="black", linestyle=":", linewidth=1.0, label="_necking")
            e1 = frame.get("eps1_major", [math.nan])[k]
            e2 = frame.get("eps2_minor", [math.nan])[k]
            ax_zoom.text(
                0.03, 0.96,
                "e1=%.4f   e2=%.4f   t_necking=%.4f s" % (e1, e2, t[k]),
                transform=ax_zoom.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox=dict(facecolor="white", edgecolor="black", linewidth=0.6, alpha=0.9),
            )
    for plot_ax in axes:
        _style_axis(plot_ax, xlabel="Time [s]")
    ax.set_ylabel("d(e1+e2)/dt [1/s]")
    ax.set_title("Volk-Hora", pad=8)
    ax_zoom.set_title("Volk-Hora - last 2 seconds", pad=8)
    ax_zoom.set_xlim(zoom_start, max(t))
    zoom_vals = [v for tv, v in zip(t, used_rate) if tv >= zoom_start and math.isfinite(v)]
    if fit is not None:
        z_ts = [max(zoom_start, fit["t_fit_start"]), max(zoom_start, fit["t_cross"])]
        z_tu = [max(zoom_start, fit["t_cross"]), fit["t_fit_end"]]
        for tv in z_ts if z_ts[1] > z_ts[0] else []:
            zoom_vals.append(fit["stable"]["slope"] * tv + fit["stable"]["intercept"])
        for tv in z_tu if z_tu[1] > z_tu[0] else []:
            zoom_vals.append(fit["unstable"]["slope"] * tv + fit["unstable"]["intercept"])
    if zoom_vals:
        zmin, zmax = min(zoom_vals), max(zoom_vals)
        span = max(zmax - zmin, 1e-6)
        ax_zoom.set_ylim(zmin - 0.10 * span, zmax + 0.18 * span)
    _style_legend(ax)
    fig.suptitle("Volk-Hora - %s" % _safe_label(job_name or os.path.basename(job_dir)), y=1.02)
    fig.tight_layout()
    return fig


def build_triaxiality_figure(job_dir: str, job_name: str | None = None):
    frame = _strain_path_frame(job_dir)
    if not frame or "TRIAX" not in frame:
        return None
    triax = frame["TRIAX"]
    if "EQPS" in frame and any(math.isfinite(v) for v in frame["EQPS"]):
        x, y = _clean_xy(frame["EQPS"], triax)
        xlabel = "Equivalent plastic strain EQPS [-]"
    else:
        x, y = _clean_xy(frame["time_s"], triax)
        xlabel = "Time [s]"
    if not x:
        return None
    fig, axes = _new_figure(figsize=(6.9, 4.2))
    ax = axes[0]
    ax.plot(x, y, color=MATLAB_COLORS[0], linewidth=1.5, label="Triaxiality eta")
    for eta, label in (
        (1.0 / 3.0, "Uniaxial eta=1/3"),
        (0.577, "Plane strain eta~0.577"),
        (2.0 / 3.0, "Equibiaxial eta=2/3"),
    ):
        ax.axhline(eta, color="gray", linestyle="--", linewidth=0.8, alpha=0.7, label=label)
    _style_axis(
        ax,
        xlabel=xlabel,
        ylabel="Triaxiality eta [-]",
        title="Stress-state path - %s" % _safe_label(job_name or os.path.basename(job_dir)),
    )
    _style_legend(ax)
    fig.tight_layout()
    return fig


def build_job_figures(job_dir: str) -> list:
    job_name = os.path.basename(os.path.normpath(job_dir))
    builders = (
        build_force_displacement_figure,
        build_energy_history_figure,
        build_strain_path_figure,
        build_vh_figure,
        build_triaxiality_figure,
    )
    figs = []
    for builder in builders:
        fig = builder(job_dir, job_name)
        if fig is not None:
            figs.append(fig)
    return figs


def write_job_pdf(job_dir: str, output_path: str | None = None) -> int:
    figs = build_job_figures(job_dir)
    if not figs:
        return 0
    output_path = output_path or os.path.join(job_dir, "postproc_plots.pdf")
    with PdfPages(output_path) as pdf:
        for fig in figs:
            pdf.savefig(fig, bbox_inches="tight", facecolor="white")
    for fig in figs:
        plt.close(fig)
    return len(figs)


def _forming_limit_point(job_dir: str, method: str):
    point = _limits(job_dir).get(method)
    if not point:
        return None
    e1 = float(point.get("e1", math.nan))
    e2 = float(point.get("e2", math.nan))
    if not (math.isfinite(e1) and math.isfinite(e2)):
        return None
    fracture_type = str(point.get("fracture_type") or "")
    return {
        "dir": job_dir,
        "name": os.path.basename(os.path.normpath(job_dir)),
        "e1": e1,
        "e2": e2,
        "valid": fracture_type in ("", "dome"),
        "fracture_type": fracture_type or "dome",
    }


def build_fld_figure(job_dirs: list[str], title: str | None = None,
                     include_vh: bool = True, show_paths: bool = True,
                     experimental_points: list[tuple[float, float]] | None = None):
    job_dirs = sorted(job_dirs, key=lambda d: (_width_from_name(d), os.path.basename(d)))
    fig, axes = _new_figure(figsize=(7.2, 4.8))
    ax = axes[0]
    all_e1: list[float] = []
    all_e2: list[float] = []
    plotted = False

    for i, job_dir in enumerate(job_dirs):
        color = MATLAB_COLORS[i % len(MATLAB_COLORS)]
        if show_paths:
            e1_path, e2_path = _strain_path(job_dir)
            if e1_path:
                all_e1.extend(e1_path)
                all_e2.extend(e2_path)
                ax.plot(e2_path, e1_path, linestyle=":", color=color,
                        linewidth=0.7, alpha=0.35, label="_strain_path")

    fracture = [p for p in (_forming_limit_point(d, "fracture") for d in job_dirs) if p]
    valid_fracture = [p for p in fracture if p["valid"]]
    invalid_fracture = [p for p in fracture if not p["valid"]]
    if valid_fracture:
        all_e1.extend(p["e1"] for p in valid_fracture)
        all_e2.extend(p["e2"] for p in valid_fracture)
        ax.plot([p["e2"] for p in valid_fracture], [p["e1"] for p in valid_fracture],
                "-o", color=MATLAB_COLORS[0], linewidth=1.6, markersize=4.5,
                label="FFLC")
        plotted = True
    if invalid_fracture:
        all_e1.extend(p["e1"] for p in invalid_fracture)
        all_e2.extend(p["e2"] for p in invalid_fracture)
        ax.plot([p["e2"] for p in invalid_fracture], [p["e1"] for p in invalid_fracture],
                linestyle="None", marker="x", color=MATLAB_COLORS[0],
                markersize=6, label="FFLC diagnostics")
        plotted = True

    if include_vh:
        vh = [p for p in (_forming_limit_point(d, "volk_hora") for d in job_dirs) if p and p["valid"]]
        if vh:
            all_e1.extend(p["e1"] for p in vh)
            all_e2.extend(p["e2"] for p in vh)
            ax.plot([p["e2"] for p in vh], [p["e1"] for p in vh],
                    "--D", color=MATLAB_COLORS[1], linewidth=1.2,
                    markersize=4, label="FLC V&H")
            plotted = True

    if experimental_points:
        e2_exp = [p[0] for p in experimental_points]
        e1_exp = [p[1] for p in experimental_points]
        all_e1.extend(e1_exp)
        all_e2.extend(e2_exp)
        ax.plot(e2_exp, e1_exp, marker="*", color="black", linestyle="None",
                markersize=8, label="Reference")
        plotted = True

    if not plotted:
        plt.close(fig)
        return None

    lims = _data_limits(all_e1, all_e2)
    if lims:
        x0, x1, y0, y1 = lims
    else:
        x0, x1, y0, y1 = -0.5, 0.5, 0.0, 1.0
    ax.plot([x0, 0.0], [-2.0 * x0, 0.0], color="silver", linestyle="-.",
            linewidth=0.9, label="_uniaxial")
    ax.plot([0.0, x1], [0.0, x1], color="silver", linestyle="--",
            linewidth=0.9, label="_equibiaxial")
    ax.axvline(0.0, linewidth=0.8, color="silver", zorder=0)
    ax.axhline(0.0, linewidth=0.8, color="silver", zorder=0)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    _style_axis(
        ax,
        xlabel="Minor strain e2 [-]",
        ylabel="Major strain e1 [-]",
        title=title or _fld_title([os.path.basename(os.path.normpath(d)) for d in job_dirs]),
    )
    _style_legend(ax, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.30))
    fig.subplots_adjust(bottom=0.28)
    return fig


def write_fld_pdf(job_dirs: list[str], output_path: str,
                  experimental_points: list[tuple[float, float]] | None = None) -> int:
    fig = build_fld_figure(job_dirs, experimental_points=experimental_points)
    if fig is None:
        return 0
    with PdfPages(output_path) as pdf:
        pdf.savefig(fig, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return 1
