from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_preserves_incoming_request_id_header():
    incoming_id = "test-request-id-123"
    resp = client.get("/health", headers={"X-Request-ID": incoming_id})

    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == incoming_id


def test_generates_request_id_when_missing():
    resp = client.get("/health")

    assert resp.status_code == 200
    generated = resp.headers.get("X-Request-ID")
    assert generated
    assert isinstance(generated, str)
    assert len(generated) > 0

    duration = resp.headers.get("X-Request-Duration-ms")
    assert duration is not None
