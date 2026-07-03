from __future__ import annotations

from pathlib import Path

import pandas as pd

from logic.results_scan import CsvCache

from .style import apply_standard_axes, new_figure


def energy(job_dir: Path, cache: CsvCache):
    path = Path(job_dir) / "energy_data.csv"
    if not path.exists():
        return None, "energy_data.csv not found"
    df = cache.read(path)
    if "total_time_s" not in df.columns:
        return None, "energy_data.csv missing total_time_s"
    fig, ax = new_figure()
    x = pd.to_numeric(df["total_time_s"], errors="coerce")
    for col, color in [("ALLIE", "tab:blue"), ("ALLKE", "tab:orange"), ("ALLWK", "tab:green")]:
        if col in df.columns:
            ax.plot(x, pd.to_numeric(df[col], errors="coerce"), label=col, color=color, linewidth=1)
    apply_standard_axes(ax, "Time [s]", "Energy", "Energy history")
    ax.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=9)
    return fig, ""

