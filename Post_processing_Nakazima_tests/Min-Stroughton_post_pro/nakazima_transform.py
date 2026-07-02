#!/usr/bin/env python3
"""Nakazima (D, R^Out) coordinate transform for the 3D curvature method.

Transforms deformed surface points into punch-centred coordinates:
    D     — arc length along each matrix column on the deformed surface
    R_out — radial distance from each point to the estimated punch centre O'

Paper reference:
    Min et al. (2017), Sec. 2.2, Eq. 2-3, Fig. 4-5:

    Punch centre:
        O' = (X_P, Y_P, Z_P - r_N - t_P)              (Eq. 2)
    Pole thickness:
        t_P(k) = t_0 * exp(-eps1_P(k) - eps2_P(k))    (Eq. 3)
    Radial coordinate:
        R^Out = ||point - O'||
    Arc-length coordinate:
        D = cumulative 3D distance along ordered deformed DIC points in
            each matrix column. This is the discrete VIC3D implementation
            of the paper's arc-distance coordinate.

    Reference subtraction (Eq. 6):
        R'^Out_{i,j}(k) = R^Out_{i,j}(k) - R^Out_{i,j}(M)

Usage:
    from nakazima_transform import NakazimaConfig, compute_nakazima_transform

    naka_cfg = NakazimaConfig(
        pole_mode="max_z",
        pole_search_center=(0.0, 0.0),
        pole_search_radius=15.0,
    )
    naka = compute_nakazima_transform(mat, M=72, cfg=naka_cfg)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import math

import numpy as np

from dic_loader import DICData
from curvature_matrix import CurvatureMatrixData


D_MODE_CUMULATIVE_DIC_ARC = "cumulative_dic_arc"
D_MODE_ALIASES = {
    D_MODE_CUMULATIVE_DIC_ARC: D_MODE_CUMULATIVE_DIC_ARC,
    "dic_surface_arc": D_MODE_CUMULATIVE_DIC_ARC,
    "deformed_cumulative_chord": D_MODE_CUMULATIVE_DIC_ARC,
}
D_DEFINITION = (
    "cumulative 3D distance along ordered deformed DIC points in each "
    "matrix column"
)
D_UNITS = "mm"
R_OUT_DEFINITION = (
    "distance from deformed DIC point to reconstructed punch center O_prime"
)


def _normalize_D_mode(mode: str) -> str:
    """Normalize legacy/internal D-mode labels to the paper-aligned label."""
    return D_MODE_ALIASES.get(mode, mode)


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass
class NakazimaConfig:
    """Configuration for the Nakazima coordinate transform."""

    # Punch geometry
    punch_radius: float = 50.0      # r_N [mm] (50.8 mm in paper, 50 mm typical)
    thickness: float = 1.25          # t_0 [mm] initial sheet thickness (A = 1.25 mm)

    # Pole detection mode:
    #   "max_z"     — point with max Z_def in an explicit search window
    #   "known_xy"  — use known reference coordinates (pole_xy)
    pole_mode: str = "max_z"

    # Known pole location in material coordinates [mm] (for "known_xy" mode)
    pole_xy: Optional[tuple] = None  # (X, Y)

    # Search centre for max_z pole detection [mm] in material coordinates.
    # Required when pole_mode="max_z".
    pole_search_center: Optional[tuple] = None

    # Search radius for max_z pole detection [mm]
    # Required when pole_mode="max_z".
    pole_search_radius: Optional[float] = None

    # Pole smoothing: average strains over this radius [mm] around the pole
    pole_strain_radius: float = 2.0

    # Z-axis sign convention:
    #   "z_up"   — punch pushes specimen upward (Z_P is max Z)
    #   "z_down" — punch pushes specimen downward (Z_P is min Z, |Z| largest)
    z_convention: str = "z_down"


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class NakazimaTransformResult:
    """Punch-centred coordinate transform for Nakazima tests."""

    # --- Per-frame, per-point fields (n_frames, n_sel) ---
    R_out: np.ndarray              # radial distance to O' [mm]
    R_prime_out: np.ndarray        # R_out - R_out[M] (reference-subtracted)
    D: np.ndarray                  # arc-length coordinate [mm]

    # --- Reference frame ---
    M: int                         # reference frame index
    M_frame_id: int
    M_time: float

    # --- Punch pole P(k) — per frame ---
    pole_xyz: np.ndarray           # (n_frames, 3) deformed pole position
    pole_point_id: np.ndarray      # (n_frames,) DIC point index (into full mesh)

    # --- Pole strain and thickness ---
    eps1_P: np.ndarray             # (n_frames,) major strain at pole
    eps2_P: np.ndarray             # (n_frames,) minor strain at pole
    t_P: np.ndarray                # (n_frames,) current pole thickness [mm]

    # --- Punch centre O'(k) ---
    O_prime: np.ndarray            # (n_frames, 3) punch centre

    # --- Configuration ---
    punch_radius: float
    thickness_0: float
    pole_mode: str
    pole_xy: Optional[tuple]           # explicit pole_xy if provided
    pole_search_center: np.ndarray     # (2,) search centre used for pole detection
    pole_search_radius: float          # search radius [mm], NaN for known_xy
    z_convention: str
    D_mode: str                        # "cumulative_dic_arc"
    D_definition: str
    D_units: str
    R_out_definition: str

    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"NakazimaTransformResult",
            f"",
            f"  punch radius:             {self.punch_radius} mm",
            f"  initial thickness:        {self.thickness_0} mm",
            f"  pole mode:                {self.pole_mode}",
            f"  pole_xy:                  {self.pole_xy}",
            f"  pole search centre:       ({self.pole_search_center[0]:.1f}, {self.pole_search_center[1]:.1f})",
            f"  pole search radius:       {self.pole_search_radius:.1f} mm",
            f"  z convention:             {self.z_convention}",
            f"  D mode:                   {self.D_mode}",
            f"  D definition:             {self.D_definition}",
            f"  D units:                  {self.D_units}",
            f"  R_out definition:         {self.R_out_definition}",
            f"  reference frame M:        index {self.M}, "
            f"frame {self.M_frame_id}, t={self.M_time:.3f} s",
            f"  t_P range:                "
            f"[{self.t_P.min():.4f}, {self.t_P.max():.4f}] mm",
            f"  R'_out at M (should ~0):  "
            f"max|R'[M]|={float(np.nanmax(np.abs(self.R_prime_out[self.M]))):.2e}",
            f"",
            f"  warnings:                 "
            f"{', '.join(self.warnings) if self.warnings else 'none'}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"NakazimaTransformResult(pole={self.pole_mode}, "
            f"M={self.M_frame_id})"
        )


# ---------------------------------------------------------------------------
#  Pole detection
# ---------------------------------------------------------------------------

def _find_pole_max_z(
    X_def: np.ndarray,
    Y_def: np.ndarray,
    Z_def: np.ndarray,
    valid: np.ndarray,
    search_center_xy: np.ndarray,
    search_radius: float,
    X_ref: np.ndarray,
    Y_ref: np.ndarray,
    z_convention: str,
) -> np.ndarray:
    """Find pole point index per frame using max |Z_def| in search window.

    The search is done in material (reference) coordinates so the window
    stays fixed across frames.

    Returns
    -------
    pole_idx : (n_frames,) int — index into the full DIC point array
    """
    n_frames = X_def.shape[0]
    # Search mask: material distance from search centre
    dist_ref = np.sqrt(
        (X_ref - search_center_xy[0]) ** 2
        + (Y_ref - search_center_xy[1]) ** 2
    )
    in_window = dist_ref <= search_radius

    pole_idx = np.zeros(n_frames, dtype=int)
    for k in range(n_frames):
        candidates = in_window & valid[k]
        if not np.any(candidates):
            # Fall back to global search
            candidates = valid[k]
        z = Z_def[k, candidates]
        if z_convention == "z_down":
            # Punch pushes down: pole has most negative Z (largest |Z|)
            local_idx = int(np.nanargmin(z))
        else:
            # Punch pushes up: pole has most positive Z
            local_idx = int(np.nanargmax(z))
        pole_idx[k] = int(np.where(candidates)[0][local_idx])

    return pole_idx


def _find_pole_known_xy(
    X_ref: np.ndarray,
    Y_ref: np.ndarray,
    pole_xy: tuple,
    n_frames: int,
) -> np.ndarray:
    """Find the DIC point nearest to known pole coordinates.

    Returns the same index for all frames (persistent point).
    """
    dist = np.sqrt(
        (X_ref - pole_xy[0]) ** 2
        + (Y_ref - pole_xy[1]) ** 2
    )
    idx = int(np.argmin(dist))
    return np.full(n_frames, idx, dtype=int)


# ---------------------------------------------------------------------------
#  Arc length
# ---------------------------------------------------------------------------

def _compute_cumulative_dic_arc(
    X_def: np.ndarray,
    Y_def: np.ndarray,
    Z_def: np.ndarray,
    s_local: np.ndarray,
    columns_mask: List[np.ndarray],
) -> np.ndarray:
    """Compute D for each column from ordered deformed DIC points.

    Points within each column are sorted by ``s_local``. For each frame,
    neighbour distances are computed from the measured deformed 3D DIC
    coordinates and accumulated from one end of the column. This is the
    practical discrete VIC3D implementation of the paper's arc-distance
    coordinate D.

    Returns
    -------
    D : (n_frames, n_sel) cumulative DIC surface arc distance [mm]
    """
    n_frames, n_sel = X_def.shape
    D = np.full((n_frames, n_sel), np.nan)

    for col_mask in columns_mask:
        col_ids = np.where(col_mask)[0]
        if len(col_ids) < 2:
            continue

        # Sort by s_local
        order = np.argsort(s_local[col_ids])
        sorted_ids = col_ids[order]

        for k in range(n_frames):
            x = X_def[k, sorted_ids]
            y = Y_def[k, sorted_ids]
            z = Z_def[k, sorted_ids]

            # Cumulative 3D distance along ordered deformed DIC points.
            dx = np.diff(x)
            dy = np.diff(y)
            dz = np.diff(z)
            ds = np.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
            d = np.zeros(len(sorted_ids))
            d[1:] = np.cumsum(ds)

            D[k, sorted_ids] = d

    return D


# Backward-compatible internal alias. The official exposed mode is
# ``cumulative_dic_arc``.
_compute_arc_chord = _compute_cumulative_dic_arc


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def compute_nakazima_transform(
    mat: CurvatureMatrixData,
    M: int,
    cfg: Optional[NakazimaConfig] = None,
    columns_mask: Optional[List[np.ndarray]] = None,
    dic: Optional[DICData] = None,
) -> NakazimaTransformResult:
    """Compute (D, R^Out) transform for Nakazima tests.

    Parameters
    ----------
    mat : CurvatureMatrixData
        Output of build_curvature_matrix() (Step 3).
    M : int
        Reference frame index.
    cfg : NakazimaConfig
    columns_mask : list of bool arrays, optional
        One mask per column (from SACConfig columns). If None, treats all
        points as one column for D computation.
    dic : DICData, optional
        Full DIC mesh data. When provided, pole detection searches the
        entire mesh (~10k-21k points) instead of just the narrow matrix
        strip (~400-500 points). Strongly recommended for Nakazima tests
        where the punch pole P is typically far from the neck zone.

    Returns
    -------
    NakazimaTransformResult
    """
    if cfg is None:
        raise ValueError(
            "compute_nakazima_transform requires explicit cfg. "
            "Use known_xy with pole_xy, or max_z with pole_search_center "
            "and pole_search_radius."
        )

    warnings: List[str] = []
    n_frames = len(mat.time)
    n_sel = len(mat.point_ids)

    # --- Choose search arrays: full DIC mesh or matrix-only ---
    if dic is not None:
        # Full mesh for pole search
        pole_X_ref = dic.X[0, :]       # reference coords (constant across frames)
        pole_Y_ref = dic.Y[0, :]
        pole_X_def = dic.X + dic.U     # deformed coords per frame
        pole_Y_def = dic.Y + dic.V
        pole_Z_def = dic.Z + dic.W
        pole_valid = dic.valid
        pole_eps1 = dic.eps1
        pole_eps2 = dic.eps2
    else:
        warnings.append(
            "No full DIC mesh provided — pole search restricted to "
            f"matrix points ({n_sel} pts in {mat.W_X:.0f}×{mat.W_Y:.0f} mm strip). "
            "Pole may be outside the matrix."
        )
        pole_X_ref = mat.X_ref
        pole_Y_ref = mat.Y_ref
        pole_X_def = mat.X_def
        pole_Y_def = mat.Y_def
        pole_Z_def = mat.Z_def
        pole_valid = mat.valid
        pole_eps1 = mat.eps1
        pole_eps2 = mat.eps2

    # --- Pole detection ---
    if cfg.pole_mode == "known_xy":
        if cfg.pole_xy is None:
            raise ValueError(
                "pole_mode='known_xy' requires explicit pole_xy=(X, Y). "
                "The user must provide the punch pole location in material "
                "coordinates. Do not rely on an implicit default."
            )
        pole_idx = _find_pole_known_xy(
            pole_X_ref, pole_Y_ref, cfg.pole_xy, n_frames,
        )
        search_center = np.array([np.nan, np.nan], dtype=float)
        search_radius = float("nan")
    elif cfg.pole_mode == "max_z":
        if cfg.pole_search_center is None:
            raise ValueError(
                "pole_mode='max_z' requires explicit pole_search_center=(X, Y)."
            )
        if cfg.pole_search_radius is None:
            raise ValueError(
                "pole_mode='max_z' requires explicit pole_search_radius."
            )
        # Explicit DIC/material coordinates, not the neck centre.
        search_center = np.array(cfg.pole_search_center, dtype=float)
        search_radius = float(cfg.pole_search_radius)
        pole_idx = _find_pole_max_z(
            pole_X_def, pole_Y_def, pole_Z_def,
            pole_valid,
            search_center, search_radius,
            pole_X_ref, pole_Y_ref,
            cfg.z_convention,
        )
    else:
        raise ValueError(f"Unknown pole_mode: {cfg.pole_mode}")

    # --- Pole position, strain, thickness per frame ---
    pole_xyz = np.empty((n_frames, 3))
    eps1_P = np.empty(n_frames)
    eps2_P = np.empty(n_frames)
    t_P = np.empty(n_frames)
    O_prime = np.empty((n_frames, 3))

    for k in range(n_frames):
        pi = pole_idx[k]
        pole_xyz[k] = [pole_X_def[k, pi], pole_Y_def[k, pi], pole_Z_def[k, pi]]

        # Pole strain: average over neighbourhood for robustness
        dist = np.sqrt(
            (pole_X_ref - pole_X_ref[pi]) ** 2
            + (pole_Y_ref - pole_Y_ref[pi]) ** 2
        )
        near = (dist <= cfg.pole_strain_radius) & pole_valid[k]
        if np.any(near):
            eps1_P[k] = float(np.nanmean(pole_eps1[k, near]))
            eps2_P[k] = float(np.nanmean(pole_eps2[k, near]))
        else:
            eps1_P[k] = float(pole_eps1[k, pi])
            eps2_P[k] = float(pole_eps2[k, pi])

        # Eq. 3: t_P(k) = t_0 * exp(-eps1_P - eps2_P)
        if np.isfinite(eps1_P[k]) and np.isfinite(eps2_P[k]):
            t_P[k] = cfg.thickness * math.exp(-eps1_P[k] - eps2_P[k])
        else:
            t_P[k] = cfg.thickness

        # Eq. 2: O' = (X_P, Y_P, Z_P - r_N - t_P)  for z_down
        #         O' = (X_P, Y_P, Z_P + r_N + t_P)  for z_up
        px, py, pz = pole_xyz[k]
        if cfg.z_convention == "z_down":
            O_prime[k] = [px, py, pz - cfg.punch_radius - t_P[k]]
        else:
            O_prime[k] = [px, py, pz + cfg.punch_radius + t_P[k]]

    # --- R_out[k, p] = ||point - O'[k]|| ---
    R_out = np.empty((n_frames, n_sel))
    for k in range(n_frames):
        dx = mat.X_def[k, :] - O_prime[k, 0]
        dy = mat.Y_def[k, :] - O_prime[k, 1]
        dz = mat.Z_def[k, :] - O_prime[k, 2]
        R_out[k, :] = np.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

    # --- Reference subtraction: R'_out = R_out - R_out[M] ---
    R_prime_out = R_out - R_out[M, :][np.newaxis, :]

    # --- D: arc-length coordinate ---
    if columns_mask is None:
        # Single column: all points
        columns_mask = [np.ones(n_sel, dtype=bool)]

    D = _compute_cumulative_dic_arc(
        mat.X_def, mat.Y_def, mat.Z_def,
        mat.s_local, columns_mask,
    )

    M_frame_id = int(mat.frame_ids[M])
    M_time = float(mat.time[M])

    return NakazimaTransformResult(
        R_out=R_out,
        R_prime_out=R_prime_out,
        D=D,
        M=M,
        M_frame_id=M_frame_id,
        M_time=M_time,
        pole_xyz=pole_xyz,
        pole_point_id=pole_idx,
        eps1_P=eps1_P,
        eps2_P=eps2_P,
        t_P=t_P,
        O_prime=O_prime,
        punch_radius=cfg.punch_radius,
        thickness_0=cfg.thickness,
        pole_mode=cfg.pole_mode,
        pole_xy=cfg.pole_xy,
        pole_search_center=search_center,
        pole_search_radius=search_radius,
        z_convention=cfg.z_convention,
        D_mode=_normalize_D_mode(D_MODE_CUMULATIVE_DIC_ARC),
        D_definition=D_DEFINITION,
        D_units=D_UNITS,
        R_out_definition=R_OUT_DEFINITION,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
#  Convenience: full Nakazima pipeline (replaces Steps 4-6 for Nakazima)
# ---------------------------------------------------------------------------

@dataclass
class ReferenceConfig:
    """Configuration for reference frame M selection.

    Use a manual mode when a wrapped reference frame is known, or
    ``time_fraction`` for a documented time-based selection rule.
    """

    # Reference selection mode:
    #   "manual_index"      — M is given as an array index (0-based)
    #   "manual_frame_id"   — M is given as a DIC frame ID
    #   "manual_time"       — M is the frame nearest to ref_time [s]
    #   "time_fraction"     — M is nearest to ref_fraction of recorded time
    reference_mode: str = "time_fraction"

    # Manual reference values (one must be set for manual modes)
    ref_index: Optional[int] = None
    ref_frame_id: Optional[int] = None
    ref_time: Optional[float] = None

    # Fraction of recorded physical time for time_fraction mode
    ref_fraction: float = 0.75


@dataclass
class ReferenceMetadata:
    """Metadata for the selected reference frame."""
    reference_mode: str
    reference_frame_index: int
    reference_frame_id: int
    reference_time: float
    reference_fraction: Optional[float]


def _select_reference_frame(
    mat: CurvatureMatrixData,
    ref_cfg: ReferenceConfig,
) -> tuple:
    """Select the reference frame M.

    Returns
    -------
    M : int
        Array index into mat.time / mat.frame_ids
    ref_meta : ReferenceMetadata
    """
    n_frames = len(mat.time)
    mode = ref_cfg.reference_mode
    ref_fraction_used = None

    if mode == "manual_index":
        if ref_cfg.ref_index is None:
            raise ValueError("reference_mode='manual_index' requires ref_index")
        M = ref_cfg.ref_index
        if M < 0 or M >= n_frames:
            raise ValueError(f"ref_index={M} out of range [0, {n_frames})")

    elif mode == "manual_frame_id":
        if ref_cfg.ref_frame_id is None:
            raise ValueError("reference_mode='manual_frame_id' requires ref_frame_id")
        matches = np.where(mat.frame_ids == ref_cfg.ref_frame_id)[0]
        if len(matches) == 0:
            raise ValueError(
                f"ref_frame_id={ref_cfg.ref_frame_id} not found in frame_ids "
                f"[{mat.frame_ids[0]}..{mat.frame_ids[-1]}]"
            )
        M = int(matches[0])

    elif mode == "manual_time":
        if ref_cfg.ref_time is None:
            raise ValueError("reference_mode='manual_time' requires ref_time")
        M = int(np.argmin(np.abs(mat.time - ref_cfg.ref_time)))

    elif mode == "time_fraction":
        if not 0.0 <= ref_cfg.ref_fraction <= 1.0:
            raise ValueError("ref_fraction must be in [0, 1] for time_fraction")
        ref_fraction_used = ref_cfg.ref_fraction
        t0 = float(mat.time[0])
        t1 = float(mat.time[-1])
        target_t = t0 + ref_cfg.ref_fraction * (t1 - t0)
        M = int(np.argmin(np.abs(mat.time - target_t)))
    else:
        raise ValueError(f"Unknown reference_mode: {mode!r}")

    ref_meta = ReferenceMetadata(
        reference_mode=mode,
        reference_frame_index=M,
        reference_frame_id=int(mat.frame_ids[M]),
        reference_time=float(mat.time[M]),
        reference_fraction=ref_fraction_used,
    )

    return M, ref_meta


def run_nakazima_pipeline(
    mat: CurvatureMatrixData,
    dic: Optional[DICData] = None,
    naka_cfg: Optional[NakazimaConfig] = None,
    ref_cfg: Optional[ReferenceConfig] = None,
    k_SAC: float = 5.0e-4,
    n_columns: Optional[int] = None,
    min_points_per_column: int = 8,
):
    """Run the full Nakazima branch: transform -> SAC -> circle fit -> signal.

    Replaces the Marciniak Z-based steps 4-6 with the (D, R^Out) transform.

    Parameters
    ----------
    ref_cfg : ReferenceConfig
        Explicit reference frame configuration.

    Returns
    -------
    signal : CurvatureSignal
    naka : NakazimaTransformResult
    ref_meta : ReferenceMetadata
    """
    from circle_fitting import FittingConfig, fit_circle, CurvatureSignal

    if naka_cfg is None:
        raise ValueError(
            "run_nakazima_pipeline requires explicit naka_cfg. "
            "Use known_xy with pole_xy, or max_z with pole_search_center "
            "and pole_search_radius."
        )

    n_frames = len(mat.time)
    n_sel = len(mat.point_ids)
    warnings: List[str] = []

    # --- Reference frame M ---
    if ref_cfg is None:
        raise ValueError(
            "run_nakazima_pipeline requires explicit ref_cfg. "
            "Use manual_index, manual_frame_id, manual_time, or time_fraction."
        )
    M, ref_meta = _select_reference_frame(mat, ref_cfg)

    # --- Build column masks ---
    if n_columns is None:
        n_columns = int(getattr(mat, "N_X", 5))

    columns_mask = []
    column_info = []
    matrix_col = getattr(mat, "column_index", None)
    use_paper_columns = matrix_col is not None and len(matrix_col) == n_sel
    if use_paper_columns:
        for ci in range(n_columns):
            mask = matrix_col == ci
            columns_mask.append(mask)

            col_s = mat.s_local[mask]
            n_pts = int(np.count_nonzero(mask))
            s_range = float(col_s.max() - col_s.min()) if n_pts > 1 else 0.0
            valid_for_fit = n_pts >= min_points_per_column and s_range >= 5.0
            column_info.append((ci, mask, n_pts, s_range, valid_for_fit))
    else:
        W_X = mat.W_X
        n_edges = np.linspace(-W_X / 2.0, W_X / 2.0, n_columns + 1)
        for ci in range(n_columns):
            n_lo, n_hi = n_edges[ci], n_edges[ci + 1]
            if ci == n_columns - 1:
                mask = (mat.n_local >= n_lo) & (mat.n_local <= n_hi)
            else:
                mask = (mat.n_local >= n_lo) & (mat.n_local < n_hi)
            columns_mask.append(mask)

            col_s = mat.s_local[mask]
            n_pts = int(np.count_nonzero(mask))
            s_range = float(col_s.max() - col_s.min()) if n_pts > 1 else 0.0
            valid_for_fit = n_pts >= min_points_per_column and s_range >= 5.0
            column_info.append((ci, mask, n_pts, s_range, valid_for_fit))

    # --- Nakazima transform ---
    naka = compute_nakazima_transform(mat, M, naka_cfg, columns_mask, dic=dic)
    warnings.extend(naka.warnings)

    # --- SAC on R'_out ---
    # SAC profile is defined at reference frame M and stays fixed:
    #   Z_SAC[p] = 0.5 * k_SAC * (D_M[p] - D_M_mean)^2
    # This is consistent with the Marciniak branch where SAC uses
    # reference-frame geometry. The fitting D-coordinate uses D[k]
    # (deformed arc length at each frame k).
    D_ref = naka.D[M, :]
    # Per-column SAC centring
    SAC_profile = np.full(n_sel, 0.0)
    for ci, mask, n_pts, s_range, valid_fit in column_info:
        if n_pts == 0:
            continue
        d_col = D_ref[mask]
        finite = np.isfinite(d_col)
        if finite.any():
            d_mean = float(np.nanmean(d_col[finite]))
            SAC_profile[mask] = 0.5 * k_SAC * (d_col - d_mean) ** 2

    # R''_out = R'_out + SAC
    R_double_prime = naka.R_prime_out + SAC_profile[np.newaxis, :]

    # --- Circle fitting per column per frame ---
    fit_frames = np.arange(M + 1, n_frames)
    n_fit = len(fit_frames)
    n_cols = n_columns

    C_col = np.full((n_fit, n_cols), np.nan)
    C_col_corr = np.full((n_fit, n_cols), np.nan)
    MSR_col = np.full((n_fit, n_cols), np.nan)
    radii = np.full((n_fit, n_cols), np.nan)
    centers_s = np.full((n_fit, n_cols), np.nan)
    centers_z = np.full((n_fit, n_cols), np.nan)
    n_pts_fit = np.zeros((n_fit, n_cols), dtype=int)
    fit_valid_arr = np.zeros((n_fit, n_cols), dtype=bool)

    fit_cfg = FittingConfig()

    for fi_idx, k in enumerate(fit_frames):
        for ci, mask, n_pts, s_range, valid_for_fit in column_info:
            if not valid_for_fit:
                continue

            d_col = naka.D[k, mask]
            r_col = R_double_prime[k, mask]
            v_col = mat.valid[k, mask]

            ok = v_col & np.isfinite(d_col) & np.isfinite(r_col)
            if np.count_nonzero(ok) < fit_cfg.min_fit_points:
                continue

            d_fit = d_col[ok]
            r_fit = r_col[ok]

            order = np.argsort(d_fit)
            d_fit = d_fit[order]
            r_fit = r_fit[order]

            result = fit_circle(d_fit, r_fit)
            if result is None:
                continue
            if result.radius > fit_cfg.max_radius or result.radius < fit_cfg.min_radius:
                continue

            C_col[fi_idx, ci] = result.curvature
            C_col_corr[fi_idx, ci] = result.curvature - k_SAC
            MSR_col[fi_idx, ci] = result.msr
            radii[fi_idx, ci] = result.radius
            centers_s[fi_idx, ci] = result.center_s
            centers_z[fi_idx, ci] = result.center_z
            n_pts_fit[fi_idx, ci] = result.n_points
            fit_valid_arr[fi_idx, ci] = True

    # --- Average C_pm ---
    n_valid_cols = np.sum(fit_valid_arr, axis=1).astype(int)
    C_pm = np.full(n_fit, np.nan)
    C_pm_corr = np.full(n_fit, np.nan)
    C_pm_std = np.full(n_fit, np.nan)
    C_pm_min = np.full(n_fit, np.nan)
    C_pm_max = np.full(n_fit, np.nan)
    MSR_pm = np.full(n_fit, np.nan)

    for i in range(n_fit):
        valid_mask = fit_valid_arr[i, :]
        if not np.any(valid_mask):
            continue
        vals = C_col[i, valid_mask]
        C_pm[i] = float(np.nanmean(vals))
        C_pm_corr[i] = C_pm[i] - k_SAC
        C_pm_std[i] = float(np.nanstd(vals))
        C_pm_min[i] = float(np.nanmin(vals))
        C_pm_max[i] = float(np.nanmax(vals))
        MSR_pm[i] = float(np.nanmean(MSR_col[i, valid_mask]))

    signal = CurvatureSignal(
        frame_indices=fit_frames,
        time=mat.time[fit_frames],
        frame_ids=mat.frame_ids[fit_frames],
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
        fit_valid=fit_valid_arr,
        n_valid_columns=n_valid_cols,
        k_SAC=k_SAC,
        M=M,
        M_frame_id=int(mat.frame_ids[M]),
        M_time=float(mat.time[M]),
        fit_input=None,  # no separate fit_input for Nakazima branch
        warnings=warnings,
    )

    return signal, naka, ref_meta
