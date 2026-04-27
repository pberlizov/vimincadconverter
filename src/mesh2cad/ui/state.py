from __future__ import annotations

import os
from pathlib import Path


def get_max_upload_bytes() -> int:
    configured = os.environ.get("MESH2CAD_MAX_UPLOAD_MB")
    if configured:
        return int(configured) * 1024 * 1024
    return 200 * 1024 * 1024


def use_secure_cookies() -> bool:
    return os.environ.get("MESH2CAD_SECURE_COOKIES", "").lower() in {"1", "true", "yes", "on"}


def get_state_dir() -> Path:
    configured = os.environ.get("MESH2CAD_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home().joinpath(".mesh2cad").resolve()


def ensure_state_dirs() -> Path:
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    state_dir.joinpath("uploads").mkdir(exist_ok=True)
    state_dir.joinpath("jobs").mkdir(exist_ok=True)
    return state_dir


def get_database_path() -> Path:
    return ensure_state_dirs().joinpath("mesh2cad.sqlite3")
