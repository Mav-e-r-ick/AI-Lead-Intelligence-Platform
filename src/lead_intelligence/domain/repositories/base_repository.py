"""Generic repository contracts every named repository interface builds on.

WHY THIS FILE EXISTS:
The approved Persistence Architecture found that most of this platform's
tables are append-only ledgers (Observations, Snapshots, Relationship
edges, ...) while a small few are genuinely mutable, operational records
(Leads, and the small status-flag surface on Digital Twin/Company). That
distinction is encoded here at the type level, not left as a convention
someone has to remember: `AppendOnlyRepository` simply has no `update`
method to call. A repository that shouldn't support updates *cannot*
support them, the same "make illegal states unrepresentable" principle
already used for QualityCheckRule in the Cleaning Engine.

WHY THESE ARE GENERIC (TypeVar) RATHER THAN BOUND TO CONCRETE ENTITIES:
Today's task is the persistence *infrastructure* only — the Digital Twin,
Observation, Snapshot, etc. domain entities designed in prior architecture
sessions have not been implemented yet (that is explicitly a future task).
Making every repository generic over its entity type lets these interfaces
be fully written, fully typed, and fully testable today, without inventing
placeholder entity classes that would misrepresent unfinished design work
as done. Once the concrete entities exist, the named interfaces below bind
these TypeVars to them with no change to this file.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TEntity = TypeVar("TEntity")
TId = TypeVar("TId")


class Repository(ABC, Generic[TEntity, TId]):
    """The minimal read contract every repository provides."""

    @abstractmethod
    def get_by_id(self, entity_id: TId) -> TEntity | None:
        """Return the entity with this ID, or None if it doesn't exist."""

    @abstractmethod
    def exists(self, entity_id: TId) -> bool:
        """Return whether an entity with this ID exists, without loading it."""


class AppendOnlyRepository(Repository[TEntity, TId], Generic[TEntity, TId]):
    """A repository for entities that are only ever created, never edited.

    Covers: Observations, Snapshots, Relationship edges, Verification
    records, AI-derived insights, Outreach history, Audit logs — every
    ledger-shaped table identified in the Persistence Architecture.
    """

    @abstractmethod
    def add(self, entity: TEntity) -> None:
        """Append a new, immutable entity. There is deliberately no update()."""


class MutableRepository(Repository[TEntity, TId], Generic[TEntity, TId]):
    """A repository for entities that are fully, generically mutable.

    Covers: Lead — genuinely mutable, operational CRM-style state, by
    design (see the Persistence Architecture's analysis of why Leads are
    different in kind from everything else in this schema).

    Digital Twin and Company are *not* built on this base, even though
    they have a small mutable surface (suppression/retirement status):
    their own interfaces expose a narrow, explicit `update_status()`
    instead of a generic `update()`, so it's visible at every call site
    that status flags are the *only* thing about them that ever changes —
    their factual history lives elsewhere, in Snapshots, immutable.
    """

    @abstractmethod
    def add(self, entity: TEntity) -> None:
        """Create a new entity."""

    @abstractmethod
    def update(self, entity: TEntity) -> None:
        """Persist changes to an existing entity's mutable fields."""
