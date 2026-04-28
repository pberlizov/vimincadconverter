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
    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)


@dataclass(slots=True)
class CounterSinkHoleFeature(Feature):
    center_xy: tuple[float, float] = (0.0, 0.0)
    hole_radius: float = 0.0
    counter_sink_radius: float = 0.0
    counter_sink_angle_deg: float = 82.0
    start_from_top: bool = True
    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)


@dataclass(slots=True)
class BlindHoleFeature(Feature):
    """Counterbore / blind hole cut from the top face of the base extrusion (along ``z_dir``)."""

    center_xy: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    hole_depth: float = 0.0
    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)


@dataclass(slots=True)
class PocketFeature(Feature):
    """Planar pocket cut from the stock top face: 2D loop in base sketch coordinates."""

    profile_loop: list[tuple[float, float]] = field(default_factory=list)
    pocket_depth: float = 0.0


@dataclass(slots=True)
class SphericalBossFeature(Feature):
    center_xy: tuple[float, float] = (0.0, 0.0)
    center_offset: float = 0.0
    radius: float = 0.0


@dataclass(slots=True)
class SphericalCavityFeature(Feature):
    center_xy: tuple[float, float] = (0.0, 0.0)
    center_offset: float = 0.0
    radius: float = 0.0


@dataclass(slots=True)
class BossFeature(Feature):
    center_xy: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    height: float = 0.0
    start_offset: float = 0.0


@dataclass(slots=True)
class RevolveSolidFeature(Feature):
    """Solid of revolution: profile (radial, axial) in a pose-aware sketch plane; axis through ``axis_origin``."""

    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    radius: float = 0.0
    height: float = 0.0
    profile_rz: list[tuple[float, float]] = field(default_factory=list)
