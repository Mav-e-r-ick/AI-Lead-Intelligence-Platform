"""Database engine and session factory.

WHY THIS FILE EXISTS:
Talking to a database requires (1) an `engine` — the object that knows how
to open connections to a specific database URL, and (2) a `Session` —
a short-lived "workspace" used to load/save objects within one unit of
work (e.g. one API request). This module creates both.

WHY FACTORY FUNCTIONS INSTEAD OF ONLY MODULE-LEVEL GLOBALS:
A module-level `engine = create_engine(...)` (the original foundation-task
version of this file) is convenient but hard to test — every test that
imports this module gets the *same* engine, pointed at whatever
`DATABASE_URL` happens to be configured in the environment, with no way to
substitute an isolated in-memory database for a specific test. Extracting
`create_engine_from_settings()` and `create_session_factory()` as pure
functions lets tests build their own throwaway engine/session pair (e.g.
`create_engine_from_settings(Settings(database_url="sqlite:///:memory:"))`)
without touching the app's real configuration at all. The module-level
`engine`/`SessionLocal` below are kept for convenience — most call sites
still just want "the configured database" — but they are now *built from*
the same testable functions, not a separate code path.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from lead_intelligence.core.config import Settings, get_settings


def create_engine_from_settings(settings: Settings) -> Engine:
    """Build a SQLAlchemy Engine from typed application settings.

    Pool sizing (`pool_size`, `max_overflow`, `pool_pre_ping`) is only
    meaningful for a real client/server database like PostgreSQL — SQLite
    has no comparable connection pool, and passing those arguments to it
    raises a TypeError. SQLite instead gets `check_same_thread=False`,
    which is what lets a single SQLite connection be reused safely across
    the worker threads FastAPI runs synchronous request handlers in.
    """

    if settings.database_url.startswith("sqlite"):
        return create_engine(
            settings.database_url,
            future=True,
            connect_args={"check_same_thread": False},
        )

    return create_engine(
        settings.database_url,
        future=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=settings.database_pool_pre_ping,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to the given engine.

    `autoflush=False, autocommit=False` means nothing is sent to the
    database until code explicitly asks for it (via a flush or commit) —
    the caller stays in control of exactly when writes happen, which
    matters once transaction boundaries (see unit_of_work.py) are in play.
    """

    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


settings = get_settings()
engine = create_engine_from_settings(settings)
SessionLocal = create_session_factory(engine)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it is closed afterward.

    Intended for use as a FastAPI dependency, e.g.:
        def endpoint(db: Session = Depends(get_db_session)): ...
    Superseded for write operations by get_unit_of_work
    (interfaces/api/dependencies.py), which adds commit/rollback semantics
    on top of this same session lifecycle — this function remains useful
    for simple, read-only endpoints that don't need a Unit of Work.
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
