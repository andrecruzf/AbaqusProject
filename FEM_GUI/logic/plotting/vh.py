from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from app.constants import FEM_GUI_DIR

_mpl_dir = FEM_GUI_DIR / ".cache" / "matplotlib"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

from matplotlib.figure import Figure

from .style import apply_standard_axes


VH_ALPHA = 0.55
VH_SEED_COUNT = 50
VH_EVAL_BACK_FRAMES = 2
VH_FIT_WINDOW_SECONDS = max(0.0, float(os.environ.get("POSTPROC_VH_FIT_WINDOW_SECONDS", "2.0")))
VH_UNSTABLE_TAIL_POINTS = max(0, int(os.environ.get("POSTPROC_VH_UNSTABLE_TAIL_POINTS", "4")))
VH_UNSTABLE_FIT_WINDOW_SECONDS = max(0.0, float(os.environ.get("POSTPROC_VH_UNSTABLE_FIT_WINDOW_SECONDS", "0.6")))
VH_FIT_WINDOW_FRAC = max(0.1, min(1.0, float(os.environ.get("POSTPROC_VH_FIT_WINDOW_FRAC", "0.4"))))
VH_MIN_STABLE_POINTS = max(2, int(os.environ.get("POSTPROC_VH_MIN_STABLE_POINTS", "20")))
VH_MIN_UNSTABLE_POINTS = max(2, int(os.environ.get("POSTPROC_VH_MIN_UNSTABLE_POINTS", "4")))


def dome_rate(job_dir: Path, cache) -> tuple[Figure | None, str]:
    """V&H thinning-rate signal for one job, from strain_path.csv.

    Uses the stored fit windows from forming_limits.csv when present, otherwise
    retries the automatic two-line fit over increasing smoothing windows.
    """
    path = Path(job_dir) / "strain_path.csv"
    if not path.exists():
        return None, "strain_path.csv not found"
    df = cache.read(path)
    required = {"time_s", "eps1_major", "eps2_minor"}
    if not required <= set(df.columns):
        return None, "strain_path.csv missing time_s/eps1_major/eps2_minor"
    cols = [c for c in ("time_s", "eps1_major", "eps2_minor", "thinning_rate") if c in df.columns]
    data = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["time_s", "eps1_major", "eps2_minor"])
    data = data.groupby("time_s", as_index=False).mean().sort_values("time_s")
    if len(data) < 5:
        return None, "Not enough pre-fracture frames for a V&H fit"

    t = data["time_s"].astype(float).tolist()
    if "thinning_rate" in data.columns and data["thinning_rate"].notna().all():
        raw_rate = data["thinning_rate"].astype(float).tolist()
    else:
        strain_sum = (data["eps1_major"] + data["eps2_minor"]).astype(float).tolist()
        raw_rate = _thinning_rate(t, strain_sum)

    fit = None
    rate = raw_rate
    smoothing_used = 1
    stored = _stored_vh_settings(job_dir, cache)
    if "stable_range" in stored and "unstable_range" in stored:
        smoothing_used = int(stored.get("vh_smoothing_window") or 1)
        rate = _moving_average(raw_rate, smoothing_used)
        fit = _fit_from_ranges(t, rate, stored["stable_range"], stored["unstable_range"])
    if fit is None:
        for window in (1, 5, 11, 21):
            candidate = _moving_average(raw_rate, window)
            fit = _volk_hora_fit(t, candidate)
            if fit is not None:
                rate = candidate
                smoothing_used = window
                break

    fig = Figure(figsize=(9.5, 4.4), dpi=100)
    overview = fig.add_subplot(121)
    zoom = fig.add_subplot(122)
    fig.patch.set_facecolor("white")
    rate_label = "thinning rate" if smoothing_used == 1 else f"thinning rate ({smoothing_used} pt mean)"
    for ax in (overview, zoom):
        ax.plot(t, rate, color="#2563eb", linewidth=1.2, marker=".", markersize=3, label=rate_label)
    if fit is not None:
        stable = fit["stable"]
        unstable = fit["unstable"]
        tx = np.array([fit["t_fit_start"], fit["t_fit_end"]])
        for ax in (overview, zoom):
            ax.plot(tx, stable["slope"] * tx + stable["intercept"], color="seagreen", linewidth=1.2, label="stable fit")
            ax.plot(tx, unstable["slope"] * tx + unstable["intercept"], color="firebrick", linewidth=1.2, label="unstable fit")
            ax.scatter([fit["t_cross"]], [fit["y_cross"]], marker="x", s=48, color="#D19A3A", zorder=5, label="intersection")
        zoom.set_xlim(fit["t_fit_start"], fit["t_fit_end"])
        row = data.iloc[fit["kstable"]]
        e1 = float(row["eps1_major"])
        e2 = float(row["eps2_minor"])
        zoom.text(
            0.03,
            0.98,
            f"e1 = {e1:.4f}   e2 = {e2:.4f}   t_necking = {t[fit['kstable']]:.4f} s",
            transform=zoom.transAxes,
            va="top",
            family="monospace",
            fontsize=9,
            bbox=dict(facecolor="white", edgecolor="silver", alpha=0.8),
        )
        title = "Volk-Hora - last 2 seconds"
    else:
        title = "Fit unavailable for this signal"
    apply_standard_axes(overview, "Time [s]", r"Thinning rate $d(e_1+e_2)/dt$ [1/s]", "Volk-Hora")
    apply_standard_axes(zoom, "Time [s]", "", title)
    overview.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    return fig, ""


