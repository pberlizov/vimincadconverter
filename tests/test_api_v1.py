"""HTTP API v1: health, auth gate, sync JSON process, idempotency header."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from mesh2cad.api.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("MESH2CAD_API_KEYS", raising=False)
    return TestClient(create_app())


def test_health_unauthenticated(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "x-request-id" in {k.lower() for k in r.headers.keys()}


def test_ready(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code in (200, 503)
    data = r.json()
    assert "ready" in data


def test_v1_requires_api_key_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("MESH2CAD_API_KEYS", "secret-one,secret-two")
    app_client = TestClient(create_app())
    r = app_client.post("/v1/process", json={"input_path": "/no/such", "build": False})
    assert r.status_code == 401
    r2 = app_client.post(
        "/v1/process",
        json={"input_path": "/no/such", "build": False},
        headers={"X-API-Key": "secret-one"},
    )
    assert r2.status_code == 400


def test_v1_process_json_no_build(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MESH2CAD_API_KEYS", raising=False)
    import trimesh

    box = trimesh.creation.box(extents=(1.0, 1.2, 0.8))
    mesh_path = tmp_path / "part.stl"
    box.export(mesh_path)
    app_client = TestClient(create_app())
    r = app_client.post(
        "/v1/process",
        json={
            "input_path": str(mesh_path),
            "build": False,
            "sample_count": 800,
            "include_script": False,
            "tolerances": {"linear": 0.3, "angular_deg": 2.5, "min_region_area": 5.0, "ransac_distance": 0.2},
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload.get("build") is None or payload.get("build", {}).get("script") is None
    assert "reconstruction_plan" in payload
    assert "session_id" not in payload
    assert "artifacts" not in payload


def test_v1_process_multipart_session_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MESH2CAD_API_KEYS", raising=False)
    monkeypatch.setenv("MESH2CAD_STATE_DIR", str(tmp_path))
    import trimesh

    box = trimesh.creation.box(extents=(1.0, 1.2, 0.8))
    stl_path = tmp_path / "upload.stl"
    box.export(stl_path)
    stl_bytes = stl_path.read_bytes()
    app_client = TestClient(create_app())
    r = app_client.post(
        "/v1/process",
        files={"file": ("part.stl", stl_bytes, "application/octet-stream")},
        data={"build": "false", "sample_count": "800", "include_script": "true"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    sid = payload.get("session_id")
    assert isinstance(sid, str) and len(sid) == 32
    arts = payload.get("artifacts")
    assert isinstance(arts, dict) and arts.get("report", "").endswith("/report")
    rep = app_client.get(f"/v1/process/artifacts/{sid}/report")
    assert rep.status_code == 200
    assert rep.headers.get("content-type", "").startswith("application/json")
    bad = app_client.get("/v1/process/artifacts/not-a-uuid/report")
    assert bad.status_code == 400


def test_v1_jobs_idempotency_header(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MESH2CAD_API_KEYS", raising=False)
    import trimesh

    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh_path = tmp_path / "idem.stl"
    box.export(mesh_path)
    app_client = TestClient(create_app())
    headers = {"Idempotency-Key": "test-key-idem-1"}
    r1 = app_client.post(
        "/v1/jobs",
        json={"input_path": str(mesh_path), "build": False, "sample_count": 500},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1.get("idempotent_replay") is False
    job_id = j1["job_id"]
    r2 = app_client.post(
        "/v1/jobs",
        json={"input_path": str(mesh_path), "build": False, "sample_count": 500},
        headers=headers,
    )
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("idempotent_replay") is True
    assert j2["job_id"] == job_id
