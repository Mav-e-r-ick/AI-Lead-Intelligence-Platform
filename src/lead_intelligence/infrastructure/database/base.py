"""SQLAlchemy declarative base class.

WHY THIS FILE EXISTS:
Every future database table will be defined as a Python class that
inherits from this one `Base` class. Having a single shared `Base` (instead
of each model file creating its own) is what lets SQLAlchemy and Alembic
discover all tables together and keep them in one consistent metadata
registry.

No tables inherit from this yet — this is foundation only.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared base class for all future ORM models (database tables)."""
