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
    THROUGH_HOLE = "through_hole"
    BLIND_HOLE = "blind_hole"
    BOSS = "boss"
    POCKET = "pocket"
    REVOLVE = "revolve"
    FILLET_CANDIDATE = "fillet_candidate"


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
