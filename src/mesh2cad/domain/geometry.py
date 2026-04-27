from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Vec3 = NDArray[np.float64]


@dataclass(slots=True)
class Axis3D:
    origin: Vec3
    direction: Vec3


@dataclass(slots=True)
class Frame3D:
    origin: Vec3
    x_dir: Vec3
    y_dir: Vec3
    z_dir: Vec3


@dataclass(slots=True)
class BoundingBox:
    min_corner: Vec3
    max_corner: Vec3
