from __future__ import annotations

import os
import struct
from pathlib import Path

import numpy as np
from app.constants import FEM_GUI_DIR

_mpl_dir = FEM_GUI_DIR / ".cache" / "matplotlib"
_mpl_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_mpl_dir))

from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def read_stl_triangles(path: Path, max_faces: int = 4500) -> np.ndarray:
    data = Path(path).read_bytes()
    triangles = _read_binary_stl(data)
    if triangles is None:
        triangles = _read_ascii_stl(data.decode("utf-8", errors="ignore"))
    if triangles.size == 0:
        return triangles
    if len(triangles) > max_faces:
        step = max(1, int(np.ceil(len(triangles) / max_faces)))
        triangles = triangles[::step]
    return triangles


def punch_preview_figure(path: Path, theme) -> Figure:
    triangles = read_stl_triangles(path)
    fig = Figure(figsize=(5.8, 4.0), dpi=100)
    fig.patch.set_facecolor(theme.colors.panel)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(theme.colors.panel)
    if triangles.size == 0:
        ax.text2D(0.5, 0.5, "STL contains no triangles", transform=ax.transAxes, ha="center")
        return fig

    mesh = Poly3DCollection(
        triangles,
        facecolor="#8A929B",
        edgecolor="#313842",
        linewidths=0.08,
        alpha=0.96,
    )
    ax.add_collection3d(mesh)
    pts = triangles.reshape(-1, 3)
    center = pts.mean(axis=0)
    span = np.ptp(pts, axis=0)
    radius = max(float(span.max()) / 2.0, 1e-6)
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.view_init(elev=26, azim=-42)
    ax.set_axis_off()
    fig.tight_layout(pad=0)
    return fig


def _read_binary_stl(data: bytes) -> np.ndarray | None:
    if len(data) < 84:
        return None
    face_count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + face_count * 50
    if expected != len(data):
        return None
    triangles = np.empty((face_count, 3, 3), dtype=float)
    offset = 84
    for idx in range(face_count):
        values = struct.unpack_from("<12fH", data, offset)
        triangles[idx] = np.array(values[3:12], dtype=float).reshape(3, 3)
        offset += 50
    return triangles


def _read_ascii_stl(text: str) -> np.ndarray:
    vertices: list[list[float]] = []
    triangles: list[list[list[float]]] = []
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            try:
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            except ValueError:
                continue
            if len(vertices) == 3:
                triangles.append(vertices)
                vertices = []
    return np.array(triangles, dtype=float)
