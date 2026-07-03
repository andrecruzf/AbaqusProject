from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from logic.results_scan import CsvCache

from .sensitivity import _ke_curve, _thinning_curve
from .style import apply_standard_axes, new_figure


def convergence_map(job_dirs: dict[str, Path], cache: CsvCache) -> tuple[pd.DataFrame | None, str]:
    curves = {}
    meta = {}
    for name, path in job_dirs.items():
        params = _parse_params(name)
        if params is None:
            continue
        curve = _thinning_curve(Path(path), cache)
        if curve is None:
            continue
        curves[name] = curve
        meta[name] = params
    complete = list(curves)
    if not complete:
        return None, "No sensitivity curves found"
    ref_name = min(complete, key=lambda key: (meta[key]["mr"], meta[key]["ms"]))
    ref_curve = curves[ref_name]
    u3_max_ref = float(ref_curve["U3_mm"].max())
    u3_grid = np.linspace(0, u3_max_ref, 200)
    ref_thinning = np.interp(u3_grid, ref_curve["U3_mm"].values, ref_curve["thinning"].values)
    all_ms = sorted({item["ms"] for item in meta.values()})
    all_mr = sorted({item["mr"] for item in meta.values()})
    rows = {}
    for mr in all_mr:
        row = []
        for ms in all_ms:
            name = next((key for key, value in meta.items() if value["mr"] == mr and value["ms"] == ms), None)
            if not name:
                row.append("")
                continue
            curve = curves[name]
            u3_max = min(float(curve["U3_mm"].max()), u3_max_ref)
            mask = u3_grid <= u3_max
            if mask.sum() < 2:
                row.append("")
                continue
            thinning = np.interp(u3_grid[mask], curve["U3_mm"].values, curve["thinning"].values)
            denom = np.where(np.abs(ref_thinning[mask]) > 1e-6, ref_thinning[mask], np.nan)
            err = float(np.nanmax(np.abs((thinning - ref_thinning[mask]) / denom)) * 100.0)
            row.append(f"{err:.1f}%")
        rows[f"mr={int(mr) if float(mr).is_integer() else mr:g}"] = row
    df = pd.DataFrame(rows, index=[f"{ms:.0e}" for ms in all_ms]).T
    df.index.name = "mr \\ dt"
    return df, ""


def convergence_heatmap(job_dirs: dict[str, Path], cache: CsvCache):
    df, reason = convergence_map(job_dirs, cache)
    if df is None:
        return None, reason
    numeric = df.map(lambda value: float(str(value).replace("%", "")) if value else np.nan)
    fig, ax = new_figure()
    im = ax.imshow(numeric.values, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(numeric.columns)), labels=list(numeric.columns), fontsize=10)
    ax.set_yticks(range(len(numeric.index)), labels=list(numeric.index), fontsize=10)
    for row_idx in range(numeric.shape[0]):
        for col_idx in range(numeric.shape[1]):
            value = numeric.iloc[row_idx, col_idx]
            if not math.isnan(value):
                ax.text(col_idx, row_idx, f"{value:.1f}%", ha="center", va="center", color="white", fontsize=9)
    fig.colorbar(im, ax=ax, label="max thinning deviation [%]")
    apply_standard_axes(ax, "mass scaling dt", "mesh refinement", "Convergence map")
    return fig, ""


def _parse_params(name: str) -> dict[str, float] | None:
    mr = re.search(r"_mr([\dp]+)", name)
    ms = re.search(r"_ms(\d+)e(\d+)", name)
    mr_val = float(mr.group(1).replace("p", ".")) if mr else 1.0
    ms_val = float(ms.group(1)) * 10 ** (-int(ms.group(2))) if ms else 1e-5
    return {"mr": mr_val, "ms": ms_val}
