"""Job retention purge (DB + filesystem)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mesh2cad.ui import db as dbm
from mesh2cad.ui.db import connect, create_job_with_id, get_job, purge_terminal_jobs_older_than


def test_purge_removes_old_completed_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(tmp_path))
    dbm.initialize_database()
    inp = tmp_path / "in.stl"
    inp.write_bytes(b"x")
    job_id = "purge_test_job"
    create_job_with_id(
        job_id=job_id,
        user_id=0,
        original_name="in.stl",
        input_path=inp,
        output_dir=tmp_path / "jobdir",
        status="completed",
        request_payload={"build": False},
    )
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    with connect() as conn:
        conn.execute("UPDATE jobs SET updated_at = ? WHERE id = ?", (old, job_id))
    n = purge_terminal_jobs_older_than(days=30)
    assert n == 1
    assert get_job(job_id) is None
