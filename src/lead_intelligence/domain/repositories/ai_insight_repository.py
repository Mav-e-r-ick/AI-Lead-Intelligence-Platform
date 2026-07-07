"""AIInsightRepository — the append-only, regenerable cache of
AI-generated summaries and scores. Per the Digital Twin architecture: each
generation is immutable once created and tagged with the Timeline state
and model/prompt version that produced it; "current" is simply the latest
generation, never a separately mutated pointer.

TAIInsight is a placeholder type parameter, bound to the concrete
AIInsight domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TAIInsight = TypeVar("TAIInsight")


class AIInsightRepository(AppendOnlyRepository[TAIInsight, str], Generic[TAIInsight]):
    """Append and query AI-derived insights."""

    @abstractmethod
    def get_latest(self, subject_id: str, insight_type: str) -> TAIInsight | None:
        """Return the most recent generation of one insight type for a
        Subject (e.g. the latest career-narrative summary)."""