def _stored_vh_settings(job_dir: Path, cache) -> dict[str, Any]:
    path = Path(job_dir) / "forming_limits.csv"
    if not path.exists():
        return {}
    try:
        df = cache.read(path)
    except Exception:
        return {}
    if "method" not in df.columns:
        return {}
    rows = df[df["method"].astype(str) == "volk_hora"]
    if rows.empty:
        return {}
    row = rows.iloc[0]

    def _num(col: str) -> float | None:
        if col not in row.index:
            return None
        value = pd.to_numeric(row.get(col), errors="coerce")
        return float(value) if pd.notna(value) else None

    settings: dict[str, Any] = {"vh_smoothing_window": _num("vh_smoothing_window")}
    stable = (_num("vh_stable_t0"), _num("vh_stable_t1"))
    unstable = (_num("vh_unstable_t0"), _num("vh_unstable_t1"))
    if all(v is not None for v in stable + unstable):
        settings["stable_range"] = stable
        settings["unstable_range"] = unstable
    return settings


def _fit_from_ranges(
    t: list[float],
    rate: list[float],
    stable_range: tuple[float, float],
    unstable_range: tuple[float, float],
) -> dict[str, Any] | None:
    ts0, ts1 = stable_range
    tu0, tu1 = unstable_range
    stable_idx = [i for i in range(len(t)) if ts0 <= t[i] <= ts1]
    unstable_idx = [i for i in range(len(t)) if tu0 <= t[i] <= tu1]
    if len(stable_idx) < 2 or len(unstable_idx) < 2:
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
        "t_fit_start": min(ts0, tu0),
        "t_fit_end": max(ts1, tu1),
        "t_cross": t_cross,
        "y_cross": ss * t_cross + si,
        "kcrit": kcrit,
        "kstable": kcrit - 1,
        "stable": {"slope": ss, "intercept": si, "count": len(stable_idx), "mse": 0.0},
        "unstable": {"slope": us, "intercept": ui, "count": len(unstable_idx), "mse": 0.0},
    }


def auto_anchor(csv_path: Path) -> tuple[float, float] | None:
    data, reason = _prepare_paths(csv_path)
    if data is None:
        return None
    k_eval = _eval_index(len(data["times"]))
    best = max(data["paths"], key=lambda pid: data["paths"][pid]["rate"][k_eval])
    return data["centroids"][best]


