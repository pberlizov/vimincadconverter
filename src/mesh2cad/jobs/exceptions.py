from __future__ import annotations


CANCEL_FILENAME = ".cancel_requested"


class JobCancelledError(Exception):
    """Raised when a cancel marker is observed while the worker subprocess runs."""


class JobTimeoutError(Exception):
    """Raised when the worker exceeds MESH2CAD_JOB_TIMEOUT_SEC."""
