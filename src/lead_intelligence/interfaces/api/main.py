"""FastAPI application entry point.

WHY THIS FILE EXISTS (AND WHY IT HAS /health ENDPOINTS):
This is the only "runnable" piece of code in the whole foundation. It
exists to prove that the project's layers are wired together correctly —
that `core.config`, `core.logging`, and the package structure all import
cleanly — *before* any real feature is built on top of them.

Two health endpoints, deliberately distinct:
- `/health` is a liveness check: is the API process up at all? No
  dependencies are touched, so it never fails just because the database is
  down.
- `/health/database` is a readiness check: is the *database* currently
  reachable? A load balancer uses this one to decide whether to route real
  traffic to this instance.
Neither contains business logic — it does not touch leads, emails, or AI
providers. Every other route file (e.g. for leads or outreach) will be
added under `routes/` in a future task, and included here with
`app.include_router(...)`.

Run it locally with:
    uvicorn lead_intelligence.interfaces.api.main:app --reload
"""

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import Engine

from lead_intelligence.core.logging import configure_logging
from lead_intelligence.infrastructure.database.health import check_database_connectivity
from lead_intelligence.interfaces.api.dependencies import get_engine

configure_logging()

app = FastAPI(
    title="AI Lead Intelligence Platform",
    version="0.1.0",
    description=(
        "Foundation build. No business features are implemented yet — "
        "see the project README for the roadmap."
    ),
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the API process is up and able to respond to requests."""

    return {"status": "ok"}


@app.get("/health/database", tags=["health"])
def database_health_check(
    response: Response, db_engine: Engine = Depends(get_engine)
) -> dict[str, str | None]:
    """Report whether the configured database is currently reachable.

    Returns HTTP 200 with `{"status": "ok"}` when a connection can be
    opened and `SELECT 1` succeeds, or HTTP 503 with `{"status":
    "unavailable", "error": "..."}` otherwise.
    """

    health = check_database_connectivity(db_engine)
    if not health.connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if health.connected else "unavailable",
        "error": health.error,
    }
