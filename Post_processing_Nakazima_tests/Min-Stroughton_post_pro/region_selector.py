#!/usr/bin/env python3
"""Region selection for the improved 3D curvature method (Min et al. 2017).

Determines the neck-centered local coordinate system and rectangular point
matrix from VIC-3D DIC data and a user-drawn crack line.

Paper reference:
    Min, Stoughton, Carsley, Lin (2017) — International Journal of Mechanical
    Sciences 123, pp. 238–252.

    Sec. 2.1 step (i): "a point matrix centered at the point O (i.e. the neck
    center), which has a length of W_Y and a width of W_X, is generated"

    Fig. 3: W_X is across the neck band (X-direction), W_Y is along the neck
    band (Y-direction).

Usage:
    from dic_loader import load_specimen
    from region_selector import RegionConfig, select_region

    dic = load_specimen("/path/to/specimen")
    region = select_region(dic)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Optional

import numpy as np

from dic_loader import DICData


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass
class RegionConfig:
    """Configuration for the neck-centered region selection.

    Paper-recommended ranges (Sec 4.1, 4.3):
        W_X: 2–8 mm (recommended: 2 mm for Nakazima, up to 8 mm for Marciniak)
        W_Y: 10–40 mm (recommended: 15–20 mm for Nakazima, 20–30 mm for Marciniak)
    """

    # Matrix dimensions [mm]
    W_X: float = 2.0    # width across neck band
    W_Y: float = 20.0   # length along neck band

    # Search band for neck centre O [mm]
    # The search band extends this far on each side of the crack line,
    # perpendicular to its direction.
    search_band_width: float = 10.0

    # Smoothing radius for eps1 peak search [mm]
    # A local mean over this radius is used instead of the raw maximum
    # to reduce DIC noise sensitivity.
    eps1_smoothing_radius: float = 1.5

    # Maximum allowed distance between selected O and the crack line [mm]
    max_neck_offset: float = 5.0

    # Minimum number of valid DIC points required inside the matrix
    min_points: int = 30

    # Minimum fraction of non-NaN points required (0..1)
    min_valid_fraction: float = 0.5

    # Frame index to use for neck centre search.
    # None = last pre-crack frame (default).
    search_frame_index: Optional[int] = None


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class RegionResult:
    """Selected neck-centered region for the 3D curvature method."""

    # Neck centre O in material coordinates [mm]
    O: np.ndarray                   # shape (2,)

    # Local basis vectors (in material XY plane)
    e_y: np.ndarray                 # unit vector along neck/crack band
    e_x: np.ndarray                 # unit vector across neck band (perp to e_y)

    # Matrix dimensions [mm]
    W_X: float
    W_Y: float
    W_X_requested: float
    W_Y_requested: float
    d_X: float
    d_Y: float
    N_X: int
    N_Y: int
    matrix_selection_mode: str

    # Indices of DIC points inside the matrix (into the n_points axis)
    point_ids: np.ndarray           # shape (n_selected,), dtype int

    # Local coordinates of selected points [mm]
    # s = projection along e_y (crack direction), n = projection along e_x
    s_local: np.ndarray             # shape (n_selected,)
    n_local: np.ndarray             # shape (n_selected,)
    column_index: np.ndarray        # shape (n_selected,), 0..N_X-1

    # Frame used for the selection
    search_frame_index: int
    search_frame_id: int

    # Quality metrics
    n_valid: int                    # valid DIC points inside matrix
    n_total_in_box: int             # total grid positions inside matrix
    valid_fraction: float           # n_valid / n_total_in_box
    dist_O_to_crack: float          # distance from O to nearest crack line point [mm]
    eps1_at_O: float                # local-average eps1 at the selected neck centre
    eps1_max_in_band: float         # maximum local-average eps1 in the search band

    # Crack-line conversion metadata
    crack_line_drawn_frame_id: Optional[int] = None
    crack_line_conversion_frame_id: Optional[int] = None
    crack_line_conversion_warning: Optional[str] = None

    # Warning flags
    warnings: list = field(default_factory=list)

    def to_local(self, xy: np.ndarray) -> tuple:
        """Project (N,2) material XY coordinates into local (s, n)."""
        rel = xy - self.O
        s = rel @ self.e_y
        n = rel @ self.e_x
        return s, n

    def __repr__(self) -> str:
        return (
            f"RegionResult(O=[{self.O[0]:.2f}, {self.O[1]:.2f}], "
            f"W_X={self.W_X}, W_Y={self.W_Y}, "
            f"n_points={self.n_valid}, "
            f"valid_frac={self.valid_fraction:.3f}, "
            f"eps1_at_O={self.eps1_at_O:.4f}, "
            f"warnings={self.warnings})"
        )


# ---------------------------------------------------------------------------
#  Crack-line utilities
# ---------------------------------------------------------------------------

def _crack_px_to_mm(
    crack_px: np.ndarray,
    x_px: np.ndarray,
    y_px: np.ndarray,
    u_px: np.ndarray,
    v_px: np.ndarray,
    X_mm: np.ndarray,
    Y_mm: np.ndarray,
) -> np.ndarray:
    """Convert crack pixel coordinates to material mm via nearest-neighbor.

    Parameters
    ----------
    crack_px : (N, 2) pixel coordinates of crack line
    x_px, y_px : (n_points,) DIC image coordinates
    u_px, v_px : (n_points,) DIC pixel displacements (deformed image)
    X_mm, Y_mm : (n_points,) DIC material coordinates

    Returns
    -------
    (N, 2) material coordinates [mm]
    """
    from scipy.spatial import cKDTree

    deformed_px = np.column_stack([x_px + u_px, y_px + v_px])
    tree = cKDTree(deformed_px)
    mm_pts = np.empty((len(crack_px), 2))
    for i, pt in enumerate(crack_px):
        _, idx = tree.query(pt)
        mm_pts[i] = [X_mm[idx], Y_mm[idx]]
    return mm_pts


def _crack_line_basis(crack_mm: np.ndarray):
    """Compute neck-band direction and centre from the crack line.

    Uses SVD of the centred crack points to find the principal direction,
    which is robust even with noisy or curved crack lines.

    Returns
    -------
    midpoint : (2,) geometric centroid of the crack line
    e_y : (2,) unit vector along the crack/neck band
    e_x : (2,) unit vector perpendicular to e_y
    """
    pts = crack_mm[:, :2]
    midpoint = np.mean(pts, axis=0)
    centred = pts - midpoint

    if len(pts) == 2:
        e_y = pts[1] - pts[0]
    else:
        _, _, Vt = np.linalg.svd(centred, full_matrices=False)
        e_y = Vt[0]
        # Ensure consistent orientation (align with endpoint direction)
        if np.dot(e_y, pts[-1] - pts[0]) < 0:
            e_y = -e_y

    e_y = e_y / np.linalg.norm(e_y)
    e_x = np.array([-e_y[1], e_y[0]])  # 90° CCW rotation

    return midpoint, e_y, e_x


def _point_to_line_distance(point: np.ndarray, crack_mm: np.ndarray) -> float:
    """Minimum distance from a point to the crack polyline."""
    pts = crack_mm[:, :2]
    min_dist = np.inf

    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        ab_len_sq = np.dot(ab, ab)
        if ab_len_sq < 1e-12:
            d = np.linalg.norm(point - a)
        else:
            t = np.clip(np.dot(point - a, ab) / ab_len_sq, 0.0, 1.0)
            proj = a + t * ab
            d = np.linalg.norm(point - proj)
        min_dist = min(min_dist, d)

    return float(min_dist)


def _vtk_path_for_frame(dic: DICData, frame_idx: int):
    """Return the cached VTK path for a loaded DIC frame."""
    from pathlib import Path

    specimen_dir = Path(dic.data_file_path).parent if dic.data_file_path else None
    if specimen_dir is None:
        raise FileNotFoundError("dic.data_file_path is not available")

    results_dir = specimen_dir / "Results"
    if not results_dir.is_dir():
        results_dir = specimen_dir

    frame_id = int(dic.frame_ids[frame_idx])
    vtk_path = results_dir / "__mesh" / f"mesh_{frame_id:05d}.vtk"
    if not vtk_path.is_file():
        raise FileNotFoundError(f"VTK frame not found: {vtk_path}")
    return vtk_path


def _load_vtk_point_arrays(dic: DICData, frame_idx: int) -> dict:
    """Load point arrays from the cached VTK file for one frame."""
    from dic_loader import _load_vtk_arrays

    return _load_vtk_arrays(_vtk_path_for_frame(dic, frame_idx))


def _median_grid_spacing(dic: DICData, frame_idx: int) -> tuple[float, float]:
    """Compute paper-style d_X and d_Y from adjacent DIC grid points.

    The VTK exports include the original DIC image grid coordinates ``x`` and
    ``y``.  Adjacent points in a row/column give the material point distances
    d_X and d_Y used in Min et al.'s N_X/N_Y definition.
    """
    arrays = _load_vtk_point_arrays(dic, frame_idx)
    pix_x = np.asarray(arrays["x"], dtype=float)
    pix_y = np.asarray(arrays["y"], dtype=float)
    X = np.asarray(arrays["X"], dtype=float)
    Y = np.asarray(arrays["Y"], dtype=float)

    dx_vals = []
    for py in np.unique(pix_y):
        ids = np.where(pix_y == py)[0]
        if len(ids) < 2:
            continue
        order = ids[np.argsort(pix_x[ids])]
        gaps = np.diff(pix_x[order])
        positive = gaps[gaps > 0]
        if len(positive) == 0:
            continue
        step = float(np.min(positive))
        for i0, i1, gap in zip(order[:-1], order[1:], gaps):
            if abs(float(gap) - step) <= 1e-9:
                dx_vals.append(
                    math.hypot(float(X[i1] - X[i0]), float(Y[i1] - Y[i0]))
                )

    dy_vals = []
    for px in np.unique(pix_x):
        ids = np.where(pix_x == px)[0]
        if len(ids) < 2:
            continue
        order = ids[np.argsort(pix_y[ids])]
        gaps = np.diff(pix_y[order])
        positive = gaps[gaps > 0]
        if len(positive) == 0:
            continue
        step = float(np.min(positive))
        for i0, i1, gap in zip(order[:-1], order[1:], gaps):
            if abs(float(gap) - step) <= 1e-9:
                dy_vals.append(
                    math.hypot(float(X[i1] - X[i0]), float(Y[i1] - Y[i0]))
                )

    if not dx_vals or not dy_vals:
        raise ValueError("Could not determine DIC grid spacings d_X and d_Y")

    return float(np.median(dx_vals)), float(np.median(dy_vals))


def _select_paper_point_matrix(
    mat_xy: np.ndarray,
    valid: np.ndarray,
    O: np.ndarray,
    e_y: np.ndarray,
    e_x: np.ndarray,
    cfg: RegionConfig,
    d_X: float,
    d_Y: float,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    int,
    int,
    float,
    float,
    int,
]:
    """Select the ceil-rounded paper matrix using nearest valid DIC points."""
    from scipy.spatial import cKDTree

    N_X = max(2, int(math.ceil(cfg.W_X / d_X + 1.0)))
    N_Y = max(2, int(math.ceil(cfg.W_Y / d_Y + 1.0)))
    W_X_eff = (N_X - 1) * d_X
    W_Y_eff = (N_Y - 1) * d_Y

    n_coords = (np.arange(N_X, dtype=float) - (N_X - 1) / 2.0) * d_X
    s_coords = (np.arange(N_Y, dtype=float) - (N_Y - 1) / 2.0) * d_Y

    target_s = []
    target_n = []
    target_col = []
    target_xy = []
    for ci, n_val in enumerate(n_coords):
        for sj in s_coords:
            target_s.append(float(sj))
            target_n.append(float(n_val))
            target_col.append(ci)
            target_xy.append(O + sj * e_y + n_val * e_x)

    target_s_arr = np.asarray(target_s, dtype=float)
    target_n_arr = np.asarray(target_n, dtype=float)
    target_col_arr = np.asarray(target_col, dtype=int)
    target_xy_arr = np.asarray(target_xy, dtype=float)

    candidate_ids = np.where(valid & np.isfinite(mat_xy).all(axis=1))[0]
    if len(candidate_ids) == 0:
        return (
            np.array([], dtype=int),
            np.array([], dtype=float),
            np.array([], dtype=float),
            np.array([], dtype=int),
            N_X,
            N_Y,
            W_X_eff,
            W_Y_eff,
            N_X * N_Y,
        )

    tree = cKDTree(mat_xy[candidate_ids])
    k_query = min(64, len(candidate_ids))
    dist, idx = tree.query(target_xy_arr, k=k_query)
    if k_query == 1:
        dist = dist[:, np.newaxis]
        idx = idx[:, np.newaxis]

    max_dist = 0.75 * max(d_X, d_Y)
    used = set()
    selected = []
    selected_s = []
    selected_n = []
    selected_col = []
    for ti in range(len(target_xy_arr)):
        chosen = None
        for dd, local_idx in zip(dist[ti], idx[ti]):
            if not np.isfinite(dd) or dd > max_dist:
                continue
            pid = int(candidate_ids[int(local_idx)])
            if pid in used:
                continue
            chosen = pid
            break
        if chosen is None:
            continue
        used.add(chosen)
        selected.append(chosen)
        selected_s.append(target_s_arr[ti])
        selected_n.append(target_n_arr[ti])
        selected_col.append(target_col_arr[ti])

    return (
        np.asarray(selected, dtype=int),
        np.asarray(selected_s, dtype=float),
        np.asarray(selected_n, dtype=float),
        np.asarray(selected_col, dtype=int),
        N_X,
        N_Y,
        W_X_eff,
        W_Y_eff,
        N_X * N_Y,
    )


# ---------------------------------------------------------------------------
#  Neck centre search
# ---------------------------------------------------------------------------

def _find_neck_centre(
    material_xy: np.ndarray,
    eps1: np.ndarray,
    valid: np.ndarray,
    crack_mm: np.ndarray,
    e_y: np.ndarray,
    e_x: np.ndarray,
    crack_midpoint: np.ndarray,
    cfg: RegionConfig,
):
    """Find neck centre O as the local-average eps1 maximum in a search band.

    Steps:
        1. Select all valid DIC points within search_band_width of the crack
           line (perpendicular distance).
        2. For each candidate point, compute the local mean of eps1 within
           eps1_smoothing_radius.
        3. The candidate with the highest smoothed eps1 becomes O.
        4. Constrain O to be within max_neck_offset of the crack line.

    Returns
    -------
    O : (2,) material coordinates of neck centre
    eps1_at_O : smoothed eps1 at O
    eps1_max : maximum smoothed eps1 in the band
    """
    # Project all points into crack-local coordinates
    rel = material_xy - crack_midpoint
    s = rel @ e_y   # along crack
    n = rel @ e_x   # across crack

    # Search band: perpendicular distance to crack line < search_band_width/2
    # and along-crack extent within reasonable range of the crack endpoints
    crack_s = (crack_mm[:, :2] - crack_midpoint) @ e_y
    s_min, s_max = crack_s.min(), crack_s.max()
    # Extend slightly beyond crack endpoints
    s_margin = 2.0  # mm
    in_band = (
        valid
        & (np.abs(n) <= cfg.search_band_width / 2.0)
        & (s >= s_min - s_margin)
        & (s <= s_max + s_margin)
        & np.isfinite(eps1)
    )

    band_ids = np.where(in_band)[0]
    if len(band_ids) == 0:
        raise ValueError("No valid DIC points found in the search band")

    # Compute local-average eps1 for each candidate
    from scipy.spatial import cKDTree
    band_xy = material_xy[band_ids]
    band_eps1 = eps1[band_ids]
    tree = cKDTree(band_xy)

    smoothed_eps1 = np.empty(len(band_ids))
    for i, pt in enumerate(band_xy):
        neighbours = tree.query_ball_point(pt, cfg.eps1_smoothing_radius)
        smoothed_eps1[i] = np.nanmean(band_eps1[neighbours])

    # Find maximum
    best = np.nanargmax(smoothed_eps1)
    O = band_xy[best].copy()
    eps1_at_O = float(smoothed_eps1[best])
    eps1_max = float(np.nanmax(smoothed_eps1))

    # Constrain: if O is too far from crack line, project it back
    dist = _point_to_line_distance(O, crack_mm)
    if dist > cfg.max_neck_offset:
        # Project O onto the nearest point on the crack polyline
        pts = crack_mm[:, :2]
        best_proj = None
        best_d = np.inf
        for j in range(len(pts) - 1):
            a, b = pts[j], pts[j + 1]
            ab = b - a
            ab_len_sq = np.dot(ab, ab)
            if ab_len_sq < 1e-12:
                proj = a.copy()
            else:
                t = np.clip(np.dot(O - a, ab) / ab_len_sq, 0.0, 1.0)
                proj = a + t * ab
            d = np.linalg.norm(O - proj)
            if d < best_d:
                best_d = d
                best_proj = proj
        O = best_proj
        dist = best_d

    return O, eps1_at_O, eps1_max, dist


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def select_region(
    dic: DICData,
    crack_mm: Optional[np.ndarray] = None,
    cfg: Optional[RegionConfig] = None,
) -> RegionResult:
    """Select the neck-centered point-matrix region.

    Parameters
    ----------
    dic : DICData
        Loaded DIC data from dic_loader.load_specimen().
    crack_mm : (N, 2) array, optional
        Crack line in material coordinates [mm]. If None, the crack line
        is converted from dic.crack_line (pixel coords) using the last
        pre-crack frame's DIC mesh.
    cfg : RegionConfig, optional
        Configuration. Uses defaults if None.

    Returns
    -------
    RegionResult with neck centre, basis, point IDs, and quality metrics.
    """
    if cfg is None:
        cfg = RegionConfig()

    warnings = []

    # --- Determine search frame ---
    if cfg.search_frame_index is not None:
        search_idx = cfg.search_frame_index
    else:
        search_idx = dic.n_frames - 1  # last pre-crack frame

    search_frame_id = int(dic.frame_ids[search_idx])

    # --- Convert crack line from pixels to mm if needed ---
    crack_line_drawn_frame_id = getattr(dic, "crack_line_frame_id", None)
    crack_conversion_frame_idx = None
    crack_conversion_frame_id = None
    crack_conversion_warning = None

    if crack_mm is None:
        if dic.crack_line is None:
            raise ValueError("No crack line available (neither crack_mm nor dic.crack_line)")

        # Determine which frame to use for pixel→mm mapping.
        # The crack line was drawn on crack_line_drawn_frame_id.  We should
        # use that frame for the conversion so pixel↔material mapping is
        # consistent with the image the user annotated.
        if crack_line_drawn_frame_id is not None:
            # Find array index for the drawn frame
            drawn_matches = np.where(dic.frame_ids == crack_line_drawn_frame_id)[0]
            if len(drawn_matches) > 0:
                conv_idx = int(drawn_matches[0])
            else:
                # Drawn frame was excluded (e.g. stop_at_crack removed it)
                # Fall back to last loaded frame
                conv_idx = search_idx
                crack_conversion_warning = (
                    f"crack_line_frame_id={crack_line_drawn_frame_id} not in "
                    f"loaded frames — falling back to search frame "
                    f"{int(dic.frame_ids[search_idx])}"
                )
                warnings.append(crack_conversion_warning)
        else:
            conv_idx = search_idx
            crack_conversion_warning = (
                "crack_line_frame_id not available — using search frame "
                f"{int(dic.frame_ids[search_idx])} for pixel→mm conversion"
            )
            warnings.append(crack_conversion_warning)

        crack_conversion_frame_idx = conv_idx
        crack_conversion_frame_id = int(dic.frame_ids[conv_idx])

        # Warn if conversion frame differs from drawn frame
        if (crack_line_drawn_frame_id is not None
                and crack_conversion_frame_id != crack_line_drawn_frame_id):
            w = (
                f"Crack line drawn on frame {crack_line_drawn_frame_id} "
                f"but converted using frame {crack_conversion_frame_id}"
            )
            if w not in warnings:
                warnings.append(w)

        crack_mm = _convert_crack_line(dic, conv_idx)

    if crack_mm.shape[0] < 2:
        raise ValueError("Crack line must have at least 2 points")

    # --- Crack-line basis ---
    crack_midpoint, e_y, e_x = _crack_line_basis(crack_mm)

    # --- Material XY at search frame ---
    mat_xy = np.column_stack([dic.X[search_idx], dic.Y[search_idx]])
    eps1 = dic.eps1[search_idx]
    valid = dic.valid[search_idx] & np.isfinite(eps1)

    # --- Find neck centre O ---
    O, eps1_at_O, eps1_max, dist_to_crack = _find_neck_centre(
        mat_xy, eps1, valid, crack_mm, e_y, e_x, crack_midpoint, cfg,
    )

    if dist_to_crack > cfg.max_neck_offset:
        warnings.append(
            f"Neck centre O is {dist_to_crack:.1f} mm from crack line "
            f"(max allowed: {cfg.max_neck_offset:.1f} mm)"
        )

    # --- Select the paper-defined N_X × N_Y matrix centred at O ---
    d_X, d_Y = _median_grid_spacing(dic, search_idx)
    (
        point_ids,
        s_selected,
        n_selected,
        column_index,
        N_X,
        N_Y,
        W_X_eff,
        W_Y_eff,
        n_total_in_box,
    ) = _select_paper_point_matrix(mat_xy, valid, O, e_y, e_x, cfg, d_X, d_Y)
    n_valid = len(point_ids)
    valid_fraction = n_valid / max(n_total_in_box, 1)

    if n_valid < n_total_in_box:
        warnings.append(
            f"Paper matrix requested {N_X}x{N_Y}={n_total_in_box} points, "
            f"but only {n_valid} targets matched valid DIC points"
        )

    # --- Validate ---
    if n_valid < cfg.min_points:
        warnings.append(
            f"Only {n_valid} valid points in matrix "
            f"(minimum: {cfg.min_points})"
        )

    if valid_fraction < cfg.min_valid_fraction:
        warnings.append(
            f"Valid fraction {valid_fraction:.2f} below threshold "
            f"{cfg.min_valid_fraction:.2f}"
        )

    # --- Build result ---
    return RegionResult(
        O=O,
        e_y=e_y,
        e_x=e_x,
        W_X=W_X_eff,
        W_Y=W_Y_eff,
        W_X_requested=cfg.W_X,
        W_Y_requested=cfg.W_Y,
        d_X=d_X,
        d_Y=d_Y,
        N_X=N_X,
        N_Y=N_Y,
        matrix_selection_mode="paper_grid_ceil",
        point_ids=point_ids,
        s_local=s_selected,
        n_local=n_selected,
        column_index=column_index,
        search_frame_index=search_idx,
        search_frame_id=search_frame_id,
        n_valid=n_valid,
        n_total_in_box=n_total_in_box,
        valid_fraction=valid_fraction,
        dist_O_to_crack=dist_to_crack,
        eps1_at_O=eps1_at_O,
        eps1_max_in_band=eps1_max,
        crack_line_drawn_frame_id=crack_line_drawn_frame_id,
        crack_line_conversion_frame_id=crack_conversion_frame_id,
        crack_line_conversion_warning=crack_conversion_warning,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
#  Internal: crack pixel → mm conversion
# ---------------------------------------------------------------------------

def _convert_crack_line(dic: DICData, frame_idx: int) -> np.ndarray:
    """Convert dic.crack_line (pixel coords) to material mm.

    Uses the DIC mesh at frame_idx. Because the loader stores material (X,Y)
    and displacements (U,V) but not pixel coordinates (x, y, u, v), we need
    to reload the VTK for that frame to get pixel fields.

    Falls back to a simpler approach if pixel fields are not available:
    approximate by using material coordinates directly (valid when the crack
    line was drawn on an early frame with small displacements).
    """
    # Try to load pixel coords from the VTK file
    try:
        from pathlib import Path
        # Reconstruct VTK path from dic metadata
        specimen_dir = Path(dic.data_file_path).parent if dic.data_file_path else None
        if specimen_dir is None:
            raise FileNotFoundError

        results_dir = specimen_dir / "Results"
        if not results_dir.is_dir():
            results_dir = specimen_dir

        mesh_dir = results_dir / "__mesh"
        frame_id = dic.frame_ids[frame_idx]
        vtk_path = mesh_dir / f"mesh_{frame_id:05d}.vtk"

        if not vtk_path.is_file():
            raise FileNotFoundError

        import vtk
        from vtk.util.numpy_support import vtk_to_numpy

        reader = vtk.vtkPolyDataReader()
        reader.SetFileName(str(vtk_path))
        reader.ReadAllScalarsOn()
        reader.Update()
        pd = reader.GetOutput().GetPointData()

        x_px = vtk_to_numpy(pd.GetArray("x")).ravel()
        y_px = vtk_to_numpy(pd.GetArray("y")).ravel()
        u_px = vtk_to_numpy(pd.GetArray("u")).ravel()
        v_px = vtk_to_numpy(pd.GetArray("v")).ravel()
        X_mm = vtk_to_numpy(pd.GetArray("X")).ravel()
        Y_mm = vtk_to_numpy(pd.GetArray("Y")).ravel()

        return _crack_px_to_mm(dic.crack_line, x_px, y_px, u_px, v_px, X_mm, Y_mm)

    except (FileNotFoundError, ImportError, TypeError):
        raise ValueError(
            "Cannot convert crack line from pixels to mm: "
            "VTK pixel fields (x, y, u, v) not accessible. "
            "Please provide crack_mm directly."
        )