def connected_zone(
    csv_path: Path,
    anchor_x: float | None = None,
    anchor_y: float | None = None,
    smoothing_window: int = 20,
    alpha: float = VH_ALPHA,
) -> tuple[Figure | None, str, dict[str, Any]]:
    prepared, reason = _prepare_paths(csv_path)
    if prepared is None:
        return None, reason, {}

    times = prepared["times"]
    paths = prepared["paths"]
    centroids = prepared["centroids"]
    k_eval = _eval_index(len(times))
    rates_eval = sorted([paths[pid]["rate"][k_eval] for pid in paths], reverse=True)
    top_n = min(VH_SEED_COUNT, len(rates_eval))
    rep_max = sum(rates_eval[:top_n]) / float(top_n)
    threshold = float(alpha) * rep_max
    hot = [pid for pid in paths if paths[pid]["rate"][k_eval] >= threshold]
    if not hot:
        return None, "No high-thinning-rate candidates found.", {}

    conn_radius = _connection_radius(list(paths), centroids)
    components = _connected_components(hot, centroids, conn_radius)
    anchor = (anchor_x, anchor_y) if anchor_x is not None and anchor_y is not None else None
    zone = max(components, key=lambda comp: _component_score(comp, paths, centroids, k_eval, anchor))

    rep_rate = []
    rep_e1 = []
    rep_e2 = []
    for idx in range(len(times)):
        rep_rate.append(float(np.mean([paths[pid]["rate"][idx] for pid in zone])))
        rep_e1.append(float(np.mean([paths[pid]["e1"][idx] for pid in zone])))
        rep_e2.append(float(np.mean([paths[pid]["e2"][idx] for pid in zone])))
    rate_for_fit = _moving_average(rep_rate, smoothing_window)
    fit = _volk_hora_fit(times, rate_for_fit)

    fig = Figure(figsize=(9.5, 4.6), dpi=100)
    left = fig.add_subplot(121)
    right = fig.add_subplot(122)
    fig.patch.set_facecolor("white")

    all_xy = np.array([centroids[pid] for pid in paths], dtype=float)
    hot_xy = np.array([centroids[pid] for pid in hot], dtype=float)
    zone_xy = np.array([centroids[pid] for pid in zone], dtype=float)
    left.scatter(all_xy[:, 0], all_xy[:, 1], s=7, color="#B8B8B8", label="all paths")
    left.scatter(hot_xy[:, 0], hot_xy[:, 1], s=12, color="#D19A3A", label="high rate")
    left.scatter(zone_xy[:, 0], zone_xy[:, 1], s=18, color="#007A96", label="connected zone")
    if anchor:
        left.scatter([anchor[0]], [anchor[1]], s=60, marker="x", color="#D85757", linewidths=1.5, label="anchor")
    left.set_aspect("equal", adjustable="box")
    apply_standard_axes(left, "x [mm]", "y [mm]", "Connected V&H zone")
    left.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=8)

    right.plot(times, rate_for_fit, color="#007A96", linewidth=1.1, label="zone signal")
    summary: dict[str, Any] = {
        "zone_paths": len(zone),
        "hot_paths": len(hot),
        "alpha": alpha,
        "connection_radius": conn_radius,
        "fit": "unavailable",
    }
    if fit is not None:
        stable = fit["stable"]
        unstable = fit["unstable"]
        ts = np.array([fit["t_fit_start"], fit["t_cross"]])
        tu = np.array([fit["t_cross"], fit["t_fit_end"]])
        right.plot(ts, stable["slope"] * ts + stable["intercept"], color="seagreen", linewidth=1, label="stable fit")
        right.plot(tu, unstable["slope"] * tu + unstable["intercept"], color="firebrick", linewidth=1, label="unstable fit")
        right.scatter([fit["t_cross"]], [fit["y_cross"]], marker="x", s=48, color="#D19A3A", label="intersection")
        kstable = fit["kstable"]
        summary.update(
            {
                "fit": "available",
                "vh_time_s": times[kstable],
                "vh_eps1": rep_e1[kstable],
                "vh_eps2": rep_e2[kstable],
            }
        )
    apply_standard_axes(right, "Time [s]", r"Mean thinning rate $d(e_1+e_2)/dt$ [1/s]", "Volk-Hora signal")
    right.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=8)
    fig.tight_layout()
    return fig, "", summary


def _prepare_paths(csv_path: Path) -> tuple[dict[str, Any] | None, str]:
    if not Path(csv_path).exists():
        return None, "DIC CSV file not found."
    df = pd.read_csv(csv_path)
    column_map = _column_map(df.columns)
    missing = [name for name in ("time", "x", "y", "e1", "e2", "path") if name not in column_map]
    if missing:
        return None, "CSV is missing required columns: " + ", ".join(missing)
    data = pd.DataFrame(
        {
            "time": pd.to_numeric(df[column_map["time"]], errors="coerce"),
            "x": pd.to_numeric(df[column_map["x"]], errors="coerce"),
            "y": pd.to_numeric(df[column_map["y"]], errors="coerce"),
            "e1": pd.to_numeric(df[column_map["e1"]], errors="coerce"),
            "e2": pd.to_numeric(df[column_map["e2"]], errors="coerce"),
            "path": df[column_map["path"]].astype(str),
        }
    )
    if "ip" in column_map:
        data["path"] = data["path"] + "_IP" + df[column_map["ip"]].astype(str)
    data = data.dropna(subset=["time", "x", "y", "e1", "e2"])
    if data.empty:
        return None, "CSV has no usable numeric DIC rows."
    data = data.sort_values(["path", "time"])
    times = sorted(data["time"].dropna().unique().tolist())
    if len(times) < 5:
        return None, "At least five time frames are required for V&H analysis."

    paths: dict[str, dict[str, list[float]]] = {}
    centroids: dict[str, tuple[float, float]] = {}
    for pid, grp in data.groupby("path"):
        grp = grp.drop_duplicates(subset=["time"]).sort_values("time")
        if len(grp) != len(times):
            continue
        if any(abs(float(a) - float(b)) > 1e-9 for a, b in zip(grp["time"].tolist(), times)):
            continue
        e1 = grp["e1"].astype(float).tolist()
        e2 = grp["e2"].astype(float).tolist()
        rate = _thinning_rate(times, [a + b for a, b in zip(e1, e2)])
        paths[str(pid)] = {"e1": e1, "e2": e2, "rate": rate}
        centroids[str(pid)] = (float(grp["x"].iloc[0]), float(grp["y"].iloc[0]))
    if len(paths) < 3:
        return None, "Not enough complete DIC paths with matching time frames."
    return {"times": times, "paths": paths, "centroids": centroids}, ""


