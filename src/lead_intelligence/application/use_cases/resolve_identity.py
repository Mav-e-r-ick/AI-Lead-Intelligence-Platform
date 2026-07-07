"""The Identity Resolution Engine's application-level orchestration entry
point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors CleanDatasetUseCase's role exactly: this class knows nothing about
signal extraction, candidate generation, or scoring — it only knows how to
hand a CleanedLeadDataset to an IdentityResolutionEngine and return the
IdentityResolutionResult. Real orchestration logic lives in
IdentityResolutionEngine; this is the stable seam a future API/CLI layer calls.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.dto.cleaning_models import CleanedLeadDataset
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityResolutionResult,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)


class ResolveIdentityUseCase:
    """Resolves identities for a dataset using a pre-configured engine."""

    def __init__(self, engine: IdentityResolutionEngine) -> None:
        """Bind this use case to one already-configured engine.

        Args:
            engine: An IdentityResolutionEngine already constructed with
                its candidate port and IdentityResolutionProfile.
        """

        self._engine = engine

    def execute(
        self, dataset: CleanedLeadDataset, subject_type: SubjectType
    ) -> IdentityResolutionResult:
        """Resolve identities for `dataset` and return the full result.

        Args:
            dataset: The CleanedLeadDataset produced by the Cleaning Engine.
            subject_type: Which Subject type (Person or Company) this
                dataset's records should be resolved as.

        Returns:
            An IdentityResolutionResult containing every record's outcome,
            the manual review queue, the full audit trail, and run metrics.
        """

        logger.info(
            "Resolve identity use case starting ({} record(s), subject_type={})",
            dataset.record_count,
            subject_type.value,
        )
        result = self._engine.resolve_dataset(dataset, subject_type)
        logger.info(
            "Resolve identity use case finished: {} auto-merged, {} to review, "
            "{} new identities",
            result.metrics.auto_merged,
            result.metrics.sent_to_review,
            result.metrics.new_identities,
        )
        return result
