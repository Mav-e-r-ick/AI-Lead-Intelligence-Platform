"""The Cleaning Engine's application-level orchestration entry point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors ImportDatasetUseCase's role exactly: this class knows nothing about
individual rules, stages, or field mappings — it only knows how to hand an
ImportedLeadDataset to a CleaningPipeline and return the CleaningResult.
Real orchestration logic lives in CleaningPipeline; this is the stable
seam a future API/CLI layer calls.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.cleaning.pipeline import CleaningPipeline
from lead_intelligence.application.dto.cleaning_models import CleaningResult
from lead_intelligence.application.dto.models import ImportedLeadDataset


class CleanDatasetUseCase:
    """Cleans a dataset using a pre-configured CleaningPipeline."""

    def __init__(self, pipeline: CleaningPipeline) -> None:
        """Bind this use case to one already-configured pipeline.

        Args:
            pipeline: A CleaningPipeline already constructed with its rule
                set and CleaningProfile.
        """

        self._pipeline = pipeline

    def execute(self, dataset: ImportedLeadDataset) -> CleaningResult:
        """Clean `dataset` and return the full CleaningResult.

        Args:
            dataset: The ImportedLeadDataset produced by the Import Engine.

        Returns:
            A CleaningResult containing the cleaned dataset, a human-readable
            report, raw metrics, and the full run-wide audit trail.
        """

        logger.info(
            "Clean dataset use case starting ({} record(s))", len(dataset.records)
        )
        result = self._pipeline.run(dataset)
        logger.info(
            "Clean dataset use case finished: {} record(s), {} warning(s)",
            result.metrics.records_processed,
            result.metrics.warnings_generated,
        )
        return result
