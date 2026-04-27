from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from numpy.typing import NDArray


@dataclass(slots=True)
class MeshData:
    mesh: trimesh.Trimesh
    vertices: NDArray[np.float64]
    faces: NDArray[np.int64]
    vertex_normals: NDArray[np.float64] | None
    units: str | None
    source_path: Path
    auxiliary_surface_points: NDArray[np.float64] | None = field(
        default=None,
        metadata={"description": "Original scan points when the input was a point cloud."},
    )


def load_mesh(path: str | Path) -> MeshData:
    """Load a mesh file and normalize it to a single Trimesh instance."""
    source_path = Path(path).expanduser().resolve()
    loaded = trimesh.load(source_path, force="mesh")

    if isinstance(loaded, trimesh.Scene):
        mesh = trimesh.util.concatenate(
            tuple(
                geometry
                for geometry in loaded.geometry.values()
                if isinstance(geometry, trimesh.Trimesh)
            )
        )
    elif isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        raise TypeError(f"Unsupported geometry type: {type(loaded)!r}")

    if mesh.vertices.size == 0 or mesh.faces.size == 0:
        raise ValueError(f"Mesh at {source_path} has no vertices or faces.")

    if mesh.vertex_normals is None or len(mesh.vertex_normals) != len(mesh.vertices):
        vertex_normals = None
    else:
        vertex_normals = np.asarray(mesh.vertex_normals, dtype=np.float64)

    return MeshData(
        mesh=mesh,
        vertices=np.asarray(mesh.vertices, dtype=np.float64),
        faces=np.asarray(mesh.faces, dtype=np.int64),
        vertex_normals=vertex_normals,
        units=getattr(mesh, "units", None),
        source_path=source_path,
        auxiliary_surface_points=None,
    )
