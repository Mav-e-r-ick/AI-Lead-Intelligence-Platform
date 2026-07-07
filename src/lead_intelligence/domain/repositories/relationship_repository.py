"""RelationshipRepository — the generic, graph-shaped edge table connecting
Subjects to other Subjects or Artifacts (Companies, People, Universities,
Boards, Investors, Events, Awards, Products, Patents, Skills, Technologies,
News). One uniform representation for every relationship type, per the
Digital Twin architecture — this is also what makes a future graph
database migration an infrastructure decision rather than a redesign (see
the Persistence Architecture's storage recommendation).

TRelationship is a placeholder type parameter, bound to the concrete
Relationship domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TRelationship = TypeVar("TRelationship")


class RelationshipRepository(
    AppendOnlyRepository[TRelationship, str], Generic[TRelationship]
):
    """Append and query Relationship edges, in both directions."""

    @abstractmethod
    def find_by_subject(
        self, subject_id: str, relationship_type: str | None = None
    ) -> Sequence[TRelationship]:
        """Forward lookup: every relationship this Subject is the source
        of (e.g. "this person's employers"), optionally filtered by type."""

    @abstractmethod
    def find_by_object(
        self, object_id: str, relationship_type: str | None = None
    ) -> Sequence[TRelationship]:
        """Reverse lookup: every relationship where this is the target
        (e.g. "everyone who works at this company") — the index that
        enables graph-like traversal without a graph database."""
