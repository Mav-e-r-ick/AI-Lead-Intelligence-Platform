"""The Executive Processing Pipeline's application-level orchestration
entry point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors EnrichSubjectUseCase's, CompareExecutiveUseCase's,
DetectInflectionsUseCase's, and VerifyContactUseCase's role exactly: this
class knows nothing about enrichment providers, comparison rules,
inflection rules, or verification providers — it only knows how to hand
one executive record to an ExecutiveProcessingOrchestrator and return the
ExecutiveProcessingReport. Real orchestration logic lives in
ExecutiveProcessingOrchestrator; this is the stable seam a future API/CLI
layer calls.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingReport,
)
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)


class ProcessExecutiveUseCase:
    """Processes one executive record using a pre-configured orchestrator."""

    def __init__(self, orchestrator: ExecutiveProcessingOrchestrator) -> None:
        """Bind this use case to one already-configured orchestrator.

        Args:
            orchestrator: An ExecutiveProcessingOrchestrator already
                constructed with its EnrichmentCoordinator, ComparisonEngine,
                InflectionDetectionEngine, and optional VerificationCoordinator.
        """

        self._orchestrator = orchestrator

    def execute(
        self, existing_record: CleanedLeadRecord, subject_id: str
    ) -> ExecutiveProcessingReport:
        """Process `existing_record` end to end and return the full report.

        Args:
            existing_record: The existing (cleaned) executive record to
                process.
            subject_id: An opaque id for this executive, carried through
                every pipeline stage.

        Returns:
            An ExecutiveProcessingReport containing every stage's result
            (or None for a stage that didn't run/failed), the overall
            status, and any stage errors encountered.
        """

        logger.info("Process executive use case starting (subject_id={})", subject_id)
        report = self._orchestrator.process(existing_record, subject_id)
        logger.info(
            "Process executive use case finished: subject_id={}, status={}",
            subject_id,
            report.status.value,
        )
        return report
