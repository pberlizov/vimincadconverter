"""In-process counters (Prometheus text when ``/metrics`` is enabled)."""

from __future__ import annotations

import threading
import time
from typing import Any


_lock = threading.Lock()
_http_requests: dict[tuple[str, int], int] = {}
_http_request_seconds: list[float] = []  # bounded ring for p95-ish
_MAX_LAT_SAMPLES = 500


def record_http_request(*, method: str, status_code: int, duration_sec: float) -> None:
    key = (method.upper(), int(status_code))
    with _lock:
        _http_requests[key] = _http_requests.get(key, 0) + 1
        _http_request_seconds.append(duration_sec)
        if len(_http_request_seconds) > _MAX_LAT_SAMPLES:
            del _http_request_seconds[: len(_http_request_seconds) - _MAX_LAT_SAMPLES]


def reset_metrics() -> None:
    with _lock:
        _http_requests.clear()
        _http_request_seconds.clear()


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "http_requests": dict(_http_requests),
            "http_latency_samples": list(_http_request_seconds),
            "ts": time.time(),
        }


def prometheus_text() -> str:
    lines: list[str] = []
    with _lock:
        lines.append("# HELP mesh2cad_http_requests_total HTTP requests handled by this process.")
        lines.append("# TYPE mesh2cad_http_requests_total counter")
        for (method, code), n in sorted(_http_requests.items()):
            lines.append(
                f'mesh2cad_http_requests_total{{method="{method}",status="{code}"}} {n}'
            )
        if _http_request_seconds:
            s = sorted(_http_request_seconds)
            p95 = s[int(0.95 * (len(s) - 1))]
            lines.append("# HELP mesh2cad_http_request_duration_seconds_p95 Recent sample p95 latency.")
            lines.append("# TYPE mesh2cad_http_request_duration_seconds_p95 gauge")
            lines.append(f"mesh2cad_http_request_duration_seconds_p95 {p95:.6f}")
    return "\n".join(lines) + "\n"
