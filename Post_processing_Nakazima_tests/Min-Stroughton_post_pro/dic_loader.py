#!/usr/bin/env python3
"""DIC VTK mesh loader for the Min-Stoughton curvature method.

Loads a specimen folder containing:
    Results/__mesh/mesh_XXXXX.vtk   (VIC-3D legacy VTK exports)
    Results/CrackData.txt           (crack frame + pixel coordinates)
    *_DataFile.txt                  (time/force/position per frame)

Returns a DICData dataclass with 2-D arrays (n_frames, n_points) for all
field quantities, plus metadata (times, frame IDs, crack info).

Usage:
    from dic_loader import load_specimen
    dic = load_specimen("/path/to/specimen_folder")
    print(dic.X.shape)       # (n_frames, n_points)
    print(dic.time)          # (n_frames,)
    print(dic.crack_frame)   # int
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class DICData:
    """Container for DIC field data loaded from VTK meshes."""

    # Material (reference) coordinates — constant across frames
    # shape: (n_frames, n_points)
    X: np.ndarray
    Y: np.ndarray
    Z: np.ndarray

    # Displacements — deformed = (X+U, Y+V, Z+W)
    # shape: (n_frames, n_points)
    U: np.ndarray
    V: np.ndarray
    W: np.ndarray

    # Principal strains
    # shape: (n_frames, n_points)
    eps1: np.ndarray
    eps2: np.ndarray

    # Validity mask (True = valid DIC correlation)
    # shape: (n_frames, n_points)
    valid: np.ndarray

    # Time vector — shape: (n_frames,)
    time: np.ndarray

    # Frame IDs (from VTK filenames) — shape: (n_frames,)
    frame_ids: np.ndarray

    # --- Metadata ---
    test_type: str = "nakazima"

    crack_frame: Optional[int] = None
    crack_line: Optional[np.ndarray] = None  # (N, 2) pixel coordinates
    crack_line_frame_id: Optional[int] = None  # frame on which crack_line was drawn

    # Optional extras
    n_points: int = 0
    n_frames: int = 0
    specimen_name: str = ""
    data_file_path: Optional[Path] = None

    time_source: str = "unknown"  # "physical_time" or "frame_id_fallback"

    def deformed_xyz(self, frame_idx: int) -> np.ndarray:
        """Return (n_points, 3) deformed coordinates for one frame."""
        return np.column_stack([
            self.X[frame_idx] + self.U[frame_idx],
            self.Y[frame_idx] + self.V[frame_idx],
            self.Z[frame_idx] + self.W[frame_idx],
        ])

    def __repr__(self) -> str:
        return (
            f"DICData(specimen='{self.specimen_name}', "
            f"n_frames={self.n_frames}, n_points={self.n_points}, "
            f"frames={self.frame_ids[0]}..{self.frame_ids[-1]}, "
            f"crack_frame={self.crack_frame})"
        )


# ---------------------------------------------------------------------------
#  VTK loading
# ---------------------------------------------------------------------------

def _load_vtk_arrays(vtk_path: Path) -> dict:
    """Load a legacy VTK file and return dict of 1-D numpy arrays."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(str(vtk_path))
    reader.ReadAllScalarsOn()
    reader.Update()
    poly = reader.GetOutput()

    pd = poly.GetPointData()
    arrays = {}
    for i in range(pd.GetNumberOfArrays()):
        name = pd.GetArrayName(i)
        arrays[name] = vtk_to_numpy(pd.GetArray(i)).ravel()
    return arrays


# ---------------------------------------------------------------------------
#  CrackData.txt parsing
# ---------------------------------------------------------------------------

def _parse_crack_data(crack_file: Path):
    """Parse CrackData.txt -> (crack_frame, crack_points_px).

    Format:
        Line 1:  <experiment_name>-<FRAME>_0.tiff,
        Line 2+: x_px,y_px
    """
    with open(crack_file) as f:
        header = f.readline().strip()
        # Extract frame number: e.g. "E0_RM00_000_W20_002-0600_0.tiff,"
        match = re.search(r"-(\d+)_\d+\.tiff", header)
        if match is None:
            raise ValueError(f"Cannot parse crack frame from: {header}")
        crack_frame = int(match.group(1))

        pts = []
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2 and parts[0]:
                pts.append([float(parts[0]), float(parts[1])])

    crack_line = np.array(pts) if pts else None
    # crack_line was drawn on the crack frame itself
    return crack_frame, crack_line, crack_frame


