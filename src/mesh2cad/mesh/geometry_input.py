from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import numpy as np
import trimesh
from numpy.typing import NDArray

from mesh2cad.mesh.io import MeshData, load_mesh
from mesh2cad.mesh.point_normals import estimate_point_normals_knn
from mesh2cad.mesh.sampling import SampledCloud


@dataclass(slots=True)
class PointCloudData:
    """Dense 3D samples without connectivity (path-based detection)."""

    points: NDArray[np.float64]
    normals: NDArray[np.float64] | None
    source_path: Path


GeometryInput = Union[MeshData, PointCloudData]

_POINT_CLOUD_SUFFIXES = {".xyz", ".pts", ".csv", ".npy"}


def load_geometry(path: str | Path) -> GeometryInput:
    """Load triangle mesh or ASCII/binary point cloud supported extensions."""
    source_path = Path(path).expanduser().resolve()
    suffix = source_path.suffix.lower()

    if suffix in _POINT_CLOUD_SUFFIXES:
        return _load_point_cloud_file(source_path)

    if suffix == ".ply":
        try:
            return load_mesh(source_path)
        except (TypeError, ValueError):
            return _load_ply_as_point_cloud(source_path)

    return load_mesh(source_path)


def _load_point_cloud_file(source_path: Path) -> PointCloudData:
    suffix = source_path.suffix.lower()
    if suffix == ".npy":
        arr = np.load(source_path, allow_pickle=False)
        pts = np.asarray(arr, dtype=np.float64).reshape(-1, 3)
    elif suffix == ".csv":
        pts = np.loadtxt(source_path, delimiter=",", dtype=np.float64)
        if pts.ndim == 1:
            pts = pts.reshape(1, -1)
        if pts.shape[1] < 3:
            raise ValueError("CSV point cloud must have at least three columns (x,y,z).")
        pts = pts[:, :3]
    else:
        pts = np.loadtxt(source_path, dtype=np.float64)
        if pts.ndim == 1:
            pts = pts.reshape(1, -1)
        if pts.shape[1] < 3:
            raise ValueError("Point cloud file must have at least three columns (x,y,z).")
        pts = pts[:, :3]

    if len(pts) < 3:
        raise ValueError(f"Not enough points in {source_path}.")

    return PointCloudData(points=pts, normals=None, source_path=source_path)


def _load_ply_as_point_cloud(source_path: Path) -> PointCloudData:
    data = trimesh.load(source_path, file_type="ply")
    if isinstance(data, trimesh.PointCloud):
        pts = np.asarray(data.vertices, dtype=np.float64)
        return PointCloudData(points=pts, normals=None, source_path=source_path)
    if isinstance(data, trimesh.Trimesh) and len(data.faces) == 0 and len(data.vertices) > 0:
        pts = np.asarray(data.vertices, dtype=np.float64)
        return PointCloudData(points=pts, normals=None, source_path=source_path)
    raise ValueError(f"PLY at {source_path} is not a point-only payload; use a mesh loader instead.")


def point_cloud_to_meshdata(cloud: PointCloudData, *, hull_vertex_cap: int = 8000) -> MeshData:
    """Convex hull proxy mesh for repair/validation hooks; preserves ``source_path``."""
    pts = np.asarray(cloud.points, dtype=np.float64)
    if len(pts) > hull_vertex_cap:
        rng = np.random.default_rng(0)
        idx = rng.choice(len(pts), size=hull_vertex_cap, replace=False)
        hull_pts = pts[idx]
    else:
        hull_pts = pts
    hull = trimesh.convex.convex_hull(hull_pts)
    vn = None
    if hull.vertex_normals is not None and len(hull.vertex_normals) == len(hull.vertices):
        vn = np.asarray(hull.vertex_normals, dtype=np.float64)
    return MeshData(
        mesh=hull,
        vertices=np.asarray(hull.vertices, dtype=np.float64),
        faces=np.asarray(hull.faces, dtype=np.int64),
        vertex_normals=vn,
        units=getattr(hull, "units", None),
        source_path=cloud.source_path,
        auxiliary_surface_points=pts,
    )


def build_sampled_cloud_from_points(cloud: PointCloudData, *, count: int) -> SampledCloud:
    pts = np.asarray(cloud.points, dtype=np.float64)
    nrm = cloud.normals if cloud.normals is not None else estimate_point_normals_knn(pts)
    if len(pts) <= count:
        return SampledCloud(points=pts, normals=nrm, source_face_indices=None)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(pts), size=count, replace=False)
    return SampledCloud(
        points=pts[idx],
        normals=nrm[idx],
        source_face_indices=None,
    )
