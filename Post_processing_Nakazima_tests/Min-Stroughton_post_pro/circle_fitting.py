#!/usr/bin/env python3
"""Step 6: Circle fitting and C_pm(t) computation.

For each frame after M, fits circles to each column of the SAC-augmented
point matrix and averages to get the curvature signal C_pm(t).

Paper reference:
    Min et al. (2017), Sec. 2.1 step (iii):
    "the curvature C_pm is calculated by fitting an equation of a circle
     to the (Y, Z') coordinates [...] C_pm is the averaged curvature of
     the point matrix in the Y-axis direction."

    C_col = 1/R   (from circle fit to (s, Z'') per column)
    C_pm  = mean(C_col) over valid columns
    C_pm_corrected = C_pm - k_SAC   (remove artificial component)

Usage:
    from circle_fitting import FittingConfig, compute_curvature_signal

    signal = compute_curvature_signal(fit_input)
    print(signal.report())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import math

import numpy as np

from sac_preparation import CurvatureFitInput


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass
class FittingConfig:
    """Configuration for circle fitting."""

    # Minimum points for a valid circle fit
    min_fit_points: int = 5

    # Maximum allowed radius [mm] — reject if R > this (nearly flat)
    max_radius: float = 1e6

    # Minimum allowed radius [mm] — reject if R < this (unphysical)
    min_radius: float = 0.1


# ---------------------------------------------------------------------------
#  Circle fit (algebraic least squares)
# ---------------------------------------------------------------------------

@dataclass
class CircleFit:
    """Result of a single circle fit."""
    curvature: float       # 1/R [1/mm]
    radius: float          # R [mm]
    center_s: float        # a [mm]
    center_z: float        # b [mm]
    msr: float             # mean squared residual [mm^2]
    rmse: float            # root mean squared residual [mm]
    n_points: int
    valid: bool


def fit_circle(s: np.ndarray, z: np.ndarray) -> Optional[CircleFit]:
    """Algebraic least-squares circle fit to 2D points (s, z).

    Minimises sum of (s_i^2 + z_i^2 + A*s_i + B*z_i + C)^2
    which gives the linear system:
        [s, z, 1] @ [A, B, C]^T = -(s^2 + z^2)

    Circle parameters:
        centre = (-A/2, -B/2)
        R^2 = (A/2)^2 + (B/2)^2 - C

    Returns None if the fit fails or is degenerate.
    """
    s = np.asarray(s, dtype=float)
    z = np.asarray(z, dtype=float)
    ok = np.isfinite(s) & np.isfinite(z)
    s, z = s[ok], z[ok]
    n = len(s)

    if n < 3:
        return None

    # Build linear system
    A_mat = np.column_stack([s, z, np.ones(n)])
    b_vec = -(s ** 2 + z ** 2)

    try:
        coeffs, _, _, _ = np.linalg.lstsq(A_mat, b_vec, rcond=None)
    except np.linalg.LinAlgError:
        return None

    aa, bb, cc = coeffs
    cx = -0.5 * aa
    cz = -0.5 * bb
    r_sq = cx ** 2 + cz ** 2 - cc

    if not np.isfinite(r_sq) or r_sq <= 0.0:
        return None

    R = math.sqrt(r_sq)
    if R <= 0.0 or not np.isfinite(R):
        return None

    # Residuals
    dist = np.sqrt((s - cx) ** 2 + (z - cz) ** 2)
    residuals = dist - R
    msr = float(np.mean(residuals ** 2))
    rmse = math.sqrt(msr)

    return CircleFit(
        curvature=1.0 / R,
        radius=R,
        center_s=float(cx),
        center_z=float(cz),
        msr=msr,
        rmse=rmse,
        n_points=n,
        valid=True,
    )


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class CurvatureSignal:
    """C_pm(t) curvature signal from circle fitting."""

    # --- Frame axes ---
    frame_indices: np.ndarray      # (n_fit,) indices into full time axis
    time: np.ndarray               # (n_fit,) time values [s]
    frame_ids: np.ndarray          # (n_fit,) frame IDs

    # --- Per-column curvature (n_fit, n_columns) ---
    C_col: np.ndarray              # raw 1/R
    C_col_corrected: np.ndarray    # 1/R - k_SAC

    # --- Averaged curvature (n_fit,) ---
    C_pm: np.ndarray               # mean of valid C_col per frame
    C_pm_corrected: np.ndarray     # C_pm - k_SAC
    C_pm_std: np.ndarray           # std across columns
    C_pm_min: np.ndarray           # min across columns
    C_pm_max: np.ndarray           # max across columns

    # --- Fit quality (n_fit, n_columns) ---
    MSR_col: np.ndarray            # mean squared residual per column
    MSR_pm: np.ndarray             # average MSR across columns (n_fit,)

    # --- Per-fit metadata (n_fit, n_columns) ---
    radii: np.ndarray
    centers_s: np.ndarray
    centers_z: np.ndarray
    n_points_per_fit: np.ndarray   # int
    fit_valid: np.ndarray          # bool

    # --- Per-frame summary ---
    n_valid_columns: np.ndarray    # (n_fit,) int

    # --- SAC value ---
    k_SAC: float

    # --- Reference ---
    M: int
    M_frame_id: int
    M_time: float

    # --- Source ---
    fit_input: CurvatureFitInput

    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        """Human-readable summary."""
        n_fit = len(self.time)
        n_cols = self.C_col.shape[1]

        # Stats on C_pm_corrected (the signal we care about)
        cpc = self.C_pm_corrected
        finite = np.isfinite(cpc)
        if finite.any():
            cpc_mean = float(np.nanmean(cpc[finite]))
            cpc_max = float(np.nanmax(cpc[finite]))
            cpc_last = float(cpc[finite][-1]) if finite.any() else float("nan")
        else:
            cpc_mean = cpc_max = cpc_last = float("nan")

        msr_finite = self.MSR_pm[np.isfinite(self.MSR_pm)]
        msr_mean = float(np.mean(msr_finite)) if len(msr_finite) > 0 else float("nan")

        lines = [
            f"CurvatureSignal",
            f"",
            f"  frames fitted:            {n_fit}",
            f"  columns per frame:        {n_cols}",
            f"  valid columns (min/max):  "
            f"{int(self.n_valid_columns.min())}/{int(self.n_valid_columns.max())}",
            f"  k_SAC:                    {self.k_SAC:.2e} mm^-1",
            f"",
            f"  C_pm_corrected:",
            f"    mean:                   {cpc_mean:.6f} mm^-1",
            f"    max:                    {cpc_max:.6f} mm^-1",
            f"    last frame:             {cpc_last:.6f} mm^-1",
            f"",
            f"  MSR (mean):               {msr_mean:.2e} mm^2",
            f"",
            f"  warnings:                 "
            f"{', '.join(self.warnings) if self.warnings else 'none'}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"CurvatureSignal(n_frames={len(self.time)}, "
            f"C_pm_corrected_max={float(np.nanmax(self.C_pm_corrected)):.6f})"
        )


# ---------------------------------------------------------------------------
#  Main computation
# ---------------------------------------------------------------------------

def compute_curvature_signal(
    fit_input: CurvatureFitInput,
    cfg: Optional[FittingConfig] = None,
) -> CurvatureSignal:
    """Fit circles per column per frame and compute C_pm(t).

    Parameters
    ----------
    fit_input : CurvatureFitInput
        Output of prepare_for_fitting() (Step 5).
    cfg : FittingConfig, optional

    Returns
    -------
    CurvatureSignal with C_pm(t) and per-column details.
    """
    if cfg is None:
        cfg = FittingConfig()

    warnings: List[str] = []

    fi = fit_input
    fit_frames = fi.frame_indices_to_fit
    n_fit = len(fit_frames)
    columns = fi.columns
    valid_columns = [c for c in columns if c.valid_for_fitting]
    n_cols = len(columns)

    if len(valid_columns) == 0:
        warnings.append("No valid columns — cannot fit curvature")

    # --- Allocate output arrays ---
    C_col = np.full((n_fit, n_cols), np.nan)
    C_col_corr = np.full((n_fit, n_cols), np.nan)
    MSR_col = np.full((n_fit, n_cols), np.nan)
    radii = np.full((n_fit, n_cols), np.nan)
    centers_s = np.full((n_fit, n_cols), np.nan)
    centers_z = np.full((n_fit, n_cols), np.nan)
    n_pts_fit = np.zeros((n_fit, n_cols), dtype=int)
    fit_valid = np.zeros((n_fit, n_cols), dtype=bool)

    # --- Fit each frame × column ---
    for fi_idx, k in enumerate(fit_frames):
        for col in valid_columns:
            ci = col.index
            # Get points in this column
            col_mask = col.mask
            s_col = fi.s_local[col_mask]
            z_col = fi.Z_double_prime[k, col_mask]
            v_col = fi.valid[k, col_mask]

            # Apply validity
            ok = v_col & np.isfinite(s_col) & np.isfinite(z_col)
            if np.count_nonzero(ok) < cfg.min_fit_points:
                continue

            s_fit = s_col[ok]
            z_fit = z_col[ok]

            # Sort by s
            order = np.argsort(s_fit)
            s_fit = s_fit[order]
            z_fit = z_fit[order]

            # Fit circle
            result = fit_circle(s_fit, z_fit)
            if result is None:
                continue

            # Validate fit
            if result.radius > cfg.max_radius:
                continue
            if result.radius < cfg.min_radius:
                continue

            C_col[fi_idx, ci] = result.curvature
            C_col_corr[fi_idx, ci] = result.curvature - fi.k_SAC
            MSR_col[fi_idx, ci] = result.msr
            radii[fi_idx, ci] = result.radius
            centers_s[fi_idx, ci] = result.center_s
            centers_z[fi_idx, ci] = result.center_z
            n_pts_fit[fi_idx, ci] = result.n_points
            fit_valid[fi_idx, ci] = True

    # --- Average across columns ---
    n_valid_cols = np.sum(fit_valid, axis=1).astype(int)

    C_pm = np.full(n_fit, np.nan)
    C_pm_corr = np.full(n_fit, np.nan)
    C_pm_std = np.full(n_fit, np.nan)
    C_pm_min = np.full(n_fit, np.nan)
    C_pm_max = np.full(n_fit, np.nan)
    MSR_pm = np.full(n_fit, np.nan)

    for i in range(n_fit):
        valid_mask = fit_valid[i, :]
        if not np.any(valid_mask):
            continue
        vals = C_col[i, valid_mask]
        C_pm[i] = float(np.nanmean(vals))
        C_pm_corr[i] = C_pm[i] - fi.k_SAC
        C_pm_std[i] = float(np.nanstd(vals))
        C_pm_min[i] = float(np.nanmin(vals))
        C_pm_max[i] = float(np.nanmax(vals))
        MSR_pm[i] = float(np.nanmean(MSR_col[i, valid_mask]))

    # --- Warnings ---
    # Check for frames with no valid fits
    n_no_fit = int(np.sum(n_valid_cols == 0))
    if n_no_fit > 0:
        warnings.append(f"{n_no_fit} frames have no valid circle fits")

    return CurvatureSignal(
        frame_indices=fit_frames,
        time=fi.time[fit_frames],
        frame_ids=fi.frame_ids[fit_frames],
        C_col=C_col,
        C_col_corrected=C_col_corr,
        C_pm=C_pm,
        C_pm_corrected=C_pm_corr,
        C_pm_std=C_pm_std,
        C_pm_min=C_pm_min,
        C_pm_max=C_pm_max,
        MSR_col=MSR_col,
        MSR_pm=MSR_pm,
        radii=radii,
        centers_s=centers_s,
        centers_z=centers_z,
        n_points_per_fit=n_pts_fit,
        fit_valid=fit_valid,
        n_valid_columns=n_valid_cols,
        k_SAC=fi.k_SAC,
        M=fi.M,
        M_frame_id=fi.M_frame_id,
        M_time=fi.M_time,
        fit_input=fit_input,
        warnings=warnings,
    )