# ---------------------------------------------------------------------------
#  DataFile.txt parsing (time ↔ frame mapping)
# ---------------------------------------------------------------------------

def _parse_data_file(data_file: Path) -> dict:
    """Parse *_DataFile.txt -> {frame_number: time_seconds}.

    Format (semicolon-separated):
        Time [s]; Force [kN]; Position [mm]; LeftImg; RightImg; ...
        0.000;0.4600;0.0000;E0_RM00_000_W20_002-0093_0.tiff;...
    """
    frame_to_time = {}
    with open(data_file) as f:
        next(f)  # skip header
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 4 or not parts[3].strip():
                continue
            match = re.search(r"-(\d+)_\d+\.tiff", parts[3])
            if match is None:
                continue
            frame = int(match.group(1))
            frame_to_time[frame] = float(parts[0])
    return frame_to_time


# ---------------------------------------------------------------------------
#  Main loader
# ---------------------------------------------------------------------------

def load_specimen(
    specimen_dir: str | Path,
    test_type: str = "nakazima",
    stop_at_crack: bool = True,
) -> DICData:
    """Load DIC data from a specimen folder into a DICData container.

    The production pipeline assumes standard VIC-3D VTK export behavior
    (persistent point ordering, monotonic frame numbering), consistent
    with the existing IVP post-processing code.

    Parameters
    ----------
    specimen_dir : path
        Folder containing Results/__mesh/*.vtk, Results/CrackData.txt,
        and optionally *_DataFile.txt.
    test_type : str
        "nakazima" or "marciniak".
    stop_at_crack : bool
        If True, only load frames before the crack frame.
    Returns
    -------
    DICData with 2-D arrays (n_frames, n_points).
    """
    specimen_dir = Path(specimen_dir).resolve()
    results_dir = specimen_dir / "Results"
    mesh_dir = results_dir / "__mesh"

    if not mesh_dir.is_dir():
        # Maybe the path IS the Results dir
        if (specimen_dir / "__mesh").is_dir():
            results_dir = specimen_dir
            mesh_dir = specimen_dir / "__mesh"
            specimen_dir = specimen_dir.parent
        else:
            raise FileNotFoundError(f"No __mesh/ directory found at {mesh_dir}")

    # --- Discover VTK files, sorted by frame number ---
    vtk_files = sorted(mesh_dir.glob("mesh_*.vtk"),
                       key=lambda p: int(p.stem.split("_")[1]))
    if len(vtk_files) == 0:
        raise FileNotFoundError(f"No mesh_*.vtk files in {mesh_dir}")

    # --- Parse crack data ---
    crack_file = results_dir / "CrackData.txt"
    crack_frame = None
    crack_line = None
    crack_line_frame_id = None
    if crack_file.is_file():
        crack_frame, crack_line, crack_line_frame_id = _parse_crack_data(crack_file)

    # --- Parse time mapping ---
    data_files = sorted(specimen_dir.glob("*_DataFile.txt"))
    frame_to_time = {}
    data_file_path = None
    if data_files:
        data_file_path = data_files[0]
        frame_to_time = _parse_data_file(data_file_path)

    # --- Filter frames ---
    selected_vtk = []
    selected_frame_ids = []
    for vf in vtk_files:
        fid = int(vf.stem.split("_")[1])
        if stop_at_crack and crack_frame is not None and fid >= crack_frame:
            break
        selected_vtk.append(vf)
        selected_frame_ids.append(fid)

    if len(selected_vtk) == 0:
        raise ValueError("No frames to load (all at or after crack frame?)")

    # --- Load first frame to define the canonical point set ---
    first = _load_vtk_arrays(selected_vtk[0])
    n_frames = len(selected_vtk)

    # VIC-3D exports carry a persistent point-ID array ("index"). When points
    # drop out (loss of correlation) the per-frame point COUNT changes, so we
    # cannot assume identical ordering/length across frames. We therefore map
    # every frame onto the first frame's ID set: present points fill their
    # slot, missing points stay NaN/invalid. When all frames share the first
    # frame's ordering (constant count) this reproduces the old arrays exactly.
    has_index = "index" in first
    if has_index:
        canon_index = np.asarray(first["index"]).astype(np.int64)
        n_points = len(canon_index)
        # Sorted lookup so each frame's IDs map to canonical columns (vectorized)
        _order = np.argsort(canon_index)
        _sorted_ids = canon_index[_order]
    else:
        n_points = len(first["X"])

    # --- Allocate output arrays (NaN/invalid by default for missing points) ---
    X = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    Y = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    Z = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    U = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    V = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    W = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    eps1 = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    eps2 = np.full((n_frames, n_points), np.nan, dtype=np.float64)
    valid_mask = np.zeros((n_frames, n_points), dtype=bool)

    # --- Load all frames ---
    for i, vf in enumerate(selected_vtk):
        arrays = first if i == 0 else _load_vtk_arrays(vf)
        fn = len(arrays["X"])

        def _field(name, fill):
            return arrays[name] if name in arrays else np.full(fn, fill)

        if "sigma" in arrays:
            valid = arrays["sigma"] != -1
        else:
            valid = np.isfinite(arrays["X"])

        if has_index:
            # Map this frame's point IDs to canonical columns; drop any IDs not
            # present in the first frame.
            fid_ids = np.asarray(arrays["index"]).astype(np.int64)
            pos = np.clip(np.searchsorted(_sorted_ids, fid_ids), 0, len(_sorted_ids) - 1)
            match = _sorted_ids[pos] == fid_ids
            cols = _order[pos]
            c = cols[match]
            X[i, c] = arrays["X"][match]
            Y[i, c] = arrays["Y"][match]
            Z[i, c] = arrays["Z"][match]
            U[i, c] = _field("U", 0.0)[match]
            V[i, c] = _field("V", 0.0)[match]
            W[i, c] = _field("W", 0.0)[match]
            eps1[i, c] = _field("e1", np.nan)[match]
            eps2[i, c] = _field("e2", np.nan)[match]
            valid_mask[i, c] = valid[match]
        else:
            # No persistent IDs: require a constant point count (legacy path).
            if fn != n_points:
                raise ValueError(
                    f"Frame {selected_frame_ids[i]} has {fn} points but the "
                    f"first frame has {n_points}, and no 'index' field is "
                    "available to align them."
                )
            X[i] = arrays["X"]
            Y[i] = arrays["Y"]
            Z[i] = arrays["Z"]
            U[i] = _field("U", 0.0)
            V[i] = _field("V", 0.0)
            W[i] = _field("W", 0.0)
            eps1[i] = _field("e1", np.nan)
            eps2[i] = _field("e2", np.nan)
            valid_mask[i] = valid

    # --- Build time array ---
    frame_ids = np.array(selected_frame_ids, dtype=int)

    # Detect whether physical time is available or frame IDs used as fallback
    n_with_time = sum(1 for fid in frame_ids if fid in frame_to_time)
    if n_with_time == len(frame_ids):
        time_source = "physical_time"
    elif n_with_time == 0:
        time_source = "frame_id_fallback"
    else:
        time_source = "partial_physical_time"

    time_arr = np.array(
        [frame_to_time.get(fid, float(fid)) for fid in frame_ids],
        dtype=np.float64,
    )

    return DICData(
        X=X, Y=Y, Z=Z,
        U=U, V=V, W=W,
        eps1=eps1, eps2=eps2,
        valid=valid_mask,
        time=time_arr,
        frame_ids=frame_ids,
        test_type=test_type,
        crack_frame=crack_frame,
        crack_line=crack_line,
        crack_line_frame_id=crack_line_frame_id,
        n_points=n_points,
        n_frames=n_frames,
        specimen_name=specimen_dir.name,
        data_file_path=data_file_path,
        time_source=time_source,
    )