def _column_map(columns: Iterable[str]) -> dict[str, str]:
    lookup = {col.lower().strip(): col for col in columns}

    def first(*names: str) -> str | None:
        for name in names:
            if name.lower() in lookup:
                return lookup[name.lower()]
        return None

    mapping = {}
    for key, names in {
        "time": ("time_s", "time", "t"),
        "x": ("centroid_x", "x_mm", "x", "X"),
        "y": ("centroid_y", "y_mm", "y", "Y"),
        "e1": ("eps1_major", "major_strain", "e1", "eps1", "epsilon1"),
        "e2": ("eps2_minor", "minor_strain", "e2", "eps2", "epsilon2"),
        "path": ("path_id", "element_label", "facet_id", "point_id", "id", "label"),
        "ip": ("integration_point", "ip"),
    }.items():
        col = first(*names)
        if col is not None:
            mapping[key] = col
    return mapping


def _thinning_rate(times: list[float], strain_sum: list[float]) -> list[float]:
    out = [0.0] * len(times)
    for idx in range(len(times)):
        if idx == 0:
            dt = times[1] - times[0]
            out[idx] = (strain_sum[1] - strain_sum[0]) / dt if dt > 1e-12 else 0.0
        elif idx == len(times) - 1:
            dt = times[idx] - times[idx - 1]
            out[idx] = (strain_sum[idx] - strain_sum[idx - 1]) / dt if dt > 1e-12 else 0.0
        else:
            dt = times[idx + 1] - times[idx - 1]
            out[idx] = (strain_sum[idx + 1] - strain_sum[idx - 1]) / dt if dt > 1e-12 else 0.0
    return out


def _eval_index(n_points: int) -> int:
    return max(1, min(n_points - 1, n_points - 1 - VH_EVAL_BACK_FRAMES))


