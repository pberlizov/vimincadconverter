"""Configure stdlib logging (optional JSON lines for machine ingestion)."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "client"):
            v = getattr(record, key, None)
            if v is not None:
                payload[key] = v
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Idempotent root configuration (call from ``create_app`` / workers)."""
    root = logging.getLogger()
    if getattr(root, "_mesh2cad_logging_configured", False):
        return
    level_name = os.environ.get("MESH2CAD_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("MESH2CAD_LOG_JSON", "").lower() in {"1", "true", "yes", "on"}:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    root.handlers.clear()
    root.addHandler(handler)
    setattr(root, "_mesh2cad_logging_configured", True)
