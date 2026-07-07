"""VerificationRepository — the append-only log of deliverability/validity
checks. Decorates a resolved fact with a freshness stamp; never a
competing value for that fact (the Verification/Enrichment distinction
from the Executive Intelligence Architecture).

TVerificationRecord is a placeholder type parameter, bound to the concrete
VerificationRecord domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TVerificationRecord = TypeVar("TVerificationRecord")


class VerificationRepository(
    AppendOnlyRepository[TVerificationRecord, str], Generic[TVerificationRecord]
):
    """Append and query Verification records."""

    @abstractmethod
    def get_latest(self, subject_id: str, attribute: str) -> TVerificationRecord | None:
        """Return the most recent verification check for one attribute —
        the hot path consulted immediately before every outreach send."""
