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


# ------------------------------------------------------------------
# CORS -- both default frontend origins must be allowed (a real browser CORS
# error was traced to 127.0.0.1:5173 being blocked while localhost:5173 was
# allowed; see app/core/config.py's Settings.frontend_origins).
# ------------------------------------------------------------------


def test_cors_allows_localhost_frontend_origin():
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_allows_127_0_0_1_frontend_origin():
    resp = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
    assert resp.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_cors_rejects_unrelated_origin():
    resp = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in resp.headers
