"""Generate report figures for the W120 punch/blank friction sweep."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/abaqusproject_mplconfig")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "report" / "img" / "results"
PANEL_FIGSIZE = (5.8, 4.2)


@dataclass(frozen=True)
class Job:
    mu: float
    relpath: str

    @property
    def label(self) -> str:
        return rf"$\mu={self.mu:.2f}$"

    @property
    def path(self) -> Path:
        return ROOT / self.relpath


FRICTION_SWEEP = [
    Job(0.00, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_pd32/Naka100_W120_t1p5_ang0_ms1e6_pd32"),
    Job(0.05, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_pd32_fr0p05/Naka100_W120_t1p5_ang0_ms1e6_pd32_fr0p05"),
    Job(0.10, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_pd32_fr0p1/Naka100_W120_t1p5_ang0_ms1e6_pd32_fr0p1"),
    Job(0.15, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_pd32_fr0p15/Naka100_W120_t1p5_ang0_ms1e6_pd32_fr0p15"),
    Job(0.20, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_pd32_fr0p2/Naka100_W120_t1p5_ang0_ms1e6_pd32_fr0p2"),
    Job(0.25, "FLC_output/FLC_Naka100_t1p5_ang0_ms1e6_pd32_fr0p25/Naka100_W120_t1p5_ang0_ms1e6_pd32_fr0p25"),
]


def _read(job: Job) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    missing = [name for name in ("strain_path.csv", "punch_fd.csv", "global.csv", "forming_limits.csv") if not (job.path / name).exists()]
    if missing:
        raise FileNotFoundError(f"{job.path}: missing {', '.join(missing)}")
    strain = pd.read_csv(job.path / "strain_path.csv").sort_values("time_s")
    punch = pd.read_csv(job.path / "punch_fd.csv").sort_values("total_time_s")
    global_history = pd.read_csv(job.path / "global.csv").sort_values("time_s")
    limits = pd.read_csv(job.path / "forming_limits.csv")
    return strain, punch, global_history, limits


def _fracture_row(job: Job) -> pd.Series:
    *_, limits = _read(job)
    rows = limits[limits["method"] == "fracture"]
    if rows.empty:
        raise ValueError(f"{job.path}: forming_limits.csv has no fracture row")
    return rows.iloc[0]


def _strain_curve(job: Job) -> pd.DataFrame:
    strain, _, _, _ = _read(job)
    return strain


def _force_curve(job: Job) -> pd.DataFrame:
    _, punch, _, _ = _read(job)
    curve = punch.copy()
    curve["RF3_kN"] = curve["RF3_N"] / 1000.0
    return curve


def _force_curve_to_fracture(job: Job) -> pd.DataFrame:
    _, punch, _, _ = _read(job)
    fracture = _fracture_row(job)
    curve = punch[punch["total_time_s"] <= float(fracture["time_s"]) + 1e-12].copy()
    curve["RF3_kN"] = curve["RF3_N"] / 1000.0
    return curve


def _energy_history_to_fracture(job: Job) -> pd.DataFrame:
    _, punch, global_history, _ = _read(job)
    fracture = _fracture_row(job)
    max_u3 = float(punch["U3_mm"].max())
    cutoff_u3 = 0.05 * max_u3
    history = global_history[
        (global_history["time_s"] < float(fracture["time_s"]))
        & (global_history["U3_mm"] >= cutoff_u3)
        & (global_history["ALLIE"] > 1e-12)
    ].copy()
    history["ke_allie_pct"] = history["ALLKE"] / history["ALLIE"] * 100.0
    return history


def _energy_ratio_to_fracture(job: Job) -> float:
    history = _energy_history_to_fracture(job)
    if history.empty:
        return np.nan
    return float(history["ke_allie_pct"].max())


def _late_energy_ratio_to_fracture(job: Job) -> float:
    fracture = _fracture_row(job)
    history = _energy_history_to_fracture(job)
    if history.empty:
        return np.nan
    fracture_time = float(fracture["time_s"])
    late = history[history["time_s"] >= fracture_time - 0.5]
    if late.empty:
        return np.nan
    return float(late["ke_allie_pct"].max())


def _force_at_fracture(job: Job) -> float:
    _, punch, _, _ = _read(job)
    fracture = _fracture_row(job)
    return float(
        np.interp(
            float(fracture["time_s"]),
            punch["total_time_s"].to_numpy(),
            punch["RF3_N"].to_numpy(),
        )
        / 1000.0
    )


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
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=300)
    fig.savefig(OUT_DIR / f"{stem}.pdf")
    plt.close(fig)


def _plot_strain_path() -> None:
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    cmap = plt.get_cmap("tab10")
    for idx, job in enumerate(FRICTION_SWEEP):
        curve = _strain_curve(job)
        fracture = _fracture_row(job)
        color = cmap(idx)
        ax.plot(
            curve["eps2_minor"],
            curve["eps1_major"],
            label=job.label,
            color=color,
            linewidth=1.6,
        )
        ax.plot(
            [float(fracture["eps2_minor"])],
            [float(fracture["eps1_major"])],
            marker="o",
            markersize=4.5,
            color=color,
            linestyle="None",
        )
    _style_axes(ax, r"Minor strain $\varepsilon_2$ [-]", r"Major strain $\varepsilon_1$ [-]")
    ax.set_title(r"Punch/blank friction sensitivity (W120)")
    ax.legend(loc="upper left", frameon=False, fontsize=8)
    _save(fig, "friction_sensitivity_strain_path")


def _plot_force_displacement() -> None:
    fig, ax = plt.subplots(figsize=PANEL_FIGSIZE)
    cmap = plt.get_cmap("tab10")
    for idx, job in enumerate(FRICTION_SWEEP):
        curve = _force_curve(job)
        fracture = _fracture_row(job)
        color = cmap(idx)
        ax.plot(
            curve["U3_mm"],
            curve["RF3_kN"],
            label=job.label,
            color=color,
            linewidth=1.5,
        )
        ax.plot(
            [float(fracture["U3_mm"])],
            [_force_at_fracture(job)],
            marker="o",
            markersize=4.2,
            color=color,
            linestyle="None",
        )
    _style_axes(ax, r"Punch displacement $U_3$ [mm]", r"Punch reaction force $F_3$ [kN]")
    ax.set_title(r"Punch force response")
    ax.legend(loc="upper left", frameon=False, fontsize=8, ncol=2)
    _save(fig, "friction_sensitivity_force_displacement")


def _summary_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for job in FRICTION_SWEEP:
        fracture = _fracture_row(job)
        force_curve = _force_curve_to_fracture(job)
        rows.append(
            {
                "mu": job.mu,
                "fracture_eps1": float(fracture["eps1_major"]),
                "fracture_eps2": float(fracture["eps2_minor"]),
                "fracture_u3_mm": float(fracture["U3_mm"]),
                "max_force_kN_to_fracture": float(force_curve["RF3_kN"].max()),
                "force_kN_at_fracture": _force_at_fracture(job),
                "max_ke_allie_pct_after_5pct_travel_to_fracture": _energy_ratio_to_fracture(job),
                "max_ke_allie_pct_last_0p5s_before_fracture": _late_energy_ratio_to_fracture(job),
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
    _plot_strain_path()
    _plot_force_displacement()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(_summary_rows()).to_csv(OUT_DIR / "friction_sensitivity_summary.csv", index=False)
    print(f"Wrote figures and summary to {OUT_DIR}")


if __name__ == "__main__":
    main()
