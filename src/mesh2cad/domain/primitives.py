from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from mesh2cad.domain.types import Confidence, PrimitiveKind

Vec3 = NDArray[np.float64]


@dataclass(slots=True)
class PrimitiveRegion:
    point_indices: list[int]
    face_indices: list[int] = field(default_factory=list)
    area: float = 0.0


@dataclass(slots=True)
class Primitive:
    kind: PrimitiveKind
    confidence: Confidence
    region: PrimitiveRegion


@dataclass(slots=True)
class PlanePrimitive(Primitive):
    origin: Vec3
    normal: Vec3


@dataclass(slots=True)
class CylinderPrimitive(Primitive):
    axis_origin: Vec3
    axis_direction: Vec3
    radius: float
    height_estimate: float | None = None
