"""Tests for the database connectivity health check
(infrastructure/database/health.py)."""

from __future__ import annotations

from sqlalchemy import create_engine

from lead_intelligence.infrastructure.database.health import check_database_connectivity


def test_reports_connected_for_a_reachable_database() -> None:
    engine = create_engine("sqlite:///:memory:")

    health = check_database_connectivity(engine)

    assert health.connected is True
    assert health.error is None


def test_reports_not_connected_for_an_unreachable_database() -> None:
    # Port 1 is a well-known reserved port with nothing listening on it, so
    # the connection is refused immediately and deterministically, with no
    # real network dependency or timeout to wait out.
    engine = create_engine("postgresql+psycopg2://user:pass@localhost:1/nonexistent")

    health = check_database_connectivity(engine)

    assert health.connected is False
    assert health.error is not None
