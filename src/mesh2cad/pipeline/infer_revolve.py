from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from mesh2cad.domain.features import RevolveSolidFeature
from mesh2cad.domain.primitives import ConePrimitive, CylinderPrimitive, Primitive
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


def infer_tapered_revolve_solid(
    primitives: list[Primitive],
    tolerances: ToleranceConfig,
) -> RevolveInferenceResult:
    """Infer tapered revolve solid from cone-dominant rotational input."""
    cones = [p for p in primitives if isinstance(p, ConePrimitive)]
    cylinders = [p for p in primitives if isinstance(p, CylinderPrimitive)]
    
    if not cones and not cylinders:
        return RevolveInferenceResult(features=[], warnings=["No rotational primitives for tapered revolve path."])
    
    # Try to find cone-dominant configurations
    if cones:
        best_cone = max(cones, key=lambda c: c.confidence.score)
        if best_cone.confidence.score >= 0.3:
            return _create_tapered_revolve_from_cone(best_cone, tolerances)
    
    # Fall back to cylinder if no suitable cone
    if cylinders:
        best_cylinder = max(cylinders, key=lambda c: c.confidence.score)
        if best_cylinder.confidence.score >= 0.25:
            return _create_cylindrical_revolve(best_cylinder, tolerances)
    
    return RevolveInferenceResult(features=[], warnings=["No suitable primitives for tapered revolve path."])


def _create_tapered_revolve_from_cone(
    cone: ConePrimitive,
    tolerances: ToleranceConfig,
) -> RevolveInferenceResult:
    """Create tapered revolve feature from cone primitive."""
    axis = np.asarray(cone.axis_direction, dtype=np.float64)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-9:
        return RevolveInferenceResult(features=[], warnings=["Invalid cone axis for tapered revolve."])
    axis = axis / norm
    origin = np.asarray(cone.axis_origin, dtype=np.float64)
    
    # Extract cone parameters
    base_radius = float(cone.base_radius)
    top_radius = float(cone.top_radius)
    height = float(cone.height_estimate) if cone.height_estimate else 0.0
    
    if height <= tolerances.linear * 2.0:
        return RevolveInferenceResult(features=[], warnings=["Cone height insufficient for tapered revolve."])
    
    # Create tapered profile
    # Profile points are in (r, z) coordinates where z is along the axis
    profile = [
        (0.0, -height / 2.0),
        (base_radius, -height / 2.0),
        (top_radius, height / 2.0),
        (0.0, height / 2.0),
    ]
    
    # Determine if this is a true taper or just a cylinder
    taper_ratio = abs(base_radius - top_radius) / max(base_radius, top_radius)
    is_tapered = taper_ratio > 0.1  # 10% difference threshold
    
    parameters = {
        "base_radius": base_radius,
        "top_radius": top_radius,
        "height": height,
        "taper_ratio": taper_ratio,
        "is_tapered": is_tapered,
    }
    
    conf = Confidence(
        score=min(1.0, cone.confidence.score * 0.9),
        reasons=[
            "cone primitive for tapered revolve",
            f"base_radius {base_radius:.4f}",
            f"top_radius {top_radius:.4f}",
            f"height {height:.4f}",
            f"taper_ratio {taper_ratio:.3f}",
        ],
    )
    
    feature = RevolveSolidFeature(
        kind=FeatureKind.REVOLVE,
        confidence=conf,
        parameters=parameters,
        references={"source_primitive": "cone"},
        axis_origin=tuple(float(x) for x in origin.tolist()),
        axis_direction=tuple(float(x) for x in axis.tolist()),
        radius=base_radius,  # Use base radius as primary
        height=height,
        profile_rz=profile,
    )
    
    warnings = []
    if not is_tapered:
        warnings.append("Cone appears cylindrical; using cylindrical revolve interpretation.")
    
    return RevolveInferenceResult(features=[feature], warnings=warnings)


def _create_cylindrical_revolve(
    cylinder: CylinderPrimitive,
    tolerances: ToleranceConfig,
) -> RevolveInferenceResult:
    """Create cylindrical revolve feature as fallback for tapered revolve."""
    axis = np.asarray(cylinder.axis_direction, dtype=np.float64)
    norm = float(np.linalg.norm(axis))
    if norm < 1e-9:
        return RevolveInferenceResult(features=[], warnings=["Invalid cylinder axis for revolve."])
    axis = axis / norm
    origin = np.asarray(cylinder.axis_origin, dtype=np.float64)
    
    radius = float(cylinder.radius)
    height = float(cylinder.height_estimate) if cylinder.height_estimate else 0.0
    
    if height <= tolerances.linear * 2.0:
        return RevolveInferenceResult(features=[], warnings=["Cylinder height insufficient for revolve."])
    
    # Create cylindrical profile (same as simple revolve)
    profile = [
        (0.0, -height / 2.0),
        (radius, -height / 2.0),
        (radius, height / 2.0),
        (0.0, height / 2.0),
    ]
    
    parameters = {
        "radius": radius,
        "height": height,
        "taper_ratio": 0.0,
        "is_tapered": False,
    }
    
    conf = Confidence(
        score=min(1.0, cylinder.confidence.score * 0.85),
        reasons=[
            "cylinder primitive for revolve (tapered fallback)",
            f"radius {radius:.4f}",
            f"height {height:.4f}",
        ],
    )
    
    feature = RevolveSolidFeature(
        kind=FeatureKind.REVOLVE,
        confidence=conf,
        parameters=parameters,
        references={"source_primitive": "cylinder"},
        axis_origin=tuple(float(x) for x in origin.tolist()),
        axis_direction=tuple(float(x) for x in axis.tolist()),
        radius=radius,
        height=height,
        profile_rz=profile,
    )
    
    return RevolveInferenceResult(features=[feature], warnings=["Using cylindrical revolve as tapered fallback."])
