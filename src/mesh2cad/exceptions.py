"""Custom exceptions for ViminCADConverter."""

from __future__ import annotations

from typing import Any


class Mesh2CADError(Exception):
    """Base exception for all mesh2cad errors."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class GeometryError(Mesh2CADError):
    """Raised when geometry processing fails."""
    pass


class MeshLoadError(GeometryError):
    """Raised when mesh loading fails."""
    pass


class MeshRepairError(GeometryError):
    """Raised when mesh repair fails."""
    pass


class SamplingError(GeometryError):
    """Raised when point sampling fails."""
    pass


class PrimitiveFittingError(GeometryError):
    """Raised when primitive fitting fails."""
    pass


class FeatureInferenceError(GeometryError):
    """Raised when feature inference fails."""
    pass


class CADGenerationError(Mesh2CADError):
    """Raised when CAD generation fails."""
    pass


class Build123dError(CADGenerationError):
    """Raised when build123d execution fails."""
    pass


class ValidationError(Mesh2CADError):
    """Raised when validation fails."""
    pass


class ConfigurationError(Mesh2CADError):
    """Raised when configuration is invalid."""
    pass


class FileUploadError(Mesh2CADError):
    """Raised when file upload validation fails."""
    pass


class JobProcessingError(Mesh2CADError):
    """Raised when job processing fails."""
    pass


class AuthenticationError(Mesh2CADError):
    """Raised when authentication fails."""
    pass


class RateLimitError(Mesh2CADError):
    """Raised when rate limit is exceeded."""
    pass


class InsufficientResourcesError(Mesh2CADError):
    """Raised when system resources are insufficient."""
    pass
