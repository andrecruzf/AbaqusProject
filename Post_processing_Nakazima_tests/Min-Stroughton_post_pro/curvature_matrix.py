#!/usr/bin/env python3
"""Step 3: Time-resolved curvature matrix from persistent DIC point IDs.

Extracts all field histories (deformed geometry, strains, validity) for the
points selected by the region selector, ready for later curvature fitting.

No reference subtraction, SAC, or circle fitting is done here.

Usage:
    from dic_loader import load_specimen
    from region_selector import select_region
    from curvature_matrix import build_curvature_matrix

    dic = load_specimen("/path/to/specimen")
    region = select_region(dic)
    mat = build_curvature_matrix(dic, region)
    print(mat.report())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from dic_loader import DICData
from region_selector import RegionResult


@dataclass
class QualityMetrics:
    """Quality metrics for the curvature matrix."""

    n_points: int
    n_frames: int
    valid_fraction_per_frame: np.ndarray     # (n_frames,)
    min_valid_fraction: float
    last_fully_valid_frame_index: int        # last frame where all points valid


@dataclass
class CurvatureMatrixData:
    """Time-resolved field data for the curvature point matrix."""

    # --- Selected point indices (into DIC n_points axis) ---
    point_ids: np.ndarray          # (n_sel,)

    # --- Local coordinates [mm] ---
    s_local: np.ndarray            # (n_sel,)  along crack (e_y direction)
    n_local: np.ndarray            # (n_sel,)  across crack (e_x direction)

    # --- Reference (material) coordinates [mm] — constant across frames ---
    X_ref: np.ndarray              # (n_sel,)
    Y_ref: np.ndarray              # (n_sel,)
    Z_ref: np.ndarray              # (n_sel,)

    # --- Displacement histories [mm] — shape (n_frames, n_sel) ---
    U: np.ndarray
    V: np.ndarray
    W: np.ndarray

    # --- Deformed coordinate histories [mm] — shape (n_frames, n_sel) ---
    X_def: np.ndarray
    Y_def: np.ndarray
    Z_def: np.ndarray

    # --- Strain histories — shape (n_frames, n_sel) ---
    eps1: np.ndarray
    eps2: np.ndarray

    # --- Validity mask — shape (n_frames, n_sel) ---
    valid: np.ndarray              # dtype bool

    # --- Time / frame metadata ---
    time: np.ndarray               # (n_frames,)
    frame_ids: np.ndarray          # (n_frames,)
    crack_frame: Optional[int]
    last_valid_frame: int          # frame ID of last frame with full coverage
    selection_frame: int           # frame ID used for region selection

    # --- Region geometry ---
    O: np.ndarray                  # (2,) neck centre [mm]
    e_x: np.ndarray               # (2,) across crack
    e_y: np.ndarray               # (2,) along crack
    W_X: float
    W_Y: float
    W_X_requested: float
    W_Y_requested: float
    d_X: float
    d_Y: float
    N_X: int
    N_Y: int
    column_index: np.ndarray
    matrix_selection_mode: str

    # --- Tracking ---
    matrix_tracking_mode: str      # "persistent_dic_points"

    # --- Quality ---
    quality_metrics: QualityMetrics
    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        """Human-readable summary report."""
        qm = self.quality_metrics
        lines = [
            f"CurvatureMatrixData",
            f"",
            f"  tracking mode:            {self.matrix_tracking_mode}",
            f"  selected points:          {qm.n_points}",
            f"  paper matrix:             {self.N_X} x {self.N_Y}",
            f"  DIC spacing:              d_X={self.d_X:.4f} mm, "
            f"d_Y={self.d_Y:.4f} mm",
            f"  frames:                   {qm.n_frames}",
            f"  valid coverage:           {qm.min_valid_fraction:.0%}",
            f"  deformed coords available: yes",
            f"  strain histories available:yes",
            f"  warnings:                 {', '.join(self.warnings) if self.warnings else 'none'}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        qm = self.quality_metrics
        return (
            f"CurvatureMatrixData(n_points={qm.n_points}, "
            f"n_frames={qm.n_frames}, "
            f"valid={qm.min_valid_fraction:.0%}, "
            f"tracking='{self.matrix_tracking_mode}')"
        )


# ---------------------------------------------------------------------------
#  Builder
# ---------------------------------------------------------------------------

def build_curvature_matrix(
    dic: DICData,
    region: RegionResult,
) -> CurvatureMatrixData:
    """Build the time-resolved curvature matrix from DIC data + region.

    Parameters
    ----------
    dic : DICData
        Full DIC dataset from dic_loader.load_specimen().
    region : RegionResult
        Selected region from region_selector.select_region().
    Returns
    -------
    CurvatureMatrixData with all field histories for the selected points.
    """
    warnings: List[str] = []
    pid = region.point_ids
    n_sel = len(pid)
    n_frames = dic.n_frames

    # --- Validate point_ids ---
    s_local = region.s_local
    n_local = region.n_local
    column_index = region.column_index
    if np.any(pid < 0) or np.any(pid >= dic.n_points):
        bad = pid[(pid < 0) | (pid >= dic.n_points)]
        warnings.append(f"{len(bad)} point_ids out of bounds [0, {dic.n_points})")
        # Clamp to valid range — keep s_local/n_local in sync
        keep = (pid >= 0) & (pid < dic.n_points)
        pid = pid[keep]
        s_local = s_local[keep]
        n_local = n_local[keep]
        column_index = column_index[keep]
        n_sel = len(pid)

    # --- Reference coordinates (frame 0, but constant) ---
    X_ref = dic.X[0, pid].copy()
    Y_ref = dic.Y[0, pid].copy()
    Z_ref = dic.Z[0, pid].copy()

    # --- Displacement histories ---
    U = dic.U[:, pid].copy()
    V = dic.V[:, pid].copy()
    W = dic.W[:, pid].copy()

    # --- Deformed coordinates ---
    X_def = X_ref[np.newaxis, :] + U
    Y_def = Y_ref[np.newaxis, :] + V
    Z_def = Z_ref[np.newaxis, :] + W

    # --- Strain histories ---
    eps1 = dic.eps1[:, pid].copy()
    eps2 = dic.eps2[:, pid].copy()

    # --- Validity mask ---
    valid = dic.valid[:, pid].copy()

    # --- Time ---
    time = dic.time.copy()
    frame_ids = dic.frame_ids.copy()

    # --- Quality metrics ---
    valid_frac = valid.sum(axis=1) / max(n_sel, 1)
    min_valid_frac = float(valid_frac.min())

    # Last fully valid frame
    fully_valid = valid_frac >= 1.0 - 1e-9
    if np.any(fully_valid):
        last_fully_valid_idx = int(np.where(fully_valid)[0][-1])
    else:
        last_fully_valid_idx = 0
    last_valid_frame = int(frame_ids[last_fully_valid_idx])

    qm = QualityMetrics(
        n_points=n_sel,
        n_frames=n_frames,
        valid_fraction_per_frame=valid_frac,
        min_valid_fraction=min_valid_frac,
        last_fully_valid_frame_index=last_fully_valid_idx,
    )

    return CurvatureMatrixData(
        point_ids=pid,
        s_local=s_local,
        n_local=n_local,
        X_ref=X_ref,
        Y_ref=Y_ref,
        Z_ref=Z_ref,
        U=U, V=V, W=W,
        X_def=X_def, Y_def=Y_def, Z_def=Z_def,
        eps1=eps1, eps2=eps2,
        valid=valid,
        time=time,
        frame_ids=frame_ids,
        crack_frame=dic.crack_frame,
        last_valid_frame=last_valid_frame,
        selection_frame=region.search_frame_id,
        O=region.O,
        e_x=region.e_x,
        e_y=region.e_y,
        W_X=region.W_X,
        W_Y=region.W_Y,
        W_X_requested=region.W_X_requested,
        W_Y_requested=region.W_Y_requested,
        d_X=region.d_X,
        d_Y=region.d_Y,
        N_X=region.N_X,
        N_Y=region.N_Y,
        column_index=column_index,
        matrix_selection_mode=region.matrix_selection_mode,
        matrix_tracking_mode="persistent_dic_points",
        quality_metrics=qm,
        warnings=warnings,
    )
