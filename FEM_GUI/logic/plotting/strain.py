from __future__ import annotations

from pathlib import Path

import pandas as pd

from logic.results_scan import CsvCache

from .style import apply_standard_axes, new_figure


def strain_path(job_dir: Path, cache: CsvCache):
    path = Path(job_dir) / "strain_path.csv"
    if not path.exists():
        return None, "strain_path.csv not found"
    df = cache.read(path)
    if not {"eps1_major", "eps2_minor"}.issubset(df.columns):
        return None, "strain_path.csv missing eps1_major/eps2_minor columns"
    fig, ax = new_figure()
    ax.plot(
        pd.to_numeric(df["eps2_minor"], errors="coerce"),
        pd.to_numeric(df["eps1_major"], errors="coerce"),
        color="tab:blue",
        linewidth=1,
        marker="None",
    )
    apply_standard_axes(ax, r"Minor strain $e_2$ [$-$]", r"Major strain $e_1$ [$-$]", "Strain path", zero_x=True, zero_y=True)
    return fig, ""


def strain_evolution(job_dir: Path, cache: CsvCache):
    path = Path(job_dir) / "strain_path.csv"
    if not path.exists():
        return None, "strain_path.csv not found"
    df = cache.read(path)
    if not {"time_s", "eps1_major", "eps2_minor"}.issubset(df.columns):
        return None, "strain_path.csv missing time_s/strain columns"
    fig, ax = new_figure()
    t = pd.to_numeric(df["time_s"], errors="coerce")
    ax.plot(t, pd.to_numeric(df["eps1_major"], errors="coerce"), color="tab:blue", linewidth=1, label=r"$e_1$")
    ax.plot(t, pd.to_numeric(df["eps2_minor"], errors="coerce"), color="tab:orange", linewidth=1, label=r"$e_2$")
    apply_standard_axes(ax, "Time [s]", "Strain [-]", "Strain evolution")
    ax.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=9)
    return fig, ""


def triaxiality(job_dir: Path, cache: CsvCache):
    path = Path(job_dir) / "strain_path.csv"
    if not path.exists():
        return None, "strain_path.csv not found"
    df = cache.read(path)
    if "TRIAX" not in df.columns:
        return None, "strain_path.csv has no TRIAX column"
    cols = [c for c in ("time_s", "TRIAX", "EQPS") if c in df.columns]
    data = df[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["time_s", "TRIAX"])
    data = data.groupby("time_s", as_index=False).mean().sort_values("time_s")
    if data.empty:
        return None, "strain_path.csv has no usable TRIAX rows"
    if "EQPS" in data.columns and data["EQPS"].notna().any():
        x = data["EQPS"]
        xlabel = "Equivalent plastic strain EQPS [-]"
    else:
        x = data["time_s"]
        xlabel = "Time [s]"
    fig, ax = new_figure()
    ax.plot(x, data["TRIAX"], color="tab:blue", linewidth=1, label=r"Triaxiality $\eta$")
    for eta, label in [
        (1.0 / 3.0, r"Uniaxial $\eta=1/3$"),
        (0.577, r"Plane strain $\eta\approx0.577$"),
        (2.0 / 3.0, r"Equibiaxial $\eta=2/3$"),
    ]:
        ax.axhline(eta, color="gray", linestyle="--", linewidth=0.8, alpha=0.7, label=label)
    apply_standard_axes(ax, xlabel, r"Triaxiality $\eta$ [$-$]", "Stress-state path")
    ax.legend(frameon=True, edgecolor="k", fancybox=False, fontsize=8)
    return fig, ""


def cluster_location(job_dir: Path, cache: CsvCache):
    path = Path(job_dir) / "strain_cluster.csv"
    if not path.exists():
        return None, "strain_cluster.csv not found"
    df = cache.read(path)
    x_col = next((col for col in ("x_mm", "X", "x") if col in df.columns), None)
    y_col = next((col for col in ("y_mm", "Y", "y") if col in df.columns), None)
    if not x_col or not y_col:
        return None, "strain_cluster.csv missing x/y columns"
    fig, ax = new_figure()
    ax.scatter(pd.to_numeric(df[x_col], errors="coerce"), pd.to_numeric(df[y_col], errors="coerce"), s=7, marker="x", c="tab:blue")
    ax.set_aspect("equal", adjustable="box")
    apply_standard_axes(ax, "x [mm]", "y [mm]", "Cluster location")
    return fig, ""

