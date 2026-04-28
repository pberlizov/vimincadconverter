"""Fixed-window rate limits: in-memory (default) or optional Redis (multi-replica)."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mesh2cad.exceptions import RateLimitError

# Simple deque window used by RateLimitMiddleware when Redis backend is not active.
_MW_LOCK = Lock()
_MW_WINDOWS: defaultdict[str, deque[float]] = defaultdict(deque)


@dataclass(slots=True)
class RateLimitWindow:
    """Represents a rate limit window for a specific client."""
    requests: deque[float] = field(default_factory=deque)
    last_reset: float = field(default_factory=time.time)
    total_requests: int = 0
    blocked_until: float | None = None


@dataclass(slots=True)
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_minute: int = 120
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_limit: int = 10  # Max requests in 10 seconds
    cleanup_interval: int = 300  # Clean up old entries every 5 minutes
    max_clients: int = 10000  # Maximum number of tracked clients


class InMemoryRateLimiter:
    """Improved in-memory rate limiter with better performance and monitoring."""
    
    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._lock = Lock()
        self._windows: dict[str, RateLimitWindow] = defaultdict(RateLimitWindow)
        self._last_cleanup = time.time()
        self._stats = {
            "total_requests": 0,
            "blocked_requests": 0,
            "active_clients": 0,
            "last_cleanup": 0,
        }
    
    def is_allowed(
        self, 
        client_id: str, 
        request_time: float | None = None
    ) -> tuple[bool, dict[str, Any]]:
        """Check if a request is allowed and return detailed status."""
        if request_time is None:
            request_time = time.time()
        
        with self._lock:
            self._cleanup_if_needed(request_time)
            
            window = self._windows[client_id]
            
            # Check if client is temporarily blocked
            if window.blocked_until and request_time < window.blocked_until:
                self._stats["blocked_requests"] += 1
                return False, self._create_block_response(window, request_time)
            
            # Remove old requests outside the current minute window
            minute_ago = request_time - 60
            while window.requests and window.requests[0] < minute_ago:
                window.requests.popleft()
            
            # Check rate limits
            current_requests = len(window.requests)
            
            # Burst limit (very short term)
            if current_requests >= self.config.burst_limit:
                window.blocked_until = request_time + 30  # Block for 30 seconds
                self._stats["blocked_requests"] += 1
                return False, self._create_block_response(window, request_time)
            
            # Minute limit
            if current_requests >= self.config.requests_per_minute:
                window.blocked_until = request_time + 60  # Block until next minute
                self._stats["blocked_requests"] += 1
                return False, self._create_block_response(window, request_time)
            
            # Hour limit (check total requests in last hour)
            hour_ago = request_time - 3600
            hour_requests = sum(
                1 for req_time in window.requests 
                if req_time > hour_ago
            )
            if hour_requests >= self.config.requests_per_hour:
                window.blocked_until = request_time + 300  # Block for 5 minutes
                self._stats["blocked_requests"] += 1
                return False, self._create_block_response(window, request_time)
            
            # Day limit (check total requests in last day)
            day_ago = request_time - 86400
            day_requests = sum(
                1 for req_time in window.requests 
                if req_time > day_ago
            )
            if day_requests >= self.config.requests_per_day:
                window.blocked_until = request_time + 3600  # Block for 1 hour
                self._stats["blocked_requests"] += 1
                return False, self._create_block_response(window, request_time)
            
            # Request is allowed
            window.requests.append(request_time)
            window.total_requests += 1
            self._stats["total_requests"] += 1
            
            return True, self._create_allow_response(window, request_time)
    
    def _cleanup_if_needed(self, current_time: float) -> None:
        """Clean up old entries if cleanup interval has passed."""
        if current_time - self._last_cleanup < self.config.cleanup_interval:
            return
        
        # Remove very old entries (older than 1 day)
        day_ago = current_time - 86400
        clients_to_remove = []
        
        for client_id, window in self._windows.items():
            # Remove old requests
            window.requests = deque(
                req_time for req_time in window.requests 
                if req_time > day_ago
            )
            
            # Remove client if no recent activity and not blocked
            if (not window.requests and 
                not window.blocked_until and 
                window.blocked_until is None):
                clients_to_remove.append(client_id)
        
        for client_id in clients_to_remove:
            del self._windows[client_id]
        
        # Enforce maximum client limit
        if len(self._windows) > self.config.max_clients:
            # Remove oldest clients
            sorted_clients = sorted(
                self._windows.items(),
                key=lambda x: x[1].last_reset
            )
            excess = len(self._windows) - self.config.max_clients
            for client_id, _ in sorted_clients[:excess]:
                del self._windows[client_id]
        
        self._last_cleanup = current_time
        self._stats["last_cleanup"] = current_time
        self._stats["active_clients"] = len(self._windows)
    
    def _create_allow_response(self, window: RateLimitWindow, current_time: float) -> dict[str, Any]:
        """Create response for allowed requests."""
        return {
            "allowed": True,
            "requests_this_minute": len(window.requests),
            "total_requests": window.total_requests,
            "reset_time": window.last_reset + 60,
            "limits": {
                "per_minute": self.config.requests_per_minute,
                "per_hour": self.config.requests_per_hour,
                "per_day": self.config.requests_per_day,
                "burst": self.config.burst_limit,
            }
        }
    
    def _create_block_response(self, window: RateLimitWindow, current_time: float) -> dict[str, Any]:
        """Create response for blocked requests."""
        return {
            "allowed": False,
            "blocked_until": window.blocked_until,
            "retry_after": int(window.blocked_until - current_time) if window.blocked_until else None,
            "requests_this_minute": len(window.requests),
            "total_requests": window.total_requests,
            "block_reason": self._get_block_reason(window, current_time),
            "limits": {
                "per_minute": self.config.requests_per_minute,
                "per_hour": self.config.requests_per_hour,
                "per_day": self.config.requests_per_day,
                "burst": self.config.burst_limit,
            }
        }
    
    def _get_block_reason(self, window: RateLimitWindow, current_time: float) -> str:
        """Determine the reason for blocking."""
        if len(window.requests) >= self.config.burst_limit:
            return "Burst limit exceeded"
        
        minute_ago = current_time - 60
        minute_requests = sum(
            1 for req_time in window.requests 
            if req_time > minute_ago
        )
        if minute_requests >= self.config.requests_per_minute:
            return "Minute rate limit exceeded"
        
        hour_ago = current_time - 3600
        hour_requests = sum(
            1 for req_time in window.requests 
            if req_time > hour_ago
        )
        if hour_requests >= self.config.requests_per_hour:
            return "Hour rate limit exceeded"
        
        return "Day rate limit exceeded"
    
    def get_stats(self) -> dict[str, Any]:
        """Get rate limiting statistics."""
        with self._lock:
            return {
                **self._stats,
                "active_clients": len(self._windows),
                "config": {
                    "requests_per_minute": self.config.requests_per_minute,
                    "requests_per_hour": self.config.requests_per_hour,
                    "requests_per_day": self.config.requests_per_day,
                    "burst_limit": self.config.burst_limit,
                }
            }
    
    def reset_client(self, client_id: str) -> None:
        """Reset rate limiting for a specific client."""
        with self._lock:
            if client_id in self._windows:
                del self._windows[client_id]
    
    def reset_all(self) -> None:
        """Reset all rate limiting state."""
        with self._lock:
            self._windows.clear()
            self._stats = {
                "total_requests": 0,
                "blocked_requests": 0,
                "active_clients": 0,
                "last_cleanup": time.time(),
            }


# Global rate limiter instance
_rate_limiter: InMemoryRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        config = RateLimitConfig(
            requests_per_minute=int(os.environ.get("MESH2CAD_RATE_LIMIT_PER_MINUTE", "120")),
            requests_per_hour=int(os.environ.get("MESH2CAD_RATE_LIMIT_PER_HOUR", "1000")),
            requests_per_day=int(os.environ.get("MESH2CAD_RATE_LIMIT_PER_DAY", "10000")),
            burst_limit=int(os.environ.get("MESH2CAD_RATE_LIMIT_BURST", "10")),
        )
        _rate_limiter = InMemoryRateLimiter(config)
    return _rate_limiter


def _use_redis_rate_limit() -> bool:
    raw = os.environ.get("MESH2CAD_RATE_LIMIT_BACKEND", "").strip().lower()
    if raw not in {"redis", "1", "true", "yes", "on"}:
        return False
    return bool(os.environ.get("MESH2CAD_REDIS_URL", "").strip())


def reset_rate_limit_state() -> None:
    """Clear counters (for tests and hot-reload)."""
    limiter = get_rate_limiter()
    limiter.reset_all()
    with _MW_LOCK:
        _MW_WINDOWS.clear()
    
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
        with _MW_LOCK:
            dq = _MW_WINDOWS[key]
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
