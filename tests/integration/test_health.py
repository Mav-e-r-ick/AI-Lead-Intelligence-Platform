"""Smoke test proving the foundation actually wires together and runs.

This does not test any business feature (none exist yet). It checks that
the FastAPI app in interfaces/api/main.py starts up and its /health
endpoint responds (exercising the import chain across core -> interfaces
without touching any external service), and that /health/database
correctly reports both a reachable and an unreachable database.
"""

from sqlalchemy import create_engine
from fastapi.testclient import TestClient

from lead_intelligence.interfaces.api.dependencies import get_engine
from lead_intelligence.interfaces.api.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_check_returns_ok_when_database_reachable() -> None:
    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "error": None}


def test_database_health_check_returns_503_when_database_unreachable() -> None:
    # Port 1 is reserved and never has anything listening on it, so the
    # connection is refused immediately and deterministically.
    broken_engine = create_engine(
        "postgresql+psycopg2://user:pass@localhost:1/nonexistent"
    )
    app.dependency_overrides[get_engine] = lambda: broken_engine

    try:
        response = client.get("/health/database")
    finally:
        app.dependency_overrides.pop(get_engine, None)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["error"]
