"""Generate report figures for the W100 mass-scaling / mesh-refinement sweeps."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import math

os.environ.setdefault("MPLCONFIGDIR", "/tmp/abaqusproject_mplconfig")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "report" / "img" / "results"


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
    strain, _, _, limits = _read(job)
    fracture = limits[limits["method"] == "fracture"]
    if not fracture.empty:
        fracture_time = float(fracture.iloc[0]["time_s"])
        strain = strain[strain["time_s"] <= fracture_time + 1e-12]
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


def _save(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def _plot_strain_path(jobs: list[Job], stem: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 4.2))
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
    ax.legend(frameon=False, fontsize=8)
    _save(fig, stem)


def _plot_energy(jobs: list[Job], stem: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 3.7))
    cmap = plt.get_cmap("tab10")
    max_u3 = 0.0
    for idx, job in enumerate(jobs):
        curve = _energy_curve(job)
        max_u3 = max(max_u3, float(np.nanmax(curve["U3_mm"])))
        curve = curve.replace([np.inf, -np.inf], np.nan).dropna()
        cutoff = 0.05 * max_u3
        curve = curve[curve["U3_mm"] >= cutoff]
        ax.plot(curve["time_s"], curve["ke_ratio_pct"], label=job.label, color=cmap(idx), linewidth=1.5)
    ax.axhline(5.0, color="#222222", linestyle="--", linewidth=1.0, label="5% criterion")
    ax.set_yscale("log")
    ax.set_ylim(0.5, 5000)
    _style_axes(ax, r"Simulation time $t$ [s]", r"$\mathrm{ALLKE}/\mathrm{ALLIE}$ [%]")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    _save(fig, stem)


def _plot_forming_limit_points() -> None:
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    for idx, job in enumerate(MASS_SWEEP):
        fracture = _limit_row(job)
        if fracture is None:
            continue
        ax.plot(fracture["eps2_minor"], fracture["eps1_major"], marker="o", color=plt.get_cmap("Blues")(0.35 + 0.1 * idx), linestyle="None", label=f"MS {job.label}")
    for idx, job in enumerate(MESH_SWEEP):
        fracture = _limit_row(job)
        if fracture is None:
            continue
        ax.plot(fracture["eps2_minor"], fracture["eps1_major"], marker="s", color=plt.get_cmap("Oranges")(0.35 + 0.15 * idx), linestyle="None", label=f"MR {int(job.mr)}")
    _style_axes(ax, r"Minor strain $\varepsilon_2$ [-]", r"Major strain $\varepsilon_1$ [-]")
    ax.set_title("Extracted fracture forming-limit points")
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=7)
    _save(fig, "ms_mr_forming_limit_points")


def _summary_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for job in MASS_SWEEP + MESH_SWEEP:
        curve = _energy_curve(job).replace([np.inf, -np.inf], np.nan).dropna()
        max_u3 = float(np.nanmax(curve["U3_mm"]))
        curve_after_start = curve[curve["U3_mm"] >= 0.05 * max_u3]
        max_ke = float(np.nanmax(curve_after_start["ke_ratio_pct"])) if not curve_after_start.empty else math.nan
        fracture = _limit_row(job)
        volk_hora = _limit_row(job, "volk_hora")
        rows.append(
            {
                "sweep": job.group,
                "label": job.label.replace("$", ""),
                "mass_scaling_dt_s": job.dt,
                "mesh_refinement_factor": job.mr,
                "max_ke_allie_pct_after_5pct_u3": max_ke,
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
    _plot_energy(MASS_SWEEP, "ms_mr_mass_scaling_energy", r"Quasi-staticity check ($f_\mathrm{MR}=2$)")
    _plot_strain_path(MESH_SWEEP, "ms_mr_mesh_refinement_strain_path", r"Mesh-refinement sensitivity ($\Delta t_\mathrm{MS}=10^{-5}$ s)")
    _plot_energy(MESH_SWEEP, "ms_mr_mesh_refinement_energy", r"Quasi-staticity check ($\Delta t_\mathrm{MS}=10^{-5}$ s)")
    _plot_forming_limit_points()
    summary = pd.DataFrame(_summary_rows())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_DIR / "ms_mr_summary.csv", index=False)
    print(f"Wrote figures and summary to {OUT_DIR}")


if __name__ == "__main__":
    main()
