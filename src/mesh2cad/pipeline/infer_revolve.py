from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from mesh2cad.domain.features import RevolveSolidFeature
from mesh2cad.domain.primitives import CylinderPrimitive, Primitive
from mesh2cad.domain.types import Confidence, FeatureKind, ToleranceConfig


@dataclass(slots=True)
class RevolveInferenceResult:
    features: list[RevolveSolidFeature]
    warnings: list[str]


def infer_simple_revolve_solid(
    primitives: list[Primitive],
    tolerances: ToleranceConfig,
) -> RevolveInferenceResult:
    """Pick the strongest cylinder and emit a simple revolve-solid feature (axis-aligned CAD)."""
    cylinders = [p for p in primitives if isinstance(p, CylinderPrimitive)]
    if not cylinders:
        return RevolveInferenceResult(features=[], warnings=["No cylinder primitives for revolve path."])

    best = max(cylinders, key=lambda c: c.confidence.score)
    if best.confidence.score < 0.25:
        return RevolveInferenceResult(
            features=[],
            warnings=["Cylinder confidence too low for revolve path."],
        )

    if best.height_estimate is None or best.height_estimate <= tolerances.linear * 2.0:
        return RevolveInferenceResult(features=[], warnings=["Cylinder height unavailable for revolve path."])

    axis = np.asarray(best.axis_direction, dtype=np.float64)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-9:
        return RevolveInferenceResult(features=[], warnings=["Invalid cylinder axis for revolve path."])
    axis = axis / norm
    origin = np.asarray(best.axis_origin, dtype=np.float64)

    r = float(best.radius)
    h = float(best.height_estimate)
    profile = [
        (0.0, -h / 2.0),
        (r, -h / 2.0),
        (r, h / 2.0),
        (0.0, h / 2.0),
    ]

    conf = Confidence(
        score=min(1.0, best.confidence.score * 0.95),
        reasons=[
            "dominant cylinder primitive",
            f"radius {r:.4f}",
            f"height {h:.4f}",
        ],
    )

    feature = RevolveSolidFeature(
        kind=FeatureKind.REVOLVE,
        confidence=conf,
        parameters={"radius": r, "height": h},
        references={"source_primitive": "cylinder"},
        axis_origin=tuple(float(x) for x in origin.tolist()),
        axis_direction=tuple(float(x) for x in axis.tolist()),
        radius=r,
        height=h,
        profile_rz=profile,
    )
    return RevolveInferenceResult(features=[feature], warnings=[])
