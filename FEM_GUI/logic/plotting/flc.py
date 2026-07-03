from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from logic.results_scan import CsvCache

from .style import apply_fld_axes, bottom_legend, method_marker, new_figure, palette_color


METHOD_LABELS = {
    "fracture": "Fracture",
    "volk_hora": "Volk & Hora",
    "sdv6": "SDV6/damage",
}


def forming_limits_table(job_dir: Path, cache: CsvCache) -> tuple[list[str], list[list[str]]]:
    path = Path(job_dir) / "forming_limits.csv"
    if not path.exists():
        return [], []
    df = cache.read(path)
    return [str(col) for col in df.columns], [[_format_cell(value) for value in row] for row in df.to_numpy()]


def unified(
    job_dirs: dict[str, Path],
    cache: CsvCache,
    methods: set[str] | None = None,
    visible_groups: set[str] | None = None,
):
    methods = methods or {"fracture", "volk_hora"}
    groups = _group_jobs(job_dirs)
    if visible_groups is not None:
        groups = {name: jobs for name, jobs in groups.items() if name in visible_groups}

    fig, ax = new_figure()
    all_e1: list[float] = []
    all_e2: list[float] = []
    legend_items = 0
    for group_idx, (group, jobs) in enumerate(sorted(groups.items())):
        color = palette_color(group_idx)
        for method in sorted(methods):
            points = _limit_points(jobs, cache, method)
            if not points:
                continue
            points.sort(key=lambda item: item["e2"])
            all_e1.extend(point["e1"] for point in points)
            all_e2.extend(point["e2"] for point in points)
            marker, marker_size, method_label = method_marker(method)
            label = f"{group} - {METHOD_LABELS.get(method, method_label)}"
            ax.plot(
                [point["e2"] for point in points],
                [point["e1"] for point in points],
                color=color,
                marker=marker,
                markersize=marker_size,
                linewidth=1 if method == "fracture" else 0.5,
                linestyle="-",
                label=label,
            )
            legend_items += 1
    if not all_e1:
        return None, "No usable forming-limit data found"
    apply_fld_axes(ax, all_e1, all_e2, "Forming Limit Curve", legend_items=max(legend_items, 1))
    bottom_legend(fig, frameon=True, ncol=4)
    return fig, ""


def fld_for_jobs(
    jobs: dict[str, Path],
    cache: CsvCache,
    methods: set[str] | None = None,
    show_paths: bool = False,
):
    """FLD for one campaign of jobs, optionally overlaying each job's strain path."""
    methods = methods or {"fracture", "volk_hora"}
    fig, ax = new_figure()
    all_e1: list[float] = []
    all_e2: list[float] = []
    legend_items = 0

    if show_paths:
        labelled = False
        for name, path in jobs.items():
            sp_path = Path(path) / "strain_path.csv"
            if not sp_path.exists():
                continue
            try:
                df = cache.read(sp_path)
            except Exception:
                continue
            if not {"eps1_major", "eps2_minor"}.issubset(df.columns):
                continue
            data = df[["eps1_major", "eps2_minor"]].apply(pd.to_numeric, errors="coerce").dropna()
            if data.empty:
                continue
            ax.plot(
                data["eps2_minor"],
                data["eps1_major"],
                color="darkgray",
                linewidth=0.7,
                zorder=1,
                label="Strain paths" if not labelled else None,
            )
            labelled = True
            all_e1.extend(data["eps1_major"].tolist())
            all_e2.extend(data["eps2_minor"].tolist())
        if labelled:
            legend_items += 1

    for method_idx, method in enumerate(sorted(methods)):
        points = _limit_points(jobs, cache, method)
        if not points:
            continue
        points.sort(key=lambda item: item["e2"])
        all_e1.extend(point["e1"] for point in points)
        all_e2.extend(point["e2"] for point in points)
        marker, marker_size, method_label = method_marker(method)
        ax.plot(
            [point["e2"] for point in points],
            [point["e1"] for point in points],
            color=palette_color(method_idx),
            marker=marker,
            markersize=marker_size,
            linewidth=1,
            linestyle="-",
            zorder=3,
            label=METHOD_LABELS.get(method, method_label),
        )
        legend_items += 1
    if not all_e1:
        return None, "No usable forming-limit data found"
    apply_fld_axes(ax, all_e1, all_e2, "Forming Limit Diagram", legend_items=max(legend_items, 1))
    # In-axes legend: the bottom figure legend needs vertical room the embedded
    # viewer does not have.
    ax.legend(loc="best", fontsize=8, frameon=True, edgecolor="k", fancybox=False)
    fig.subplots_adjust(bottom=0.12)
    return fig, ""


def available_groups(job_dirs: dict[str, Path]) -> list[str]:
    return sorted(_group_jobs(job_dirs).keys())


def _group_jobs(job_dirs: dict[str, Path]) -> dict[str, dict[str, Path]]:
    grouped: dict[str, dict[str, Path]] = defaultdict(dict)
    for name, path in job_dirs.items():
        path = Path(path)
        parent = path.parent.name
        if parent.lower().startswith("flc") or "study" in parent.lower():
            group = _set_label(parent)
        else:
            group = "Direct jobs"
        grouped[group][name] = path
    return dict(grouped)


def _limit_points(jobs: dict[str, Path], cache: CsvCache, method: str) -> list[dict[str, float | str]]:
    points = []
    for name, path in jobs.items():
        fl_path = Path(path) / "forming_limits.csv"
        if not fl_path.exists():
            continue
        try:
            df = cache.read(fl_path)
        except Exception:
            continue
        if "method" not in df.columns:
            continue
        rows = df[df["method"] == method]
        if rows.empty:
            continue
        row = rows.iloc[0]
        e1 = pd.to_numeric(row.get("eps1_major"), errors="coerce")
        e2 = pd.to_numeric(row.get("eps2_minor"), errors="coerce")
        if pd.isna(e1) or pd.isna(e2):
            continue
        points.append({"name": name, "e1": float(e1), "e2": float(e2)})
    return points


def _set_label(dirname: str) -> str:
    match = re.match(r"(?:FLC_)?(\w+?)_t([\dp]+)_ang(\d+)(.*)", dirname)
    if not match:
        return dirname
    test = match.group(1).capitalize()
    thickness = match.group(2).replace("p", ".")
    angle = match.group(3)
    suffix = match.group(4).strip("_")
    label = f"{test} t={thickness} mm"
    if angle != "0":
        label += f" {angle} deg"
    if suffix:
        label += f" ({suffix})"
    return label


def _format_cell(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)

