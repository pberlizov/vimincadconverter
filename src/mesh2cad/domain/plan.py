from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from mesh2cad.domain.features import BaseExtrudeFeature, Feature, RevolveSolidFeature
from mesh2cad.domain.types import PartClass, ToleranceConfig

ReconstructionRoute = Literal["prismatic_extrude", "revolve_simple", "none"]


@dataclass
class PlanStage:
    name: str
    ok: bool
    message: str


@dataclass(slots=True)
class ReconstructionPlan:
    """Serializable intermediate: what we detected and which synthesis route to use."""

    route: ReconstructionRoute
    part_class: PartClass
    stages: list[PlanStage] = field(default_factory=list)
    feature_kinds: list[str] = field(default_factory=list)
    primitive_counts: dict[str, int] = field(default_factory=dict)
    tolerances: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "part_class": self.part_class.value,
            "stages": [asdict(s) for s in self.stages],
            "feature_kinds": list(self.feature_kinds),
            "primitive_counts": dict(self.primitive_counts),
            "tolerances": dict(self.tolerances),
            "notes": list(self.notes),
        }


def tolerances_to_dict(t: ToleranceConfig) -> dict[str, Any]:
    return {
        "linear": t.linear,
        "angular_deg": t.angular_deg,
        "min_region_area": t.min_region_area,
        "ransac_distance": t.ransac_distance,
    }


def build_reconstruction_plan(
    *,
    part_class: PartClass,
    features: list[Feature],
    primitive_kinds: list[str],
    tolerances: ToleranceConfig,
    stages: list[PlanStage],
) -> ReconstructionPlan:
    counts: dict[str, int] = {}
    for k in primitive_kinds:
        counts[k] = counts.get(k, 0) + 1

    kinds = [f.kind.value for f in features]
    if any(isinstance(f, BaseExtrudeFeature) for f in features):
        route: ReconstructionRoute = "prismatic_extrude"
    elif any(isinstance(f, RevolveSolidFeature) for f in features):
        route = "revolve_simple"
    else:
        route = "none"

    notes: list[str] = []
    if route == "revolve_simple":
        notes.append(
            "Revolve uses inferred axis (Axis(ORIGIN, AXIS_DIR)) and a sketch plane spanned by radial and axial directions."
        )

    return ReconstructionPlan(
        route=route,
        part_class=part_class,
        stages=stages,
        feature_kinds=kinds,
        primitive_counts=counts,
        tolerances=tolerances_to_dict(tolerances),
        notes=notes,
    )

