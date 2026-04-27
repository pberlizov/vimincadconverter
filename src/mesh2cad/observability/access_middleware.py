"""HTTP access logging with ``request_id`` and latency (for log aggregation)."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mesh2cad.observability.metrics import record_http_request

log = logging.getLogger("mesh2cad.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        rid = getattr(request.state, "request_id", None)
        try:
            response = await call_next(request)
        except Exception:
            dt = (time.perf_counter() - t0) * 1000.0
            log.error(
                "request_error",
                exc_info=True,
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(dt, 2),
                    "client": request.client.host if request.client else None,
                },
            )
            raise
        dt = (time.perf_counter() - t0) * 1000.0
        code = response.status_code
        record_http_request(method=request.method, status_code=code, duration_sec=dt / 1000.0)
        log.info(
            "request",
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status_code": code,
                "duration_ms": round(dt, 2),
                "client": request.client.host if request.client else None,
            },
        )
        return response
