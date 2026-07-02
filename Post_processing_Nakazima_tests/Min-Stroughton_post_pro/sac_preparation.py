#!/usr/bin/env python3
"""Step 5: Column construction and Superimposed Artificial Curvature (SAC).

Groups the matrix points into columns along the neck-band direction,
applies the SAC parabolic profile, and prepares everything for circle fitting.

Paper reference:
    Min et al. (2017), Sec. 2.1 step (iii):
    "the curvature C_pm is calculated by fitting an equation of a circle
     to the (Y, Z') coordinates [...] which are transformed by applying
     a superimposed artificial curvature (SAC), e.g. 2.5e-4 -- 5.0e-4 mm^-1,
     to the (Y, Z') coordinates in each column of the point matrix."

    The SAC-transformed coordinate is:
        Z''_{i,j}(k) = Z'_{i,j}(k) + 0.5 * k_SAC * s_centred^2

    where s_centred is the along-crack coordinate centred on the column.

Usage:
    from sac_preparation import SACConfig, prepare_for_fitting

    fit_input = prepare_for_fitting(ref_result)
    print(fit_input.report())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from reference_subtraction import ReferenceSubtractionResult


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass
class SACConfig:
    """Configuration for SAC application and column construction.

    Paper-recommended SAC values (Sec. 2.1, 4.2, 4.3):
        Marciniak: 2.5e-4 mm^-1
        Nakazima:  5.0e-4 mm^-1
    """

    # Superimposed Artificial Curvature [1/mm]
    k_SAC: float = 2.5e-4

    # Column binning: number of columns across W_X
    n_columns: int = 5

    # Minimum valid points per column for circle fitting
    min_points_per_column: int = 8

    # Minimum s-range per column [mm] — reject short columns
    min_s_range: float = 5.0


# ---------------------------------------------------------------------------
#  Column dataclass
# ---------------------------------------------------------------------------

@dataclass
class Column:
    """One column of matrix points running along the neck band (s-direction)."""

    index: int                     # column index (0..n_columns-1)
    n_center: float                # centre of the column bin in n_local [mm]
    n_lo: float                    # lower edge
    n_hi: float                    # upper edge

    # Indices into the matrix point arrays (point_ids, s_local, etc.)
    mask: np.ndarray               # (n_sel,) bool — which matrix points belong

    # Sorted along-crack coordinate [mm]
    s: np.ndarray                  # (n_col_pts,) sorted s_local values
    s_centred: np.ndarray          # (n_col_pts,) s - mean(s)

    # Point count and s-range
    n_points: int
    s_range: float                 # max(s) - min(s)

    valid_for_fitting: bool        # enough points and s-range?


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class CurvatureFitInput:
    """Prepared data for circle fitting (Step 6)."""

    # --- Frame range for fitting ---
    frame_indices_to_fit: np.ndarray   # indices into time axis (M+1 .. last)

    # --- Columns ---
    columns: List[Column]
    n_valid_columns: int

    # --- Per-point arrays (full matrix, n_sel points) ---
    point_ids: np.ndarray              # (n_sel,)
    s_local: np.ndarray                # (n_sel,)
    n_local: np.ndarray                # (n_sel,)

    # --- Field data (n_frames, n_sel) ---
    Z_prime: np.ndarray                # background-subtracted
    Z_double_prime: np.ndarray         # Z_prime + SAC
    valid: np.ndarray                  # bool mask

    # --- SAC ---
    k_SAC: float                       # applied SAC [1/mm]
    SAC_profile: np.ndarray            # (n_sel,) = 0.5 * k_SAC * s_centred^2

    # --- Reference info (passed through) ---
    M: int                             # reference frame index
    M_frame_id: int
    M_time: float
    time: np.ndarray                   # (n_frames,)
    frame_ids: np.ndarray              # (n_frames,)

    # --- Region geometry (passed through) ---
    O: np.ndarray
    e_x: np.ndarray
    e_y: np.ndarray
    W_X: float
    W_Y: float

    # --- Deformed geometry (for later R^Out transform) ---
    X_def: np.ndarray                  # (n_frames, n_sel)
    Y_def: np.ndarray
    Z_def: np.ndarray                  # original (not subtracted)

    # --- Strains (for limit strain extraction at onset) ---
    eps1: np.ndarray                   # (n_frames, n_sel)
    eps2: np.ndarray

    # --- Source reference ---
    ref_result: ReferenceSubtractionResult

    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        """Human-readable summary."""
        n_fit = len(self.frame_indices_to_fit)
        col_pts = [c.n_points for c in self.columns]
        col_s = [c.s_range for c in self.columns]
        lines = [
            f"CurvatureFitInput",
            f"",
            f"  SAC:                      {self.k_SAC:.2e} mm^-1",
            f"  frames to fit:            {n_fit} "
            f"(M+1={self.M + 1} .. {len(self.time) - 1})",
            f"  columns:                  {len(self.columns)} total, "
            f"{self.n_valid_columns} valid for fitting",
            f"  points per column:        {col_pts}",
            f"  s-range per column [mm]:  "
            f"[{min(col_s):.1f} .. {max(col_s):.1f}]",
            f"  SAC max contribution:     "
            f"{np.max(self.SAC_profile):.6f} mm",
            f"  Z' range (post-M):        "
            f"[{_post_M_range(self.Z_prime, self.M)}]",
            f"  Z'' range (post-M):       "
            f"[{_post_M_range(self.Z_double_prime, self.M)}]",
            f"  warnings:                 "
            f"{', '.join(self.warnings) if self.warnings else 'none'}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"CurvatureFitInput(k_SAC={self.k_SAC:.2e}, "
            f"columns={self.n_valid_columns}/{len(self.columns)}, "
            f"fit_frames={len(self.frame_indices_to_fit)})"
        )


def _post_M_range(arr: np.ndarray, M: int) -> str:
    post = arr[M + 1:]
    if post.size == 0:
        return "n/a"
    lo = float(np.nanmin(post))
    hi = float(np.nanmax(post))
    return f"{lo:.6f}, {hi:.6f}"


# ---------------------------------------------------------------------------
#  Column construction
# ---------------------------------------------------------------------------

def _build_columns(
    s_local: np.ndarray,
    n_local: np.ndarray,
    W_X: float,
    cfg: SACConfig,
) -> List[Column]:
    """Bin matrix points into columns across the neck band (n-direction)."""

    n_edges = np.linspace(-W_X / 2.0, W_X / 2.0, cfg.n_columns + 1)
    columns: List[Column] = []

    for ci in range(cfg.n_columns):
        n_lo = n_edges[ci]
        n_hi = n_edges[ci + 1]
        n_center = 0.5 * (n_lo + n_hi)

        # Select points in this column bin
        if ci == cfg.n_columns - 1:
            mask = (n_local >= n_lo) & (n_local <= n_hi)
        else:
            mask = (n_local >= n_lo) & (n_local < n_hi)

        col_s = s_local[mask]
        n_pts = len(col_s)

        if n_pts == 0:
            s_sorted = np.array([])
            s_centred = np.array([])
            s_range = 0.0
            valid_for_fitting = False
        else:
            order = np.argsort(col_s)
            s_sorted = col_s[order]
            s_centred = s_sorted - np.mean(s_sorted)
            s_range = float(s_sorted[-1] - s_sorted[0])
            valid_for_fitting = (
                n_pts >= cfg.min_points_per_column
                and s_range >= cfg.min_s_range
            )

        columns.append(Column(
            index=ci,
            n_center=float(n_center),
            n_lo=float(n_lo),
            n_hi=float(n_hi),
            mask=mask,
            s=s_sorted,
            s_centred=s_centred,
            n_points=n_pts,
            s_range=s_range,
            valid_for_fitting=valid_for_fitting,
        ))

    return columns


# ---------------------------------------------------------------------------
#  SAC profile
# ---------------------------------------------------------------------------

def _compute_sac_profile(
    s_local: np.ndarray,
    k_SAC: float,
) -> np.ndarray:
    """Compute the SAC parabolic profile for each matrix point.

    Z_SAC[p] = 0.5 * k_SAC * (s_local[p] - s_mean)^2

    The centering uses the global matrix s-mean so that all columns share
    the same SAC reference, consistent with the paper's approach of applying
    SAC "to the (Y, Z') coordinates in each column".
    """
    s_centred = s_local - np.mean(s_local)
    return 0.5 * k_SAC * s_centred ** 2


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def prepare_for_fitting(
    ref: ReferenceSubtractionResult,
    cfg: Optional[SACConfig] = None,
) -> CurvatureFitInput:
    """Prepare column-binned, SAC-augmented data for circle fitting.

    Parameters
    ----------
    ref : ReferenceSubtractionResult
        Output of apply_reference_subtraction() (Step 4).
    cfg : SACConfig, optional
        Configuration. Uses defaults if None.

    Returns
    -------
    CurvatureFitInput ready for Step 6 circle fitting.
    """
    if cfg is None:
        cfg = SACConfig()

    mat = ref.mat
    warnings: List[str] = []

    # --- Build columns ---
    columns = _build_columns(mat.s_local, mat.n_local, mat.W_X, cfg)
    n_valid_columns = sum(1 for c in columns if c.valid_for_fitting)

    if n_valid_columns == 0:
        warnings.append("No columns have enough points for circle fitting")

    # --- SAC profile ---
    SAC_profile = _compute_sac_profile(mat.s_local, cfg.k_SAC)

    # --- Z_double_prime ---
    # Z''[k,p] = Z'[k,p] + 0.5 * k_SAC * s_centred[p]^2
    Z_double_prime = ref.Z_prime + SAC_profile[np.newaxis, :]

    # --- Frame range for fitting ---
    n_frames = len(mat.time)
    frame_indices_to_fit = np.arange(ref.M + 1, n_frames)

    # Pass through Z_def (not subtracted) for later R^Out transform
    Z_def_original = mat.Z_def

    return CurvatureFitInput(
        frame_indices_to_fit=frame_indices_to_fit,
        columns=columns,
        n_valid_columns=n_valid_columns,
        point_ids=mat.point_ids,
        s_local=mat.s_local,
        n_local=mat.n_local,
        Z_prime=ref.Z_prime,
        Z_double_prime=Z_double_prime,
        valid=mat.valid,
        k_SAC=cfg.k_SAC,
        SAC_profile=SAC_profile,
        M=ref.M,
        M_frame_id=ref.M_frame_id,
        M_time=ref.M_time,
        time=mat.time,
        frame_ids=mat.frame_ids,
        O=mat.O,
        e_x=mat.e_x,
        e_y=mat.e_y,
        W_X=mat.W_X,
        W_Y=mat.W_Y,
        X_def=mat.X_def,
        Y_def=mat.Y_def,
        Z_def=Z_def_original,
        eps1=mat.eps1,
        eps2=mat.eps2,
        ref_result=ref,
        warnings=warnings,
    )

