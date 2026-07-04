"""Generate report figures for the W100 mass-scaling / mesh-refinement sweeps."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import math

os.environ.setdefault("MPLCONFIGDIR", "/tmp/abaqusproject_mplconfig")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "report" / "img" / "results"
PANEL_FIGSIZE = (5.8, 4.2)


@dataclass(frozen=True)
class Job:
    group: str
    label: str
    dt: float
    mr: float
    relpath: str

    @property
    def path(self) -> Path:
        return ROOT / self.relpath


MASS_SWEEP = [
    Job("mass", r"$1\times10^{-6}$ s", 1e-6, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_mr2/Naka100_W100_t1p5_ang0_ms1e6_mr2"),
    Job("mass", r"$5\times10^{-6}$ s", 5e-6, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms5e6_mr2/Naka100_W100_t1p5_ang0_ms5e6_mr2"),
    Job("mass", r"$1\times10^{-5}$ s", 1e-5, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e5_mr2/Naka100_W100_t1p5_ang0_ms1e5_mr2"),
    Job("mass", r"$5\times10^{-5}$ s", 5e-5, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms5e5_mr2/Naka100_W100_t1p5_ang0_ms5e5_mr2"),
    Job("mass", r"$1\times10^{-4}$ s", 1e-4, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e4_mr2/Naka100_W100_t1p5_ang0_ms1e4_mr2"),
]

MESH_SWEEP = [
    Job("mesh", r"$f_\mathrm{MR}=1$", 1e-5, 1, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e5/Naka100_W100_t1p5_ang0_ms1e5"),
    Job("mesh", r"$f_\mathrm{MR}=2$", 1e-5, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e5_mr2/Naka100_W100_t1p5_ang0_ms1e5_mr2"),
    Job("mesh", r"$f_\mathrm{MR}=3$", 1e-5, 3, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e5_mr3/Naka100_W100_t1p5_ang0_ms1e5_mr3"),
]

# Confirmation sweep: mesh refinement repeated at the accepted mass-scaling
# target (MS1, Delta t = 1e-6 s) identified from MASS_SWEEP.
CONFIRM_SWEEP = [
    Job("confirm", r"$f_\mathrm{MR}=1$", 1e-6, 1, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6/Naka100_W100_t1p5_ang0_ms1e6"),
    Job("confirm", r"$f_\mathrm{MR}=1.25$", 1e-6, 1.25, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_mr1p25_pd32/Naka100_W100_t1p5_ang0_ms1e6_mr1p25_pd32"),
    Job("confirm", r"$f_\mathrm{MR}=1.41$", 1e-6, 1.41, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_mr1p41_pd32/Naka100_W100_t1p5_ang0_ms1e6_mr1p41_pd32"),
    Job("confirm", r"$f_\mathrm{MR}=2$", 1e-6, 2, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_mr2/Naka100_W100_t1p5_ang0_ms1e6_mr2"),
    Job("confirm", r"$f_\mathrm{MR}=3$", 1e-6, 3, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_mr3/Naka100_W100_t1p5_ang0_ms1e6_mr3"),
]


def _read(job: Job) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    missing = [name for name in ("strain_path.csv", "punch_fd.csv", "energy_data.csv", "forming_limits.csv") if not (job.path / name).exists()]
    if missing:
        raise FileNotFoundError(f"{job.path}: missing {', '.join(missing)}")
    strain = pd.read_csv(job.path / "strain_path.csv").sort_values("time_s")
    punch = pd.read_csv(job.path / "punch_fd.csv").sort_values("total_time_s")
    energy = pd.read_csv(job.path / "energy_data.csv").sort_values("total_time_s")
    limits = pd.read_csv(job.path / "forming_limits.csv")
    return strain, punch, energy, limits


def _u3_at(time_s: np.ndarray, punch: pd.DataFrame) -> np.ndarray:
    return np.interp(time_s, punch["total_time_s"].to_numpy(), punch["U3_mm"].to_numpy())


def _strain_path_curve(job: Job) -> pd.DataFrame:
    strain, _, _, _ = _read(job)
    return pd.DataFrame(
        {
            "time_s": strain["time_s"].to_numpy(),
            "eps1_major": strain["eps1_major"].to_numpy(),
            "eps2_minor": strain["eps2_minor"].to_numpy(),
        }
    )


def _energy_curve(job: Job) -> pd.DataFrame:
    _, punch, energy, _ = _read(job)
    allie = energy["ALLIE"].to_numpy()
    ratio = energy["ALLKE"].to_numpy() / np.where(allie > 1e-12, allie, np.nan) * 100.0
    return pd.DataFrame(
        {
            "time_s": energy["total_time_s"].to_numpy(),
            "U3_mm": _u3_at(energy["total_time_s"].to_numpy(), punch),
            "ke_ratio_pct": ratio,
        }
    )


def _limit_row(job: Job, method: str = "fracture") -> pd.Series | None:
    _, _, _, limits = _read(job)
    rows = limits[limits["method"] == method]
    if rows.empty:
        return None
    return rows.iloc[0]


def _style_axes(ax: plt.Axes, xlabel: str, ylabel: str) -> None:
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, which="major", color="#d9d9d9", linewidth=0.7)
    ax.grid(True, which="minor", color="#eeeeee", linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _save(fig: plt.Figure, stem: str, *, bottom_margin: float | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if bottom_margin is None:
        fig.tight_layout()
    else:
        fig.tight_layout(rect=(0.0, bottom_margin, 1.0, 1.0))
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=300)
    fig.savefig(OUT_DIR / f"{stem}.pdf")
    plt.close(fig)


def _format_mr(mr: float) -> str:
    return f"{mr:g}"


def _ratio_near_time(curve: pd.DataFrame, time_s: float | None) -> float:
    if time_s is None or math.isnan(time_s) or curve.empty:
        return math.nan
    idx = (curve["time_s"] - time_s).abs().idxmin()
    return float(curve.loc[idx, "ke_ratio_pct"])


def _max_ratio_between(curve: pd.DataFrame, start_s: float, end_s: float) -> float:
    if math.isnan(start_s) or math.isnan(end_s) or curve.empty:
        return math.nan
    window = curve[(curve["time_s"] >= start_s) & (curve["time_s"] < end_s)]
    if window.empty:
        return math.nan
    return float(np.nanmax(window["ke_ratio_pct"]))


def _plot_strain_path(jobs: list[Job], stem: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    cmap = plt.get_cmap("tab10")
    for idx, job in enumerate(jobs):
        curve = _strain_path_curve(job)
        color = cmap(idx)
        ax.plot(
            curve["eps2_minor"],
            curve["eps1_major"],
            label=job.label,
            color=color,
            linewidth=1.6,
        )
        fracture = _limit_row(job)
        if fracture is not None:
            ax.plot(
                [float(fracture["eps2_minor"])],
                [float(fracture["eps1_major"])],
                marker="o",
                markersize=4.5,
                color=color,
                linestyle="None",
            )
    _style_axes(ax, r"Minor strain $\varepsilon_2$ [-]", r"Major strain $\varepsilon_1$ [-]")
    ax.set_title(title)
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    _save(fig, stem)


def _plot_energy(
    jobs: list[Job],
    stem: str,
    title: str,
    ylim: tuple[float, float] | None = None,
    *,
    legend_below: bool = False,
) -> None:
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    cmap = plt.get_cmap("tab10")
    max_ratio = 0.0
    for idx, job in enumerate(jobs):
        curve = _energy_curve(job)
        curve = curve.replace([np.inf, -np.inf], np.nan).dropna()
        if curve.empty:
            continue
        max_ratio = max(max_ratio, float(np.nanmax(curve["ke_ratio_pct"])))
        ax.plot(curve["time_s"], curve["ke_ratio_pct"], label=job.label, color=cmap(idx), linewidth=1.5)
    ax.axhline(5.0, color="#222222", linestyle="--", linewidth=1.0, label="5% criterion")
    if ylim is None:
        ax.set_ylim(0.0, max(10.0, 1.05 * max_ratio))
    else:
        ax.set_ylim(*ylim)
    _style_axes(ax, r"Simulation time $t$ [s]", r"$\mathrm{ALLKE}/\mathrm{ALLIE}$ [%]")
    ax.set_title(title)
    if legend_below:
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.02),
            frameon=False,
            fontsize=8,
            ncol=3,
        )
        _save(fig, stem, bottom_margin=0.20)
    else:
        ax.legend(loc="upper right", frameon=False, fontsize=8, ncol=2)
        _save(fig, stem)


def _plot_forming_limit_points() -> None:
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    mass_color = "#1f77b4"
    mesh_color = "#d95f02"
    confirm_color = "#2ca02c"
    for job in MASS_SWEEP:
        fracture = _limit_row(job)
        if fracture is None:
            continue
        ax.plot(fracture["eps2_minor"], fracture["eps1_major"], marker="o", color=mass_color, linestyle="None")
    for job in MESH_SWEEP:
        fracture = _limit_row(job)
        if fracture is None:
            continue
        ax.plot(fracture["eps2_minor"], fracture["eps1_major"], marker="s", color=mesh_color, linestyle="None")
    for job in CONFIRM_SWEEP:
        fracture = _limit_row(job)
        if fracture is None:
            continue
        ax.plot(fracture["eps2_minor"], fracture["eps1_major"], marker="^", color=confirm_color, linestyle="None")
    _style_axes(ax, r"Minor strain $\varepsilon_2$ [-]", r"Major strain $\varepsilon_1$ [-]")
    ax.set_title("Extracted fracture forming-limit points")
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=mass_color, markeredgecolor=mass_color, markersize=7, label="Mass-scaling sweep"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor=mesh_color, markeredgecolor=mesh_color, markersize=7, label="First mesh sweep"),
        Line2D([0], [0], marker="^", color="none", markerfacecolor=confirm_color, markeredgecolor=confirm_color, markersize=7, label="Confirmation sweep"),
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8)
    _save(fig, "ms_mr_forming_limit_points")


def _summary_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for job in MASS_SWEEP + MESH_SWEEP + CONFIRM_SWEEP:
        curve = _energy_curve(job).replace([np.inf, -np.inf], np.nan).dropna()
        max_u3 = float(np.nanmax(curve["U3_mm"]))
        curve_after_start = curve[curve["U3_mm"] >= 0.05 * max_u3]
        fracture = _limit_row(job)
        volk_hora = _limit_row(job, "volk_hora")
        fracture_time = None if fracture is None else float(fracture["time_s"])
        volk_hora_time = None if volk_hora is None else float(volk_hora["time_s"])
        curve_to_fracture = (
            curve_after_start
            if fracture_time is None
            else curve_after_start[curve_after_start["time_s"] < fracture_time]
        )
        max_ke_full = float(np.nanmax(curve_after_start["ke_ratio_pct"])) if not curve_after_start.empty else math.nan
        max_ke_to_fracture = (
            float(np.nanmax(curve_to_fracture["ke_ratio_pct"])) if not curve_to_fracture.empty else math.nan
        )
        rows.append(
            {
                "sweep": job.group,
                "label": job.label.replace("$", ""),
                "mass_scaling_dt_s": job.dt,
                "mesh_refinement_factor": job.mr,
                "max_ke_allie_pct_after_5pct_u3_full_history": max_ke_full,
                "max_ke_allie_pct_after_5pct_u3_to_fracture": max_ke_to_fracture,
                "max_ke_allie_pct_last_0p5s_before_fracture": (
                    math.nan
                    if fracture_time is None
                    else _max_ratio_between(curve, fracture_time - 0.5, fracture_time)
                ),
                "max_ke_allie_pct_between_vh_and_fracture": (
                    math.nan
                    if fracture_time is None or volk_hora_time is None
                    else _max_ratio_between(curve, volk_hora_time, fracture_time)
                ),
                "ke_allie_pct_at_fracture": _ratio_near_time(curve, fracture_time),
                "ke_allie_pct_at_volk_hora": _ratio_near_time(curve, volk_hora_time),
                "fracture_eps1": None if fracture is None else float(fracture["eps1_major"]),
                "fracture_eps2": None if fracture is None else float(fracture["eps2_minor"]),
                "fracture_u3_mm": None if fracture is None else float(fracture["U3_mm"]),
                "volk_hora_eps1": None if volk_hora is None else float(volk_hora["eps1_major"]),
                "volk_hora_eps2": None if volk_hora is None else float(volk_hora["eps2_minor"]),
                "volk_hora_u3_mm": None if volk_hora is None else float(volk_hora["U3_mm"]),
                "job_dir": str(job.path.relative_to(ROOT)),
            }
        )
    return rows


def main() -> None:
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    _plot_strain_path(MASS_SWEEP, "ms_mr_mass_scaling_strain_path", r"Mass-scaling sensitivity ($f_\mathrm{MR}=2$)")
    _plot_energy(MASS_SWEEP, "ms_mr_mass_scaling_energy", r"Energy-ratio history ($f_\mathrm{MR}=2$)")
    _plot_energy(
        MASS_SWEEP,
        "ms_mr_mass_scaling_energy_zoom",
        r"Zoom near 5% criterion ($f_\mathrm{MR}=2$)",
        ylim=(0.0, 10.0),
        legend_below=True,
    )
    _plot_strain_path(MESH_SWEEP, "ms_mr_mesh_refinement_strain_path", r"Mesh-refinement sensitivity ($\Delta t_\mathrm{MS}=10^{-5}$ s)")
    _plot_energy(MESH_SWEEP, "ms_mr_mesh_refinement_energy", r"Energy-ratio history ($\Delta t_\mathrm{MS}=10^{-5}$ s)")
    _plot_energy(
        MESH_SWEEP,
        "ms_mr_mesh_refinement_energy_zoom",
        r"Zoom near 5% criterion ($\Delta t_\mathrm{MS}=10^{-5}$ s)",
        ylim=(0.0, 10.0),
        legend_below=True,
    )
    _plot_strain_path(CONFIRM_SWEEP, "ms_mr_confirm_strain_path", r"Mesh-refinement confirmation ($\Delta t_\mathrm{MS}=10^{-6}$ s)")
    _plot_energy(CONFIRM_SWEEP, "ms_mr_confirm_energy", r"Energy-ratio history ($\Delta t_\mathrm{MS}=10^{-6}$ s)")
    _plot_energy(
        CONFIRM_SWEEP,
        "ms_mr_confirm_energy_zoom",
        r"Zoom near 5% criterion ($\Delta t_\mathrm{MS}=10^{-6}$ s)",
        ylim=(0.0, 10.0),
        legend_below=True,
    )
    _plot_forming_limit_points()
    summary = pd.DataFrame(_summary_rows())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_DIR / "ms_mr_summary.csv", index=False)
    print(f"Wrote figures and summary to {OUT_DIR}")


if __name__ == "__main__":
    main()
