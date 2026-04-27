"""API key verification for machine clients (optional via ``MESH2CAD_API_KEYS``)."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def configured_api_keys() -> set[str]:
    raw = os.environ.get("MESH2CAD_API_KEYS", "").strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    """Reject unauthenticated calls when ``MESH2CAD_API_KEYS`` is non-empty."""
    keys = configured_api_keys()
    if not keys:
        return
    token = (x_api_key or "").strip()
    if not token and authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if not token or token not in keys:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
