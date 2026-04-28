"""Optional Redis-backed fixed-window rate limits (shared across replicas)."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis import Redis

_redis: Redis | None = None


def _redis_url() -> str:
    return os.environ.get("MESH2CAD_REDIS_URL", "").strip()


def _key_prefix() -> str:
    return os.environ.get("MESH2CAD_RATE_LIMIT_REDIS_PREFIX", "mesh2cad:rl").strip() or "mesh2cad:rl"


def _client() -> Redis:
    global _redis
    if _redis is None:
        from redis import Redis

        url = _redis_url()
        if not url:
            raise RuntimeError("MESH2CAD_REDIS_URL is required for Redis rate limits.")
        _redis = Redis.from_url(url, decode_responses=True)
    return _redis


def reset_redis_rate_limit_client() -> None:
    """Drop cached Redis client (tests / reload)."""
    global _redis
    _redis = None


def redis_rate_limit_reset_pattern() -> None:
    """Delete rate-limit keys (best-effort; for tests)."""
    try:
        client = _client()
    except Exception:
        reset_redis_rate_limit_client()
        return
    prefix = _key_prefix() + ":"
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=f"{prefix}*", count=500)
        if keys:
            client.delete(*keys)
        if cursor == 0:
            break
    reset_redis_rate_limit_client()


def redis_rate_limit_allow(key: str, *, limit: int, window_sec: float) -> bool:
    """Return True if request is allowed; False if rate limited.

    Uses a fixed window per ``key`` starting at the first hit in the window (``EXPIRE`` on first ``INCR``).
    """
    if limit < 1:
        return True
    # Wall-clock bucket so all API replicas share the same Redis window.
    bucket = int(time.time()) // int(max(window_sec, 1.0))
    rkey = f"{_key_prefix()}:{key}:{bucket}"
    client = _client()
    n = int(client.incr(rkey))
    if n == 1:
        client.expire(rkey, int(max(1, window_sec)))
    return n <= limit
