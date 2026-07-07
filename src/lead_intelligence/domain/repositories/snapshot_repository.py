"""SnapshotRepository — the immutable, append-only ledger of resolved
belief changes over time. What the Timeline (a derived view, not a table
— see the Persistence Architecture) is assembled from.

TSnapshot is a placeholder type parameter, bound to the concrete Snapshot
domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TSnapshot = TypeVar("TSnapshot")


class SnapshotRepository(AppendOnlyRepository[TSnapshot, str], Generic[TSnapshot]):
    """Append and query Snapshots."""

    @abstractmethod
    def get_latest(self, subject_id: str) -> TSnapshot | None:
        """Return the most recent Snapshot for a Subject — "current state,"
        always derived by ordering, never a separately stored pointer."""

    @abstractmethod
    def get_as_of(self, subject_id: str, as_of: datetime) -> TSnapshot | None:
        """Return the Snapshot that was current as of a given moment."""

    @abstractmethod
    def get_history(self, subject_id: str) -> Sequence[TSnapshot]:
        """Return every Snapshot for a Subject, chronologically ordered —
        the historical half of that Subject's Timeline."""
