"""ObservationRepository — the append-only ledger of atomic, attributed claims.

Per the Persistence Architecture: this is the largest, most write-heavy
table in the system, and the one every other table's history ultimately
derives from. "Evidence" (the body of Observations bearing on one
question) is deliberately not a separate repository — it's the query this
repository answers directly, per that document's explicit reasoning
against a redundant second table.

TObservation is a placeholder type parameter, bound to the concrete
Observation domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TObservation = TypeVar("TObservation")


class ObservationRepository(
    AppendOnlyRepository[TObservation, str], Generic[TObservation]
):
    """Append and query Observations."""

    @abstractmethod
    def find_evidence(
        self,
        subject_id: str,
        attribute: str,
        *,
        since: datetime | None = None,
    ) -> Sequence[TObservation]:
        """Return every Observation bearing on one (subject, attribute)
        question — this *is* "Evidence," as a query rather than a table.

        Args:
            subject_id: The Person or Company this claim is about.
            attribute: Which fact is being claimed (e.g. "title").
            since: If given, only Observations at or after this time —
                used by Conflict Resolution's recency weighting.
        """

    @abstractmethod
    def find_by_provider(
        self, provider_id: str, *, since: datetime | None = None
    ) -> Sequence[TObservation]:
        """Return Observations from one provider — for provider-level
        debugging/analysis, not part of the resolution hot path."""
