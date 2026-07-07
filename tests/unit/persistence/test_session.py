"""Tests for engine/session factory construction
(infrastructure/database/session.py)."""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from lead_intelligence.core.config import Settings
from lead_intelligence.infrastructure.database.session import (
    create_engine_from_settings,
    create_session_factory,
)


def test_sqlite_url_produces_a_sqlite_engine() -> None:
    engine = create_engine_from_settings(Settings(database_url="sqlite:///:memory:"))

    assert engine.dialect.name == "sqlite"


def test_postgres_url_produces_a_postgres_engine_with_configured_pool_settings() -> (
    None
):
    settings = Settings(
        database_url="postgresql+psycopg2://user:pass@localhost/db",
        database_pool_size=7,
        database_max_overflow=3,
    )

    engine = create_engine_from_settings(settings)

    assert engine.dialect.name == "postgresql"
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.size() == 7


def test_session_factory_produces_sessions_bound_to_the_given_engine() -> None:
    engine = create_engine_from_settings(Settings(database_url="sqlite:///:memory:"))
    factory = create_session_factory(engine)

    session = factory()
    try:
        assert isinstance(session, Session)
        assert session.get_bind() is engine
    finally:
        session.close()


def test_two_calls_to_create_engine_from_settings_produce_independent_engines() -> None:
    """A regression guard for the reason this file was refactored into
    factory functions: each call must build a fresh engine, not share
    module-level state, so tests can point at isolated databases."""

    engine_a = create_engine_from_settings(Settings(database_url="sqlite:///:memory:"))
    engine_b = create_engine_from_settings(Settings(database_url="sqlite:///:memory:"))

    assert engine_a is not engine_b
