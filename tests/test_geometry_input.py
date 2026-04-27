from __future__ import annotations

from pathlib import Path

import numpy as np

from mesh2cad.mesh.geometry_input import PointCloudData, load_geometry, point_cloud_to_meshdata
from mesh2cad.mesh.io import MeshData


def test_load_geometry_xyz_roundtrip(tmp_path: Path):
    pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    path = tmp_path / "t.xyz"
    np.savetxt(path, pts, fmt="%.8f")
    geom = load_geometry(path)
    assert isinstance(geom, PointCloudData)
    assert len(geom.points) == 4


def test_point_cloud_to_meshdata_sets_auxiliary_points(tmp_path: Path):
    pts = np.random.default_rng(1).random((120, 3))
    pc = PointCloudData(points=pts, normals=None, source_path=tmp_path / "c.xyz")
    md = point_cloud_to_meshdata(pc)
    assert isinstance(md, MeshData)
    assert md.auxiliary_surface_points is not None
    assert md.auxiliary_surface_points.shape == pts.shape
