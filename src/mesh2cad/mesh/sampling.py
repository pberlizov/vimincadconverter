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
    """Sample points uniformly from the mesh surface for downstream fitting.

    The trimesh sampler relies on NumPy's global RNG. We temporarily seed it
    for reproducible primitive/feature inference on the same input mesh.
    """
    if count <= 0:
        raise ValueError("count must be positive")

    random_state = np.random.get_state()
    np.random.seed(0)
    try:
        points, face_indices = mesh_data.mesh.sample(count, return_index=True)
    finally:
        np.random.set_state(random_state)
    normals = None

    if mesh_data.mesh.face_normals is not None and len(mesh_data.mesh.face_normals) > 0:
        normals = np.asarray(mesh_data.mesh.face_normals[face_indices], dtype=np.float64)

    return SampledCloud(
        points=np.asarray(points, dtype=np.float64),
        normals=normals,
        source_face_indices=np.asarray(face_indices, dtype=np.int64),
    )
