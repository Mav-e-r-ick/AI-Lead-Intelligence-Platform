"""Database plumbing: engine, session factory, declarative base, Unit of
Work, and connectivity health check.

No tables (e.g. a `leads` table) are defined yet — this is infrastructure
only. See ../README.md.
"""

from __future__ import annotations

from lead_intelligence.infrastructure.database.base import Base
from lead_intelligence.infrastructure.database.health import (
    DatabaseHealth,
    check_database_connectivity,
)
from lead_intelligence.infrastructure.database.session import (
    create_engine_from_settings,
    create_session_factory,
    get_db_session,
)
from lead_intelligence.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "Base",
    "DatabaseHealth",
    "check_database_connectivity",
    "create_engine_from_settings",
    "create_session_factory",
    "get_db_session",
    "SqlAlchemyUnitOfWork",
]
