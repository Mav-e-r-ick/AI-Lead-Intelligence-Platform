"""OutreachHistoryRepository — the append-only, compliance-grade record of
what was actually sent, to whom, when, and with what outcome.

TOutreachEvent is a placeholder type parameter, bound to the concrete
OutreachEvent domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TOutreachEvent = TypeVar("TOutreachEvent")


class OutreachHistoryRepository(
    AppendOnlyRepository[TOutreachEvent, str], Generic[TOutreachEvent]
):
    """Append and query outreach events."""

    @abstractmethod
    def find_by_twin(self, twin_id: str) -> Sequence[TOutreachEvent]:
        """Every outreach event ever sent to this person, across *every*
        campaign — required to answer "how many times have we ever
        contacted this person," the basis for the global suppression /
        frequency-capping guarantee (Digital Twin architecture, §6)."""

    @abstractmethod
    def find_by_lead(self, lead_id: str) -> Sequence[TOutreachEvent]:
        """Outreach history scoped to one campaign's Lead record."""
