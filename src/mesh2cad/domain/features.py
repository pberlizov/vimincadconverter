from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mesh2cad.domain.types import Confidence, FeatureKind


@dataclass(slots=True)
class Feature:
    kind: FeatureKind
    confidence: Confidence
    parameters: dict[str, Any]
    references: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BaseExtrudeFeature(Feature):
    profile_loops: list[list[tuple[float, float]]] = field(default_factory=list)
    depth: float = 0.0
    sketch_plane: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ThroughHoleFeature(Feature):
    center_xy: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    depth: float | None = None


@dataclass(slots=True)
class RevolveSolidFeature(Feature):
    """Solid of revolution: profile (radial, axial) in a pose-aware sketch plane; axis through ``axis_origin``."""

    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    radius: float = 0.0
    height: float = 0.0
    profile_rz: list[tuple[float, float]] = field(default_factory=list)
