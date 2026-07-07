"""Tests for SqlAlchemyUnitOfWork's transaction lifecycle: commit persists,
everything else rolls back — the "all of this, or none of this" guarantee
the Persistence Architecture requires.

A temp-file-backed SQLite database (rather than sqlite:///:memory:) is used
so that separate Unit of Work instances in the same test can open separate
connections against the *same* underlying data, exactly like separate
requests would against a real PostgreSQL database.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from lead_intelligence.core.config import Settings
from lead_intelligence.infrastructure.database.session import (
    create_engine_from_settings,
    create_session_factory,
)
from lead_intelligence.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine_from_settings(
        Settings(database_url=f"sqlite:///{tmp_path / 'uow_test.db'}")
    )
    with engine.connect() as connection:
        connection.execute(text("CREATE TABLE widgets (name TEXT)"))
        connection.commit()
    return create_session_factory(engine)


def _widget_names(session_factory: sessionmaker[Session]) -> list[str]:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        rows = uow.session.execute(text("SELECT name FROM widgets")).fetchall()
    return [row[0] for row in rows]


def test_commit_persists_changes(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.execute(text("INSERT INTO widgets (name) VALUES ('a')"))
        uow.commit()

    assert _widget_names(session_factory) == ["a"]


def test_uncommitted_changes_are_rolled_back_on_exit(
    session_factory: sessionmaker[Session],
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.execute(text("INSERT INTO widgets (name) VALUES ('b')"))
        # commit() is never called.

    assert _widget_names(session_factory) == []


def test_exception_inside_with_block_rolls_back(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RuntimeError):
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            uow.session.execute(text("INSERT INTO widgets (name) VALUES ('c')"))
            raise RuntimeError("boom")

    assert _widget_names(session_factory) == []


def test_session_property_raises_outside_with_block(
    session_factory: sessionmaker[Session],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)

    with pytest.raises(RuntimeError):
        _ = uow.session


def test_session_property_raises_again_after_with_block_exits(
    session_factory: sessionmaker[Session],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)

    with uow:
        pass

    with pytest.raises(RuntimeError):
        _ = uow.session
