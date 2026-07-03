from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from logic.results_scan import CsvCache

from .style import apply_standard_axes, new_figure, palette_color


def thinning(job_dirs: dict[str, Path], cache: CsvCache):
    fig, ax = new_figure()
    any_data = False
    for idx, (name, job_dir) in enumerate(sorted(job_dirs.items())):
        curve = _thinning_curve(Path(job_dir), cache)
        if curve is None:
            continue
        ax.plot(
            curve["U3_mm"],
            curve["thinning"],
            label=_short_label(name),
            linewidth=1,
            marker="None",
            color=palette_color(idx),
        )
        any_data = True
    if not any_data:
        return None, "No thinning curves found"
    apply_standard_axes(ax, "Punch displacement U3 [mm]", r"Thinning strain $e_1 + e_2$ [$-$]", "Thinning sensitivity")
    ax.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=8)
    return fig, ""


def quasi_staticity(job_dirs: dict[str, Path], cache: CsvCache, limit_pct: float = 5.0):
    fig, ax = new_figure()
    any_data = False
    max_u3 = 0.0
    for idx, (name, job_dir) in enumerate(sorted(job_dirs.items())):
        curve = _ke_curve(Path(job_dir), cache)
        if curve is None:
            continue
        max_u3 = max(max_u3, float(curve["U3_mm"].max()))
        ax.plot(curve["U3_mm"], curve["ke_ratio_pct"], label=_short_label(name), linewidth=1, color=palette_color(idx))
        any_data = True
    if not any_data:
        return None, "No ALLKE/ALLIE curves found"
    ax.plot([0, max_u3], [limit_pct, limit_pct], color="k", linestyle="--", linewidth=0.75, label=f"{limit_pct:.0f}% limit")
    apply_standard_axes(ax, "Punch displacement U3 [mm]", "ALLKE / ALLIE [%]", "Quasi-staticity")
    ax.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=8)
    return fig, ""


def _thinning_curve(job_dir: Path, cache: CsvCache) -> pd.DataFrame | None:
    sp_path = job_dir / "strain_path.csv"
    fd_path = job_dir / "punch_fd.csv"
    if not sp_path.exists() or not fd_path.exists():
        return None
    spdf = cache.read(sp_path).sort_values("time_s")
    fddf = cache.read(fd_path).sort_values("total_time_s")
    if not {"time_s", "eps1_major", "eps2_minor"}.issubset(spdf.columns):
        return None
    if not {"total_time_s", "U3_mm"}.issubset(fddf.columns):
        return None
    u3 = np.interp(spdf["time_s"].values, fddf["total_time_s"].values, fddf["U3_mm"].values)
    thinning_values = spdf["eps1_major"].values + spdf["eps2_minor"].values
    return pd.DataFrame({"U3_mm": u3, "thinning": thinning_values})


def _ke_curve(job_dir: Path, cache: CsvCache) -> pd.DataFrame | None:
    energy_path = job_dir / "energy_data.csv"
    fd_path = job_dir / "punch_fd.csv"
    if not energy_path.exists() or not fd_path.exists():
        return None
    endf = cache.read(energy_path).sort_values("total_time_s")
    fddf = cache.read(fd_path).sort_values("total_time_s")
    if not {"total_time_s", "ALLKE", "ALLIE"}.issubset(endf.columns):
        return None
    if not {"total_time_s", "U3_mm"}.issubset(fddf.columns):
        return None
    u3 = np.interp(endf["total_time_s"].values, fddf["total_time_s"].values, fddf["U3_mm"].values)
    denom = np.where(endf["ALLIE"].values > 1e-12, endf["ALLIE"].values, np.nan)
    ratio = endf["ALLKE"].values / denom * 100.0
    return pd.DataFrame({"U3_mm": u3, "ke_ratio_pct": ratio})


def _short_label(name: str) -> str:
    width = re.search(r"W\d+", name)
    mr = re.search(r"_mr([\dp]+)", name)
    ms = re.search(r"_ms\d+e\d+", name)
    parts = [width.group(0) if width else Path(name).name]
    if mr:
        parts.append("mr=" + mr.group(1).replace("p", "."))
    if ms:
        parts.append(ms.group(0).lstrip("_"))
    return " ".join(parts)

