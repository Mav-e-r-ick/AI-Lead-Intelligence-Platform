"""Database connectivity health check.

WHY THIS FILE EXISTS:
The `/health` endpoint (interfaces/api/main.py) only proves the API
*process* is up — it says nothing about whether the database is reachable.
A load balancer or uptime monitor needs that second, separate signal
(readiness, not liveness) to know whether to route real traffic to this
instance. `check_database_connectivity` issues the cheapest possible query
(`SELECT 1`) against a real connection and reports the result as a typed
value rather than letting a raw driver exception escape to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class DatabaseHealth:
    """The outcome of one database connectivity check."""

    connected: bool
    error: str | None = None


def check_database_connectivity(engine: Engine) -> DatabaseHealth:
    """Attempt to open a connection and run `SELECT 1`.

    Any failure (unreachable host, bad credentials, database down) is
    caught and reported as `DatabaseHealth(connected=False, error=...)`
    instead of propagating, so a caller can turn this into an HTTP 200/503
    response without wrapping every call site in its own try/except.
    """

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseHealth(connected=True)
    except (
        Exception
    ) as exc:  # noqa: BLE001 - deliberately broad: any driver/connection failure is "unhealthy"
        return DatabaseHealth(connected=False, error=str(exc))
