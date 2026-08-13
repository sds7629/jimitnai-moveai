from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_db_reports_connected():
    """Real round trip to Postgres (docker compose's `db` service), not a
    mock — this is what agents/platform-infra.md's DoD item #1 asks for."""
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "connected"}


def test_unknown_route_returns_404():
    resp = client.get("/this-route-does-not-exist")
    assert resp.status_code == 404


def test_health_rejects_wrong_method():
    resp = client.post("/health")
    assert resp.status_code == 405
