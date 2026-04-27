from __future__ import annotations

import numpy as np

from mesh2cad.cad.vector_utils import revolve_sketch_frame, sketch_plane_vectors, unit3


def test_sketch_plane_vectors_are_orthogonal():
    sp = {
        "origin": (1.0, 2.0, 3.0),
        "x_dir": (0.0, 1.0, 0.0),
        "z_dir": (1.0, 0.0, 0.0),
    }
    o, x_dir, z_dir = sketch_plane_vectors(sp)
    assert np.allclose(o, [1.0, 2.0, 3.0])
    assert abs(float(np.dot(x_dir, z_dir))) < 1e-6
    assert abs(float(np.linalg.norm(x_dir)) - 1.0) < 1e-6
    assert abs(float(np.linalg.norm(z_dir)) - 1.0) < 1e-6


def test_revolve_sketch_frame_is_right_handed():
    o, u, x_rad, y_norm = revolve_sketch_frame((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert abs(float(np.dot(u, x_rad))) < 1e-6
    assert abs(float(np.dot(u, y_norm))) < 1e-6
    assert abs(float(np.dot(x_rad, y_norm))) < 1e-6
    assert np.allclose(unit3(np.cross(x_rad, u)), y_norm)


def test_unit3_handles_degenerate():
    v = unit3((0.0, 0.0, 0.0))
    assert np.allclose(v, [0.0, 0.0, 1.0])
