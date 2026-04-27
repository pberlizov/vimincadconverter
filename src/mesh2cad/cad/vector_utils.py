from __future__ import annotations

from typing import Any

import numpy as np


def as_float3(value: Any) -> np.ndarray:
    """Coerce ndarray, list, or tuple to shape (3,) float64."""
    if value is None:
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)
    arr = np.asarray(value, dtype=np.float64).reshape(3)
    return arr


def unit3(value: Any) -> np.ndarray:
    v = as_float3(value)
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return v / n


def format_tuple3(v: Any) -> str:
    a = as_float3(v)
    return f"({float(a[0]):.6f}, {float(a[1]):.6f}, {float(a[2]):.6f})"


def sketch_plane_vectors(sketch_plane: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (origin, x_dir unit, z_dir unit) for build123d Plane(origin, x_dir=, z_dir=). z_dir is sketch normal / extrusion direction."""
    origin = as_float3(sketch_plane.get("origin", (0.0, 0.0, 0.0)))
    x_dir = unit3(sketch_plane.get("x_dir", (1.0, 0.0, 0.0)))
    z_dir = unit3(sketch_plane.get("z_dir", (0.0, 0.0, 1.0)))
    if abs(float(np.dot(x_dir, z_dir))) > 0.99:
        x_dir = unit3(perpendicular_to(z_dir))
    return origin, x_dir, z_dir


def perpendicular_to(axis: np.ndarray) -> np.ndarray:
    a = unit3(axis)
    ref = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    if abs(float(np.dot(ref, a))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    out = np.cross(a, ref)
    return unit3(out)


def revolve_sketch_frame(axis_origin: Any, axis_direction: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Return (origin, u_axis, x_radial, y_plane_normal) for:
    - revolution axis along unit vector u through origin O
    - sketch 2D (r, z) maps to O + r * x_radial + z * u in 3D
    - y_plane_normal = x_radial × u (sketch plane normal for Plane(..., x_dir=x_radial, z_dir=y_plane_normal))
    """
    o = as_float3(axis_origin)
    u = unit3(axis_direction)
    x_rad = perpendicular_to(u)
    y_norm = np.cross(x_rad, u)
    y_norm = unit3(y_norm)
    return o, u, x_rad, y_norm
