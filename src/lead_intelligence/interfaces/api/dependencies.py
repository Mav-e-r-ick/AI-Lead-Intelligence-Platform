"""FastAPI dependency-injection providers.

WHY THIS FILE EXISTS:
Route handlers should ask for "a database session" or "a unit of work"
without knowing how one is constructed. Centralizing that construction here
— behind plain functions FastAPI calls via `Depends(...)` — is what lets a
test swap in an isolated in-memory database via
`app.dependency_overrides[get_engine] = ...` without touching route code at
all.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine

from lead_intelligence.infrastructure.database.session import SessionLocal, engine
from lead_intelligence.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


def get_engine() -> Engine:
    """Return the application's configured database Engine.

    Used by read-only checks (e.g. the /health/database endpoint) that need
    to open a connection directly, without the transactional semantics of a
    Unit of Work.
    """

    return engine


def get_unit_of_work() -> Generator[SqlAlchemyUnitOfWork, None, None]:
    """Yield an open SqlAlchemyUnitOfWork for the lifetime of one request.

    The route handler is responsible for calling `uow.commit()` once its
    work succeeds; if it doesn't (or raises), `SqlAlchemyUnitOfWork.__exit__`
    rolls the transaction back automatically. No repositories are attached
    yet — that is deferred to whichever future task implements the first
    concrete repository.
    """

    with SqlAlchemyUnitOfWork(SessionLocal) as uow:
        yield uow
