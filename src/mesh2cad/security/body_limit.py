"""Reject oversized requests using ``Content-Length`` (cheap, pre-body read)."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def max_request_bytes() -> int:
    raw_b = os.environ.get("MESH2CAD_MAX_REQUEST_BYTES")
    if raw_b is not None and str(raw_b).strip():
        return max(1024, int(raw_b))
    mb = float(os.environ.get("MESH2CAD_MAX_REQUEST_MB", "256"))
    return int(max(0.001, mb) * 1024 * 1024)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Return 413 when ``Content-Length`` exceeds ``MESH2CAD_MAX_REQUEST_MB``."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in {"POST", "PUT", "PATCH"}:
            return await call_next(request)
        cl = request.headers.get("content-length")
        if not cl:
            return await call_next(request)
        try:
            n = int(cl)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
        limit = max_request_bytes()
        if n > limit:
            return JSONResponse(
                {"detail": f"Request body exceeds limit of {limit} bytes."},
                status_code=413,
            )
        return await call_next(request)
