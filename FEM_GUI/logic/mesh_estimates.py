from __future__ import annotations

import math
from dataclasses import dataclass

from .job_config import JobConfig


@dataclass(frozen=True)
class MeshEstimate:
    width: int
    in_plane: int
    solid: int
    method: str


def ceil_div(length: float, size: float) -> int:
    size = max(float(size), 1e-9)
    return max(1, int(math.ceil(max(float(length), 0.0) / size)))


def estimate_for_width(cfg: JobConfig, specimen_width: int) -> MeshEstimate:
    width = int(specimen_width)
    thickness_seeds = max(1, int(cfg.thickness_seeds))
    mesh_scale = float(cfg.mesh_factor)

    if width == 20:
        p_inner_x, p_circle_r, p_xz = 5.0, 55.0, 5.0
    else:
        p_inner_x, p_circle_r, p_xz = 10.0, 65.0, 5.0

    if cfg.bm_mesh_manual:
        p_inner_x = float(cfg.bm_p_inner_x)
        p_circle_r = float(cfg.bm_p_circle_r)
        p_xz = float(cfg.bm_p_xzplane_1)
        s1x = float(cfg.bm_mesh_section1_x)
        s1y = float(cfg.bm_mesh_section1_y)
        s2x = float(cfg.bm_mesh_section2_x)
        s2y = float(cfg.bm_mesh_section2_y)
        s3y = float(cfg.bm_mesh_section3_y)
        s31y = float(cfg.bm_mesh_section3_1_y)
        s4y = float(cfg.bm_mesh_section4_y)
        w200_s1 = float(cfg.bm_mesh_w200_section1)
        w200_s2 = float(cfg.bm_mesh_w200_section2)
        w200_s3 = float(cfg.bm_mesh_w200_section3)
        w200_s4 = float(cfg.bm_mesh_w200_section4)
        w200_p1 = float(cfg.bm_w200_section1_y)
        w200_p2 = float(cfg.bm_w200_section2_r)
        w200_p3 = float(cfg.bm_w200_section3_r)
    else:
        s1x = s1y = 0.2 * mesh_scale
        s2x = s2y = 0.4 * mesh_scale
        s3y = s31y = 0.8 * mesh_scale
        s4y = 1.2 * mesh_scale
        w200_s1 = 0.2 * mesh_scale
        w200_s2 = 0.4 * mesh_scale
        w200_s3 = 0.8 * mesh_scale
        w200_s4 = 0.4 * mesh_scale
        w200_p1, w200_p2, w200_p3 = 10.0, 20.0, 50.0

    if width == 200:
        quarter = math.pi / 4.0
        a1 = max(w200_p1, 0.0) ** 2
        a2 = max(quarter * w200_p2**2 - a1, 0.0)
        a3 = max(quarter * (w200_p3**2 - w200_p2**2), 0.0)
        a4 = max(quarter * (70.0**2 - w200_p3**2), 0.0)
        in_plane = (
            a1 / max(w200_s1**2, 1e-9)
            + a2 / max(w200_s2**2, 1e-9)
            + a3 / max(w200_s3**2, 1e-9)
            + a4 / max(w200_s4**2, 1e-9)
        )
        return MeshEstimate(width, int(round(in_plane)), int(round(in_plane * thickness_seeds)), "area")

    half_width = width / 2.0
    n1x = ceil_div(min(p_inner_x, half_width), s1x)
    n2x = ceil_div(max(half_width - p_inner_x, 0.0), s2x)
    n1y = ceil_div(p_xz, s1y)
    n2y = ceil_div(12.5 - p_xz, s2y)
    if width == 20:
        n3y = ceil_div(48.35 - 12.5, s3y)
        n31y = ceil_div(p_circle_r - 48.35, s31y)
    elif width == 50:
        n3y = ceil_div(58.21 - 12.5, s3y)
        n31y = ceil_div(p_circle_r - 58.21, s31y)
    else:
        n3y = ceil_div(p_circle_r - 12.5, s3y)
        n31y = 0
    n4y = ceil_div(70.0 - p_circle_r, s4y)
    in_plane = (n1x + n2x) * (n1y + n2y + n3y + n31y + n4y)
    return MeshEstimate(width, int(in_plane), int(in_plane * thickness_seeds), "seed")


def mesh_estimates(cfg: JobConfig, widths: list[int]) -> tuple[list[MeshEstimate], int]:
    sym_factor = 1.0 if cfg.enable_symmetries else 4.0
    estimates = []
    for width in widths:
        est = estimate_for_width(cfg, width)
        estimates.append(
            MeshEstimate(
                width=est.width,
                in_plane=int(round(est.in_plane * sym_factor)),
                solid=int(round(est.solid * sym_factor)),
                method=est.method,
            )
        )
    return estimates, sum(item.solid for item in estimates)


def suggest_resources(cell_count: int) -> dict[str, int | float | str]:
    cells = max(1, int(cell_count))
    suggested_cpus = int(math.ceil(cells / 10000.0))
    if suggested_cpus % 2:
        suggested_cpus += 1
    cpus = max(4, min(32, suggested_cpus))
    if cells <= 100000:
        hours = 24
    elif cells <= 400000:
        hours = 48
    else:
        hours = 72
    return {
        "num_cpus": cpus,
        "slurm_mem_per_cpu_gb": 4.0,
        "slurm_time_hours": hours,
        "slurm_time_limit": f"{hours:02d}:00:00",
        "abaqus_memory_percent": 90,
    }

