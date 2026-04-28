from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PartClass(str, Enum):
    PRISMATIC = "prismatic"
    ROTATIONAL = "rotational"
    MIXED = "mixed"
    FREEFORM = "freeform"
    UNKNOWN = "unknown"


class PrimitiveKind(str, Enum):
    PLANE = "plane"
    CYLINDER = "cylinder"
    CONE = "cone"
    SPHERE = "sphere"
    LINE = "line"
    CIRCLE = "circle"


class FeatureKind(str, Enum):
    BASE_EXTRUDE = "base_extrude"
    HOLE_STACK = "hole_stack"
    THROUGH_HOLE = "through_hole"
    COUNTERSINK_HOLE = "countersink_hole"
    BLIND_HOLE = "blind_hole"
    SPHERICAL_BOSS = "spherical_boss"
    SPHERICAL_CAVITY = "spherical_cavity"
    BOSS = "boss"
    POCKET = "pocket"
    REVOLVE = "revolve"
    FILLET_CANDIDATE = "fillet_candidate"


class HoleSectionKind(str, Enum):
    CYLINDER = "cylinder"
    CONE = "cone"


class HoleTermination(str, Enum):
    THROUGH = "through"
    BLIND = "blind"


@dataclass(slots=True)
class Confidence:
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ToleranceConfig:
    linear: float = 0.25
    angular_deg: float = 2.0
    min_region_area: float = 5.0
    ransac_distance: float = 0.2
