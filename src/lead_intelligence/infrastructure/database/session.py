"""Database engine and session factory.

WHY THIS FILE EXISTS:
Talking to a database requires (1) an `engine` — the object that knows how
to open connections to a specific database URL, and (2) a `Session` —
a short-lived "workspace" used to load/save objects within one unit of
work (e.g. one API request). This module creates both, once, so the rest
of the app never has to think about connection details, only about
borrowing a session via `get_db_session()`.

This is foundation-only plumbing: no queries or tables are defined here.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from lead_intelligence.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it is closed afterward.

    Intended for use as a FastAPI dependency later, e.g.:
        def endpoint(db: Session = Depends(get_db_session)): ...
    """

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
