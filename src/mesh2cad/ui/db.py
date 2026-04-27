from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from mesh2cad.ui.state import ensure_state_dirs, get_database_path


SESSION_LIFETIME_HOURS = 24


def initialize_database() -> None:
    ensure_state_dirs()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                input_path TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                status TEXT NOT NULL,
                source_path TEXT,
                step_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                request_json TEXT NOT NULL DEFAULT '{}',
                retry_count INTEGER NOT NULL DEFAULT 0,
                warnings_json TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL DEFAULT '{}',
                error_text TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS api_idempotency (
                key TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "jobs", "request_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "jobs", "retry_count", "INTEGER NOT NULL DEFAULT 0")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_database_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def user_count() -> int:
    initialize_database()
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    return int(row["count"])


def create_user(username: str, password_hash: str, *, is_admin: bool) -> dict[str, Any]:
    now = _now()
    initialize_database()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, is_admin, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, password_hash, 1 if is_admin else 0, now),
        )
        user_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    initialize_database()
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    initialize_database()
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_session(token: str, user_id: int) -> None:
    now = datetime.now(UTC)
    expires = now + timedelta(hours=SESSION_LIFETIME_HOURS)
    initialize_database()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (token, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, user_id, now.isoformat(), expires.isoformat()),
        )


def get_user_for_session(token: str) -> dict[str, Any] | None:
    initialize_database()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, _now()),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token: str) -> None:
    initialize_database()
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def create_job(
    user_id: int,
    original_name: str,
    input_path: Path,
    output_dir: Path,
    *,
    request_payload: dict[str, Any] | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    now = _now()
    initialize_database()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, user_id, original_name, input_path, output_dir, status,
                created_at, updated_at, request_json, retry_count, warnings_json, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                user_id,
                original_name,
                str(input_path),
                str(output_dir),
                "queued",
                now,
                now,
                json.dumps(request_payload or {}),
                0,
                "[]",
                "{}",
            ),
        )
    return job_id


def create_job_with_id(
    *,
    job_id: str,
    user_id: int,
    original_name: str,
    input_path: Path,
    output_dir: Path,
    status: str = "queued",
    request_payload: dict[str, Any] | None = None,
) -> None:
    now = _now()
    initialize_database()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, user_id, original_name, input_path, output_dir, status,
                created_at, updated_at, request_json, retry_count, warnings_json, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                user_id,
                original_name,
                str(input_path),
                str(output_dir),
                status,
                now,
                now,
                json.dumps(request_payload or {}),
                0,
                "[]",
                "{}",
            ),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    initialize_database()
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _decode_job(dict(row)) if row else None


def update_job(
    job_id: str,
    *,
    status: str,
    source_path: str | None = None,
    step_path: str | None = None,
    warnings: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    error_text: str | None = None,
    request_payload: dict[str, Any] | None = None,
) -> None:
    initialize_database()
    existing = get_job(job_id)
    existing_request = (existing or {}).get("request", {})
    with connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, source_path = ?, step_path = ?, updated_at = ?,
                warnings_json = ?, payload_json = ?, error_text = ?, request_json = ?
            WHERE id = ?
            """,
            (
                status,
                source_path,
                step_path,
                _now(),
                json.dumps(warnings or []),
                json.dumps(payload or {}),
                error_text,
                json.dumps(request_payload if request_payload is not None else existing_request),
                job_id,
            ),
        )


def set_job_request(job_id: str, request_payload: dict[str, Any]) -> None:
    initialize_database()
    with connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET request_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(request_payload), _now(), job_id),
        )


def reset_job_for_retry(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    if job is None:
        return None
    initialize_database()
    with connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, source_path = ?, step_path = ?, updated_at = ?,
                warnings_json = ?, payload_json = ?, error_text = ?, retry_count = retry_count + 1
            WHERE id = ?
            """,
            (
                "queued",
                str(job.get("input_path")),
                None,
                _now(),
                "[]",
                "{}",
                None,
                job_id,
            ),
        )
    return get_job(job_id)


def list_jobs_for_user(user_id: int) -> list[dict[str, Any]]:
    initialize_database()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM jobs
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_decode_job(dict(row)) for row in rows]


def get_job_for_user(job_id: str, user_id: int) -> dict[str, Any] | None:
    initialize_database()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        ).fetchone()
    return _decode_job(dict(row)) if row else None


def job_storage_paths(job_id: str) -> tuple[Path, Path]:
    """Upload and job directories for ``job_id`` (paths may not exist yet)."""
    state_dir = ensure_state_dirs()
    return state_dir.joinpath("uploads", job_id), state_dir.joinpath("jobs", job_id)


def get_job_paths(job_id: str) -> tuple[Path, Path]:
    upload_dir, job_dir = job_storage_paths(job_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir, job_dir


def purge_terminal_jobs_older_than(*, days: int) -> int:
    """Remove completed/failed/cancelled jobs whose ``updated_at`` is older than ``days``.

    Deletes SQLite rows, idempotency keys, and on-disk upload/job directories.
    """
    import shutil

    if days < 1:
        return 0
    mod = f"-{int(days)} days"
    initialize_database()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id FROM jobs
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND datetime(updated_at) < datetime('now', ?)
            """,
            (mod,),
        ).fetchall()
        job_ids = [str(r["id"]) for r in rows]
        for jid in job_ids:
            conn.execute("DELETE FROM api_idempotency WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (jid,))
    for jid in job_ids:
        upload_dir, job_dir = job_storage_paths(jid)
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
    return len(job_ids)


def _decode_job(job: dict[str, Any]) -> dict[str, Any]:
    job["request"] = json.loads(job.pop("request_json", "{}"))
    job["warnings"] = json.loads(job.pop("warnings_json", "[]"))
    job["payload"] = json.loads(job.pop("payload_json", "{}"))
    return job


def _now() -> str:
    return datetime.now(UTC).isoformat()


def idempotency_lookup(key: str | None) -> str | None:
    """Return existing ``job_id`` for a submit idempotency key, if any."""
    if key is None:
        return None
    k = key.strip()
    if not k or len(k) > 256:
        return None
    initialize_database()
    with connect() as conn:
        row = conn.execute("SELECT job_id FROM api_idempotency WHERE key = ?", (k,)).fetchone()
    return str(row["job_id"]) if row else None


def idempotency_register(key: str, job_id: str) -> None:
    """Bind ``key`` to ``job_id`` (call after job row exists)."""
    k = key.strip()[:256]
    if not k:
        return
    now = _now()
    initialize_database()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO api_idempotency (key, job_id, created_at) VALUES (?, ?, ?)",
            (k, job_id, now),
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if any(str(row["name"]) == column for row in rows):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
