"""Tests for the generic Repository / AppendOnlyRepository / MutableRepository
contracts that every named repository interface builds on.
"""

from __future__ import annotations

import pytest

from lead_intelligence.domain.repositories.base_repository import (
    AppendOnlyRepository,
    MutableRepository,
    Repository,
)


def test_append_only_repository_has_no_update_method() -> None:
    """The 'make illegal states unrepresentable' guarantee: an append-only
    repository must not even expose an update() to call."""

    assert not hasattr(AppendOnlyRepository, "update")


def test_mutable_repository_has_update_method() -> None:
    assert hasattr(MutableRepository, "update")


def test_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Repository()  # type: ignore[abstract]


def test_incomplete_append_only_repository_cannot_be_instantiated() -> None:
    class IncompleteRepo(AppendOnlyRepository[str, str]):
        def get_by_id(self, entity_id: str) -> str | None:
            return None

        def exists(self, entity_id: str) -> bool:
            return False

        # `add` intentionally omitted.

    with pytest.raises(TypeError):
        IncompleteRepo()  # type: ignore[abstract]


def test_fully_implemented_append_only_repository_can_be_instantiated() -> None:
    class InMemoryRepo(AppendOnlyRepository[str, str]):
        def __init__(self) -> None:
            self._items: dict[str, str] = {}

        def get_by_id(self, entity_id: str) -> str | None:
            return self._items.get(entity_id)

        def exists(self, entity_id: str) -> bool:
            return entity_id in self._items

        def add(self, entity: str) -> None:
            self._items[entity] = entity

    repo = InMemoryRepo()
    repo.add("x")

    assert repo.exists("x")
    assert repo.get_by_id("x") == "x"
    assert not repo.exists("missing")


def test_fully_implemented_mutable_repository_can_be_instantiated() -> None:
    class InMemoryMutableRepo(MutableRepository[str, str]):
        def __init__(self) -> None:
            self._items: dict[str, str] = {}

        def get_by_id(self, entity_id: str) -> str | None:
            return self._items.get(entity_id)

        def exists(self, entity_id: str) -> bool:
            return entity_id in self._items

        def add(self, entity: str) -> None:
            self._items[entity] = entity

        def update(self, entity: str) -> None:
            self._items[entity] = entity

    repo = InMemoryMutableRepo()
    repo.add("x")
    repo.update("x")

    assert repo.exists("x")
