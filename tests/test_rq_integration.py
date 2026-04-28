"""Redis/RQ job path (requires Redis; skipped in default dev installs)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import trimesh

from mesh2cad.jobs.rq_support import reset_redis_connection_for_tests
from mesh2cad.jobs.runner import submit_job
from mesh2cad.ui.db import create_job_with_id, create_user, get_job, initialize_database


def _redis_url() -> str:
    return os.environ.get("MESH2CAD_TEST_REDIS_URL", "redis://127.0.0.1:6379/15").strip()


def _redis_ping() -> bool:
    try:
        from redis import Redis

        Redis.from_url(_redis_url(), decode_responses=False).ping()
        return True
    except Exception:
        return False


@pytest.fixture()
def rq_env(tmp_path, monkeypatch):
    if not _redis_ping():
        pytest.skip("Redis not reachable (set MESH2CAD_TEST_REDIS_URL or start redis)")

    from redis import Redis

    reset_redis_connection_for_tests()
    Redis.from_url(_redis_url(), decode_responses=False).flushdb()

    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(state))
    monkeypatch.setenv("MESH2CAD_REDIS_URL", _redis_url())
    monkeypatch.setenv("MESH2CAD_JOB_BACKEND", "rq")
    monkeypatch.setenv("MESH2CAD_RQ_QUEUE", "mesh2cad_test")

    initialize_database()
    user = create_user("rqtest", "not-used-hash", is_admin=True)
    uid = int(user["id"])
    mesh = tmp_path / "box.stl"
    trimesh.creation.box(extents=(4.0, 3.0, 1.0)).export(mesh)

    job_id = "rqtestjob01"
    upload_dir = state / "uploads" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_dir = state / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    create_job_with_id(
        job_id=job_id,
        user_id=uid,
        original_name="box.stl",
        input_path=mesh.resolve(),
        output_dir=job_dir.resolve(),
        request_payload={"sample_count": 800, "build": False},
    )

    yield job_id, mesh.resolve(), job_dir.resolve()

    reset_redis_connection_for_tests()


def test_rq_submit_and_worker_completes_job(rq_env):
    job_id, input_path, job_dir = rq_env

    submit_job(
        job_id=job_id,
        input_path=input_path,
        output_dir=None,
        artifact_dir=job_dir,
        sample_count=800,
        simplify_target_faces=None,
        build=False,
        auto_tune_sampling=False,
    )

    env = os.environ.copy()
    env["MESH2CAD_STATE_DIR"] = os.environ["MESH2CAD_STATE_DIR"]
    env["MESH2CAD_REDIS_URL"] = os.environ["MESH2CAD_REDIS_URL"]
    env["MESH2CAD_RQ_QUEUE"] = os.environ["MESH2CAD_RQ_QUEUE"]

    proc = subprocess.Popen(
        [sys.executable, "-m", "mesh2cad.jobs.rq_worker"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            job = get_job(job_id)
            assert job is not None
            if job["status"] == "completed":
                break
            if job["status"] == "failed":
                pytest.fail(job.get("error_text") or job.get("warnings"))
            time.sleep(0.15)
        else:
            pytest.fail("RQ job did not complete in time")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    job = get_job(job_id)
    assert job["status"] == "completed"


def test_ready_pings_redis_when_rq_backend(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    if not _redis_ping():
        pytest.skip("Redis not reachable")

    from fastapi.testclient import TestClient

    from mesh2cad.api.app import create_app

    reset_redis_connection_for_tests()
    state = tmp_path / "state_ready"
    state.mkdir()
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(state))
    monkeypatch.setenv("MESH2CAD_REDIS_URL", _redis_url())
    monkeypatch.setenv("MESH2CAD_JOB_BACKEND", "rq")
    initialize_database()

    client = TestClient(create_app())
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json().get("ready") is True


def test_use_rq_backend_false_without_env(monkeypatch):
    monkeypatch.delenv("MESH2CAD_JOB_BACKEND", raising=False)
    monkeypatch.delenv("MESH2CAD_REDIS_URL", raising=False)
    reset_redis_connection_for_tests()
    from mesh2cad.jobs.rq_support import use_rq_backend

    assert use_rq_backend() is False
