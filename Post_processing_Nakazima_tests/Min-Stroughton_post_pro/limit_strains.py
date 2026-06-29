#!/usr/bin/env python3
"""Step 8: Extract forming-limit strains at the detected onset frame.

Extracts eps1_L, eps2_L at the neck centre O using configurable modes
(nearest point, local mean, matrix max, etc.).

Paper reference:
    Min et al. (2017), Sec. 2.2 / Fig. 12b:
    "Once this change in curvature is identified, one can simply extract
     the strain conditions, and the history of the strain path at point O"

Usage:
    from limit_strains import LimitStrainConfig, extract_limit_strains

    result = extract_limit_strains(onset, mat)
    print(result.report())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from curvature_matrix import CurvatureMatrixData
from onset_detection import OnsetDetectionResult


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass
class LimitStrainConfig:
    """Configuration for limit strain extraction."""

    # Extraction mode for the reported FLC point
    #   "local_mean_around_O"  — mean of points within radius of O (default)
    #   "nearest_O"            — single nearest point to O
    #   "matrix_max_eps1"      — point with highest eps1 in the matrix
    #   "full_matrix_mean"     — mean over all matrix points
    mode: str = "local_mean_around_O"

    # Radius [mm] for local neighbourhood around O
    local_radius: float = 1.5

    # Alternative: number of nearest neighbours (used if local_radius
    # captures fewer than this many points)
    min_local_points: int = 5

    # Warn if closest point to O is farther than this [mm]
    max_nearest_distance: float = 1.0

    # Warn if onset is within this many frames of crack
    min_gap_to_crack: int = 3


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class LimitStrainResult:
    """Forming-limit strain at the detected onset of localized necking."""

    # --- Detection status ---
    onset_found: bool
    reason: str                        # "ok" or failure reason

    # --- Onset location ---
    onset_frame_id: Optional[int]
    onset_time: Optional[float]

    # --- Reported FLC point ---
    eps1_L: float
    eps2_L: float
    strain_extraction_mode: str

    # --- Nearest point to O ---
    eps1_nearest_O: float
    eps2_nearest_O: float
    closest_point_id: Optional[int]    # DIC point ID
    closest_point_distance: float      # distance to O [mm]

    # --- Local neighbourhood around O ---
    eps1_local_mean: float
    eps2_local_mean: float
    eps1_local_std: float
    eps2_local_std: float
    local_point_count: int

    # --- Full matrix diagnostics ---
    eps1_matrix_mean: float
    eps2_matrix_mean: float
    eps1_matrix_max: float
    eps2_at_eps1_matrix_max: float

    # --- Strain path history at O (up to onset) ---
    # eps1_history[k], eps2_history[k] for k = 0..onset
    strain_path_history: Dict[str, np.ndarray]

    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"LimitStrainResult",
            f"",
            f"  onset found:              {self.onset_found}",
        ]
        if not self.onset_found:
            lines.append(f"  reason:                   {self.reason}")
            lines.append(f"  eps1_L:                   n/a")
            lines.append(f"  eps2_L:                   n/a")
        else:
            lines += [
                f"  onset frame:              {self.onset_frame_id}",
                f"  onset time:               {self.onset_time:.3f} s",
                f"",
                f"  eps1_L:                   {self.eps1_L:.4f}",
                f"  eps2_L:                   {self.eps2_L:.4f}",
                f"  extraction mode:          {self.strain_extraction_mode}",
                f"",
                f"  nearest O:                eps1={self.eps1_nearest_O:.4f}, "
                f"eps2={self.eps2_nearest_O:.4f} "
                f"(dist={self.closest_point_distance:.2f} mm)",
                f"  local mean (r={self.local_point_count} pts): "
                f"eps1={self.eps1_local_mean:.4f}, "
                f"eps2={self.eps2_local_mean:.4f} "
                f"(std: {self.eps1_local_std:.4f}, {self.eps2_local_std:.4f})",
                f"  matrix mean:              eps1={self.eps1_matrix_mean:.4f}, "
                f"eps2={self.eps2_matrix_mean:.4f}",
                f"  matrix max eps1:          eps1={self.eps1_matrix_max:.4f}, "
                f"eps2={self.eps2_at_eps1_matrix_max:.4f}",
            ]
        lines += [
            f"",
            f"  warnings:                 "
            f"{', '.join(self.warnings) if self.warnings else 'none'}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        if self.onset_found:
            return (
                f"LimitStrainResult(eps1_L={self.eps1_L:.4f}, "
                f"eps2_L={self.eps2_L:.4f}, "
                f"frame={self.onset_frame_id})"
            )
        return f"LimitStrainResult(onset_found=False)"


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def extract_limit_strains(
    onset: OnsetDetectionResult,
    mat: CurvatureMatrixData,
    cfg: Optional[LimitStrainConfig] = None,
) -> LimitStrainResult:
    """Extract forming-limit strains at the detected onset frame.

    Parameters
    ----------
    onset : OnsetDetectionResult
        Output of detect_onset() (Step 7).
    mat : CurvatureMatrixData
        Output of build_curvature_matrix() (Step 3).
    cfg : LimitStrainConfig, optional

    Returns
    -------
    LimitStrainResult with eps1_L, eps2_L, and diagnostics.
    """
    if cfg is None:
        cfg = LimitStrainConfig()

    warnings: List[str] = []
    nan = float("nan")

    # --- No onset ---
    if not onset.onset_found:
        return LimitStrainResult(
            onset_found=False,
            reason=onset.reason,
            onset_frame_id=None,
            onset_time=None,
            eps1_L=nan, eps2_L=nan,
            strain_extraction_mode=cfg.mode,
            eps1_nearest_O=nan, eps2_nearest_O=nan,
            closest_point_id=None, closest_point_distance=nan,
            eps1_local_mean=nan, eps2_local_mean=nan,
            eps1_local_std=nan, eps2_local_std=nan,
            local_point_count=0,
            eps1_matrix_mean=nan, eps2_matrix_mean=nan,
            eps1_matrix_max=nan, eps2_at_eps1_matrix_max=nan,
            strain_path_history={"time": np.array([]),
                                 "eps1": np.array([]),
                                 "eps2": np.array([])},
            warnings=[f"No onset detected: {onset.reason}"],
        )

    k = onset.onset_global_frame_index
    onset_frame_id = onset.onset_frame_id
    onset_time = onset.onset_time

    # --- Gap to crack check ---
    if mat.crack_frame is not None:
        crack_idx = None
        for i, fid in enumerate(mat.frame_ids):
            if fid >= mat.crack_frame:
                crack_idx = i
                break
        if crack_idx is not None:
            gap = crack_idx - k
            if gap < cfg.min_gap_to_crack:
                warnings.append(
                    f"Onset frame {onset_frame_id} is only {gap} frames "
                    f"before crack frame {mat.crack_frame}"
                )

    # --- Strains at onset frame for all matrix points ---
    e1 = mat.eps1[k, :]     # (n_sel,)
    e2 = mat.eps2[k, :]
    v = mat.valid[k, :]

    # --- Distance of each point to O in local coordinates ---
    dist_to_O = np.sqrt(mat.s_local ** 2 + mat.n_local ** 2)

    # --- Nearest point to O ---
    if not np.any(v):
        warnings.append("No valid points at onset frame — cannot extract strains")
        return LimitStrainResult(
            onset_found=True,
            reason="no_valid_points_at_onset",
            onset_frame_id=onset_frame_id,
            onset_time=onset_time,
            eps1_L=nan, eps2_L=nan,
            strain_extraction_mode=cfg.mode,
            eps1_nearest_O=nan, eps2_nearest_O=nan,
            closest_point_id=None, closest_point_distance=nan,
            eps1_local_mean=nan, eps2_local_mean=nan,
            eps1_local_std=nan, eps2_local_std=nan,
            local_point_count=0,
            eps1_matrix_mean=nan, eps2_matrix_mean=nan,
            eps1_matrix_max=nan, eps2_at_eps1_matrix_max=nan,
            strain_path_history={"time": np.array([]),
                                 "eps1": np.array([]),
                                 "eps2": np.array([])},
            warnings=warnings,
        )

    valid_dist = dist_to_O.copy()
    valid_dist[~v] = np.inf
    nearest_idx = int(np.argmin(valid_dist))  # index into matrix point arrays
    nearest_dist = float(dist_to_O[nearest_idx])
    nearest_pid = int(mat.point_ids[nearest_idx])
    eps1_nearest = float(e1[nearest_idx])
    eps2_nearest = float(e2[nearest_idx])

    if nearest_dist > cfg.max_nearest_distance:
        warnings.append(
            f"Closest point to O is {nearest_dist:.2f} mm away "
            f"(threshold: {cfg.max_nearest_distance:.1f} mm)"
        )

    # --- Local neighbourhood around O ---
    in_radius = v & (dist_to_O <= cfg.local_radius)
    n_local_pts = int(np.count_nonzero(in_radius))

    # Fall back to nearest N if too few in radius
    if n_local_pts < cfg.min_local_points:
        sorted_ids = np.argsort(valid_dist)
        n_use = min(cfg.min_local_points, len(sorted_ids))
        in_radius = np.zeros(len(dist_to_O), dtype=bool)
        in_radius[sorted_ids[:n_use]] = True
        in_radius &= v
        n_local_pts = int(np.count_nonzero(in_radius))
        if n_local_pts < cfg.min_local_points:
            warnings.append(
                f"Only {n_local_pts} valid points near O "
                f"(requested {cfg.min_local_points})"
            )

    if n_local_pts > 0:
        eps1_local_mean = float(np.nanmean(e1[in_radius]))
        eps2_local_mean = float(np.nanmean(e2[in_radius]))
        eps1_local_std = float(np.nanstd(e1[in_radius]))
        eps2_local_std = float(np.nanstd(e2[in_radius]))
    else:
        eps1_local_mean = eps1_nearest
        eps2_local_mean = eps2_nearest
        eps1_local_std = nan
        eps2_local_std = nan
        warnings.append("No valid local neighbourhood points, using nearest")

    # --- Full matrix diagnostics ---
    e1_valid = e1[v]
    e2_valid = e2[v]
    if len(e1_valid) > 0:
        eps1_mat_mean = float(np.nanmean(e1_valid))
        eps2_mat_mean = float(np.nanmean(e2_valid))
        max_idx = int(np.nanargmax(e1_valid))
        eps1_mat_max = float(e1_valid[max_idx])
        eps2_at_max = float(e2_valid[max_idx])
    else:
        eps1_mat_mean = eps2_mat_mean = eps1_mat_max = eps2_at_max = nan
        warnings.append("No valid strain data at onset frame")

    # --- Select reported FLC point ---
    if cfg.mode == "nearest_O":
        eps1_L = eps1_nearest
        eps2_L = eps2_nearest
    elif cfg.mode == "matrix_max_eps1":
        eps1_L = eps1_mat_max
        eps2_L = eps2_at_max
    elif cfg.mode == "full_matrix_mean":
        eps1_L = eps1_mat_mean
        eps2_L = eps2_mat_mean
    else:  # "local_mean_around_O" (default)
        eps1_L = eps1_local_mean
        eps2_L = eps2_local_mean

    # --- Strain path history at O (nearest point, all frames up to onset) ---
    hist_frames = np.arange(0, k + 1)
    eps1_hist = mat.eps1[hist_frames, nearest_idx]
    eps2_hist = mat.eps2[hist_frames, nearest_idx]
    time_hist = mat.time[hist_frames]

    strain_path_history = {
        "time": time_hist,
        "frame_ids": mat.frame_ids[hist_frames],
        "eps1": eps1_hist,
        "eps2": eps2_hist,
    }

    return LimitStrainResult(
        onset_found=True,
        reason="ok",
        onset_frame_id=onset_frame_id,
        onset_time=onset_time,
        eps1_L=eps1_L,
        eps2_L=eps2_L,
        strain_extraction_mode=cfg.mode,
        eps1_nearest_O=eps1_nearest,
        eps2_nearest_O=eps2_nearest,
        closest_point_id=nearest_pid,
        closest_point_distance=nearest_dist,
        eps1_local_mean=eps1_local_mean,
        eps2_local_mean=eps2_local_mean,
        eps1_local_std=eps1_local_std,
        eps2_local_std=eps2_local_std,
        local_point_count=n_local_pts,
        eps1_matrix_mean=eps1_mat_mean,
        eps2_matrix_mean=eps2_mat_mean,
        eps1_matrix_max=eps1_mat_max,
        eps2_at_eps1_matrix_max=eps2_at_max,
        strain_path_history=strain_path_history,
        warnings=warnings,
    )

