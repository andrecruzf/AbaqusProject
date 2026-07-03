from __future__ import annotations

from pathlib import Path

import pandas as pd

from logic.results_scan import CsvCache

from .style import apply_standard_axes, new_figure


def build(job_dir: Path, cache: CsvCache):
    path = Path(job_dir) / "punch_fd.csv"
    if not path.exists():
        return None, "punch_fd.csv not found"
    df = cache.read(path)
    x_col = "U3_mm" if "U3_mm" in df.columns else None
    y_col = "RF3_N" if "RF3_N" in df.columns else None
    if x_col is None or y_col is None:
        return None, "punch_fd.csv missing U3_mm/RF3_N columns"
    fig, ax = new_figure()
    ax.plot(
        pd.to_numeric(df[x_col], errors="coerce"),
        pd.to_numeric(df[y_col], errors="coerce"),
        color="tab:blue",
        linewidth=1,
        marker="None",
    )
    _add_fracture_line(ax, job_dir, cache)
    apply_standard_axes(ax, "Punch displacement U3 [mm]", "Reaction force RF3 [N]", "Force-displacement")
    return fig, ""


def _add_fracture_line(ax, job_dir: Path, cache: CsvCache) -> None:
    fl_path = Path(job_dir) / "forming_limits.csv"
    if not fl_path.exists():
        return
    try:
        df = cache.read(fl_path)
    except Exception:
        return
    if "method" not in df.columns or "U3_mm" not in df.columns:
        return
    rows = df[df["method"] == "fracture"]
    if rows.empty:
        return
    u3 = pd.to_numeric(rows.iloc[0].get("U3_mm"), errors="coerce")
    if pd.notna(u3):
        ax.axvline(float(u3), color="tab:red", linestyle="--", linewidth=0.8, label="fracture")

