"""Fixed-window rate limits: in-memory (default) or optional Redis (multi-replica)."""

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


def _use_redis_rate_limit() -> bool:
    raw = os.environ.get("MESH2CAD_RATE_LIMIT_BACKEND", "").strip().lower()
    if raw not in {"redis", "1", "true", "yes", "on"}:
        return False
    return bool(os.environ.get("MESH2CAD_REDIS_URL", "").strip())


def reset_rate_limit_state() -> None:
    """Clear counters (for tests and hot-reload)."""
    with _lock:
        _windows.clear()
    if _use_redis_rate_limit():
        try:
            from mesh2cad.security.rate_limit_redis import (
                redis_rate_limit_reset_pattern,
                reset_redis_rate_limit_client,
            )

            redis_rate_limit_reset_pattern()
        except Exception:
            reset_redis_rate_limit_client()


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
        window = _window_seconds()
        limit = _limit_per_minute()
        if _use_redis_rate_limit():
            try:
                from mesh2cad.security.rate_limit_redis import redis_rate_limit_allow

                if not redis_rate_limit_allow(key, limit=limit, window_sec=window):
                    return JSONResponse(
                        {"detail": "Rate limit exceeded. Try again later."},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
                return await call_next(request)
            except Exception:
                pass

        now = time.monotonic()
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
