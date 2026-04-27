from __future__ import annotations

from dataclasses import dataclass, field

from mesh2cad.domain.types import PartClass


@dataclass(slots=True)
class DetectionReport:
    part_class: PartClass
    warnings: list[str] = field(default_factory=list)
    detected_primitives: int = 0
    inferred_features: int = 0
    reconstruction_confidence: float = 0.0


@dataclass(slots=True)
class ValidationReport:
    solid_valid: bool
    rms_error: float | None = None
    max_error: float | None = None
    volume_delta_ratio: float | None = None
    warnings: list[str] = field(default_factory=list)
