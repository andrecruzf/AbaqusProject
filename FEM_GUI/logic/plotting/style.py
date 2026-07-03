from __future__ import annotations

import math
import os
from collections import OrderedDict
from pathlib import Path

from app.constants import FEM_GUI_DIR, PROJECT_ROOT

_mpl_dir = FEM_GUI_DIR / ".cache" / "matplotlib"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

import matplotlib
import matplotlib.ticker as ticker
import pandas as pd
from matplotlib.figure import Figure


FIG_WIDTH = 6.4
FIG_HEIGHT = 4.8
FONT = "Arial"
GRID_STYLE = dict(which="major", axis="both", linestyle="--", color="gray", linewidth=0.5, zorder=0, alpha=0.5)
CONFIG_COLORS = PROJECT_ROOT / "GUI_FLD-evaluation" / "parameters" / "config_colors.txt"


def round_down(value: float, step: float = 1.0) -> float:
    return math.floor(value / step) * step


def round_up(value: float, step: float = 1.0) -> float:
    return math.ceil(value / step) * step


def get_linestyles() -> OrderedDict[str, tuple[int, tuple[int, ...]]]:
    return OrderedDict(
        [
            ("solid", (0, ())),
            ("dotted1", (0, (1, 1))),
            ("dotted2", (0, (1, 3))),
            ("dashdotted1", (0, (3, 2, 1, 2))),
            ("dashdotted2", (0, (3, 5, 1, 5))),
            ("dashdotdotted1", (0, (3, 2, 1, 2, 1, 2))),
            ("dashdotdotted2", (0, (3, 5, 1, 5, 1, 5))),
            ("dashed1", (0, (4, 2))),
            ("dashed2", (0, (7, 4))),
        ]
    )


def load_config_palette() -> pd.DataFrame:
    if CONFIG_COLORS.exists():
        try:
            return pd.read_csv(CONFIG_COLORS, sep=",", header=0, index_col=0)
        except Exception:
            pass
    return pd.DataFrame(
        {
            "Color": ["tab:blue", "tab:red", "tab:green", "tab:purple", "tab:orange"],
            "linestyle": ["solid", "solid", "solid", "solid", "solid"],
        },
        index=["A", "B", "C", "D", "E"],
    )


def palette_color(index: int) -> str:
    colors = ["tab:blue", "tab:red", "tab:green", "tab:purple", "tab:orange", "tab:cyan", "tab:gray", "tab:brown"]
    return colors[index % len(colors)]


def method_marker(method: str) -> tuple[str, float, str]:
    mapping = {
        "fracture": ("x", 5, "Fracture"),
        "volk_hora": ("o", 4, "Volk & Hora"),
        "sdv6": ("s", 4, "SDV6/damage"),
        "curvature": ("D", 4, "Min-Stoughton"),
    }
    return mapping.get(method, ("o", 4, method))


def new_figure(title: str | None = None):
    matplotlib.rcParams["font.family"] = FONT
    # Plain Figure, not plt.figure(): pyplot would spawn a managed GUI window
    # and is unsafe from the background task threads that render these plots.
    fig = Figure(figsize=[FIG_WIDTH, FIG_HEIGHT])
    ax = fig.subplots()
    if title:
        ax.set_title(title, fontsize=12, fontweight="bold")
    return fig, ax


def apply_standard_axes(ax, xlabel: str, ylabel: str, title: str | None = None, zero_x: bool = False, zero_y: bool = False):
    ax.tick_params(axis="both", labelsize=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    if title:
        ax.set_title(title, fontsize=12, fontweight="bold")
    if zero_x:
        ax.axvline(0, linewidth=0.8, color="silver", zorder=0)
    if zero_y:
        ax.axhline(0, linewidth=0.8, color="silver", zorder=0)
    ax.grid(**GRID_STYLE)
    ax.figure.subplots_adjust(bottom=0.15, left=0.13, right=0.96, top=0.86)


def apply_fld_axes(ax, e1_values, e2_values, title: str = "Forming Limit Curve", legend_items: int = 4):
    e1_vals = [float(v) for v in e1_values if pd.notna(v)]
    e2_vals = [float(v) for v in e2_values if pd.notna(v)]
    e1_max = max(e1_vals) if e1_vals else 1.0
    e2_min = min(e2_vals) if e2_vals else -0.5
    e2_max = max(e2_vals) if e2_vals else 0.5

    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.1))
    ax.xaxis.set_major_locator(ticker.MultipleLocator(0.1))
    ax.tick_params(axis="both", labelsize=10)
    ax.axvline(0, linewidth=0.8, color="silver", zorder=0)
    ax.set_ylabel(r"Major strain $e_1$ [$-$]", fontsize=10)
    ax.set_xlabel(r"Minor strain $e_2$ [$-$]", fontsize=10)
    ax.set_ylim(bottom=0, top=round_up(e1_max + 0.025, 0.05))
    ax.set_xlim(left=round_down(e2_min - 0.05, 0.05), right=round_up(e2_max + 0.025, 0.05))
    ax.grid(**GRID_STYLE)
    ax.set_title(title, fontsize=12, fontweight="bold")
    adjust_fld_margins(ax.figure, legend_items)


def adjust_fld_margins(fig, legend_items: int) -> None:
    lines_legend = round_up(max(1, legend_items) / 4, 1)
    marg_min = 0.14
    h_title = 0.36
    h_legend_line = 0.21
    h_xticklabel = 0.25
    h_xlabel = 0.19
    w_yticklabel = 0.32
    w_ylabel = 0.19
    marg_right = 1 - marg_min / FIG_WIDTH
    marg_top = 1 - (marg_min + h_title) / FIG_HEIGHT
    marg_left = (marg_min + w_yticklabel + w_ylabel) / FIG_WIDTH
    marg_bottom = (marg_min + lines_legend * h_legend_line + h_xticklabel + h_xlabel) / FIG_HEIGHT
    fig.subplots_adjust(bottom=marg_bottom, left=marg_left, right=marg_right, top=marg_top)


def bottom_legend(fig, frameon: bool = True, ncol: int = 4) -> None:
    fig.legend(
        loc="lower center",
        frameon=frameon,
        ncol=ncol,
        edgecolor="k",
        fancybox=False,
        fontsize=9,
        bbox_to_anchor=(0.5, 0.07 / FIG_HEIGHT),
        borderaxespad=0,
    )