def _connection_radius(pids: list[str], centroids: dict[str, tuple[float, float]]) -> float:
    nearest = []
    for pid in pids:
        x0, y0 = centroids[pid]
        distances = [
            math.hypot(centroids[qid][0] - x0, centroids[qid][1] - y0)
            for qid in pids
            if qid != pid
        ]
        if distances:
            nearest.append(min(distances))
    return max(1.6 * sorted(nearest)[len(nearest) // 2], 1e-6) if nearest else 2.0


def _connected_components(
    hot: list[str],
    centroids: dict[str, tuple[float, float]],
    radius: float,
) -> list[list[str]]:
    remaining = set(hot)
    components = []
    while remaining:
        seed = remaining.pop()
        component = [seed]
        stack = [seed]
        while stack:
            pid = stack.pop()
            x0, y0 = centroids[pid]
            neighbors = [
                qid for qid in list(remaining)
                if math.hypot(centroids[qid][0] - x0, centroids[qid][1] - y0) <= radius
            ]
            for qid in neighbors:
                remaining.remove(qid)
                stack.append(qid)
                component.append(qid)
        components.append(component)
    return components


def _component_score(
    comp: list[str],
    paths: dict[str, dict[str, list[float]]],
    centroids: dict[str, tuple[float, float]],
    k_eval: int,
    anchor: tuple[float, float] | None,
) -> tuple[float, float, int]:
    mean_rate = float(np.mean([paths[pid]["rate"][k_eval] for pid in comp]))
    if anchor is None:
        return (mean_rate, float(len(comp)), len(comp))
    distance = min(math.hypot(centroids[pid][0] - anchor[0], centroids[pid][1] - anchor[1]) for pid in comp)
    return (-distance, mean_rate, len(comp))


def _moving_average(values: list[float], window: int) -> list[float]:
    window = max(1, int(window))
    if window <= 1 or len(values) < 3:
        return list(values)
    if window % 2 == 0:
        window += 1
    half = window // 2
    out = []
    for idx in range(len(values)):
        lo = max(0, idx - half)
        hi = min(len(values), idx + half + 1)
        out.append(float(np.mean(values[lo:hi])))
    return out


def _line_fit(x: list[float], y: list[float]) -> tuple[float, float, float] | None:
    if len(x) < 2:
        return None
    coeffs = np.polyfit(np.array(x, dtype=float), np.array(y, dtype=float), 1)
    slope = float(coeffs[0])
    intercept = float(coeffs[1])
    err = float(np.mean((np.array(y) - (slope * np.array(x) + intercept)) ** 2))
    return slope, intercept, err


def _dic_instable_index(t: list[float], t_cross: float) -> int | None:
    if not np.isfinite(t_cross):
        return None
    upper = next((idx for idx, value in enumerate(t) if value > t_cross), None)
    if upper is None or upper <= 0:
        return None
    dt = t[upper] - t[upper - 1]
    if dt <= 0:
        return None
    threshold = t_cross + 0.5 * dt
    index = None
    for idx, value in enumerate(t):
        if value < threshold:
            index = idx
    if index is None or index <= 0:
        return None
    return index


def _volk_hora_fit(t: list[float], rate: list[float]) -> dict[str, Any] | None:
    t_fit_end = t[-1]
    if VH_FIT_WINDOW_SECONDS > 0.0:
        t_min_fit = max(t[0], t_fit_end - VH_FIT_WINDOW_SECONDS)
    else:
        t_min_fit = t[0] + (1.0 - VH_FIT_WINDOW_FRAC) * (t_fit_end - t[0])
    stable_idx = [idx for idx in range(1, len(t) - 1) if t_min_fit <= t[idx] <= t_fit_end]
    if VH_UNSTABLE_TAIL_POINTS > 0:
        unstable_idx = list(range(1, len(t) - 1))[-VH_UNSTABLE_TAIL_POINTS:]
    else:
        if VH_UNSTABLE_FIT_WINDOW_SECONDS > 0.0:
            t_min_unstable = max(t[0], t_fit_end - VH_UNSTABLE_FIT_WINDOW_SECONDS)
        else:
            t_min_unstable = t_min_fit
        unstable_idx = [idx for idx in range(1, len(t) - 1) if t_min_unstable <= t[idx] <= t_fit_end]
    if len(stable_idx) <= VH_MIN_STABLE_POINTS or len(unstable_idx) < VH_MIN_UNSTABLE_POINTS:
        return None
    xs = [t[idx] for idx in stable_idx]
    ys = [rate[idx] for idx in stable_idx]
    xu = [t[idx] for idx in unstable_idx]
    yu = [rate[idx] for idx in unstable_idx]
    ns = len(xs)
    nu = len(xu)

    best_stable = None
    for count in range(VH_MIN_STABLE_POINTS, ns):
        fit = _line_fit(xs[:count], ys[:count])
        if fit is None:
            continue
        score = fit[2] * float(count) / float(max(count - 1, 1))
        if best_stable is None or score < best_stable["mse"]:
            best_stable = {"count": count, "slope": fit[0], "intercept": fit[1], "mse": score}
    best_unstable = None
    if VH_UNSTABLE_TAIL_POINTS > 0:
        unstable_candidates = [(0, nu)]
    else:
        unstable_candidates = [(start, nu - start) for start in range(1, nu - VH_MIN_UNSTABLE_POINTS + 1)]
    for start, count in unstable_candidates:
        fit = _line_fit(xu[start:], yu[start:])
        if fit is None:
            continue
        score = fit[2]
        if best_unstable is None or score < best_unstable["mse"]:
            best_unstable = {"count": count, "slope": fit[0], "intercept": fit[1], "mse": score}
    if best_stable is None or best_unstable is None:
        return None
    denom = best_stable["slope"] - best_unstable["slope"]
    if abs(denom) < 1e-20:
        return None
    t_cross = (best_unstable["intercept"] - best_stable["intercept"]) / denom
    kcrit = _dic_instable_index(t, t_cross)
    if kcrit is None or kcrit <= 0:
        return None
    return {
        "t_fit_start": xs[0],
        "t_fit_end": t_fit_end,
        "t_cross": t_cross,
        "y_cross": best_stable["slope"] * t_cross + best_stable["intercept"],
        "kcrit": kcrit,
        "kstable": kcrit - 1,
        "stable": best_stable,
        "unstable": best_unstable,
        "stable_range": (xs[0], xs[best_stable["count"] - 1]),
        "unstable_range": (xu[nu - best_unstable["count"]], xu[-1]),
    }
