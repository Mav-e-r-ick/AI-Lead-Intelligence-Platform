"""The Executive Comparison Engine's application-level orchestration entry
point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors ResolveIdentityUseCase's and EnrichSubjectUseCase's role exactly:
this class knows nothing about field rules, resolvers, or comparison
strategies — it only knows how to hand an existing record and its new
observations to a ComparisonEngine and return the ComparisonResult. Real
orchestration logic lives in ComparisonEngine; this is the stable seam a
future API/CLI layer calls.
"""

from __future__ import annotations

from typing import Sequence

from loguru import logger

from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.comparison_models import ComparisonResult
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate


class CompareExecutiveUseCase:
    """Compares one executive record using a pre-configured engine."""

    def __init__(self, engine: ComparisonEngine) -> None:
        """Bind this use case to one already-configured engine.

        Args:
            engine: A ComparisonEngine already constructed with its
                ComparisonProfile.
        """

        self._engine = engine

    def execute(
        self,
        existing_record: CleanedLeadRecord,
        observations: Sequence[ObservationCandidate],
        record_reference: str,
    ) -> ComparisonResult:
        """Compare `existing_record` against `observations` and return the
        full ComparisonResult.

        Args:
            existing_record: The existing (cleaned) executive record.
            observations: ObservationCandidates newly collected for this
                same executive (e.g. from the Company Website Provider).
            record_reference: An opaque, traceable reference to
                `existing_record` (e.g. "row:42").

        Returns:
            A ComparisonResult containing one FieldComparison per
            configured field and a summary.
        """

        logger.info(
            "Compare executive use case starting (record_reference={}, "
            "{} observation(s))",
            record_reference,
            len(observations),
        )
        result = self._engine.compare(existing_record, observations, record_reference)
        logger.info(
            "Compare executive use case finished: {} matched, {} changed, "
            "{} conflict(s)",
            result.summary.fields_matched,
            result.summary.fields_changed,
            result.summary.fields_conflict,
        )
        return result
