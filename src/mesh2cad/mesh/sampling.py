from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from mesh2cad.mesh.io import MeshData


@dataclass(slots=True)
class SampledCloud:
    points: NDArray[np.float64]
    normals: NDArray[np.float64] | None
    source_face_indices: NDArray[np.int64] | None


def sample_surface(mesh_data: MeshData, count: int = 20_000) -> SampledCloud:
    """Sample points uniformly from the mesh surface for downstream fitting."""
    if count <= 0:
        raise ValueError("count must be positive")

    points, face_indices = mesh_data.mesh.sample(count, return_index=True)
    normals = None

    if mesh_data.mesh.face_normals is not None and len(mesh_data.mesh.face_normals) > 0:
        normals = np.asarray(mesh_data.mesh.face_normals[face_indices], dtype=np.float64)

    return SampledCloud(
        points=np.asarray(points, dtype=np.float64),
        normals=normals,
        source_face_indices=np.asarray(face_indices, dtype=np.int64),
    )
