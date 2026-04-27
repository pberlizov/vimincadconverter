"""Fixed-window in-memory rate limits (per client IP; best for a single replica)."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_lock = Lock()
_windows: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limit_state() -> None:
    """Clear counters (for tests and hot-reload)."""
    with _lock:
        _windows.clear()


def _limit_per_minute() -> int:
    try:
        return max(1, int(os.environ.get("MESH2CAD_RATE_LIMIT_PER_MINUTE", "120")))
    except ValueError:
        return 120


def _window_seconds() -> float:
    return 60.0


def _client_key(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _should_limit(path: str, method: str) -> bool:
    if method != "POST":
        return False
    return path.startswith("/v1/process") or path == "/v1/jobs" or path.startswith("/process")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429 when a client exceeds ``MESH2CAD_RATE_LIMIT_PER_MINUTE`` POSTs per minute on hot paths."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not _should_limit(request.url.path, request.method):
            return await call_next(request)
        key = f"{_client_key(request)}:{request.url.path}"
        now = time.monotonic()
        window = _window_seconds()
        limit = _limit_per_minute()
        with _lock:
            dq = _windows[key]
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= limit:
                return JSONResponse(
                    {"detail": "Rate limit exceeded. Try again later."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            dq.append(now)
        return await call_next(request)
