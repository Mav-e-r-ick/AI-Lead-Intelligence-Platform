"""Smoke test proving the foundation actually wires together and runs.

This does not test any business feature (none exist yet). It only checks
that the FastAPI app in interfaces/api/main.py starts up and its /health
endpoint responds, which exercises the import chain across
core -> interfaces without touching any external service.
"""

from fastapi.testclient import TestClient

from lead_intelligence.interfaces.api.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
