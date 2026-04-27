"""Observability hooks, webhook URL policy, rate and body limits."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from mesh2cad.api.app import create_app
from mesh2cad.observability.metrics import reset_metrics
from mesh2cad.security.rate_limit import reset_rate_limit_state
from mesh2cad.security.webhook_url import WebhookUrlRejected, validate_webhook_url


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    reset_rate_limit_state()
    reset_metrics()
    yield
    reset_rate_limit_state()
    reset_metrics()


def test_validate_webhook_rejects_loopback() -> None:
    with pytest.raises(WebhookUrlRejected):
        validate_webhook_url("https://127.0.0.1/hook")
    with pytest.raises(WebhookUrlRejected):
        validate_webhook_url("https://[::1]/x")


def test_validate_webhook_requires_https_by_default() -> None:
    with pytest.raises(WebhookUrlRejected):
        validate_webhook_url("http://example.com/hook")


def test_metrics_endpoint_respects_flag(monkeypatch) -> None:
    monkeypatch.delenv("MESH2CAD_METRICS_ENABLED", raising=False)
    c = TestClient(create_app())
    assert c.get("/metrics").status_code == 404
    monkeypatch.setenv("MESH2CAD_METRICS_ENABLED", "1")
    c2 = TestClient(create_app())
    r = c2.get("/metrics")
    assert r.status_code == 200
    assert "# HELP mesh2cad_http_requests_total" in r.text


def test_rate_limit_on_v1_process(monkeypatch, tmp_path) -> None:
    import trimesh

    monkeypatch.delenv("MESH2CAD_API_KEYS", raising=False)
    monkeypatch.setenv("MESH2CAD_RATE_LIMIT_PER_MINUTE", "3")
    box = trimesh.creation.box(extents=(1, 1, 1))
    p = tmp_path / "r.stl"
    box.export(p)
    c = TestClient(create_app())
    for _ in range(3):
        assert c.post("/v1/process", json={"input_path": str(p), "build": False}).status_code == 200
    r = c.post("/v1/process", json={"input_path": str(p), "build": False})
    assert r.status_code == 429


def test_max_request_bytes_prefers_bytes_env(monkeypatch) -> None:
    monkeypatch.setenv("MESH2CAD_MAX_REQUEST_BYTES", "4096")
    from mesh2cad.security.body_limit import max_request_bytes

    assert max_request_bytes() == 4096
