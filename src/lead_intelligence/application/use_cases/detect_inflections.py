"""The Inflection Detection Engine's application-level orchestration entry
point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors CompareExecutiveUseCase's role exactly: this class knows nothing
about rules, registries, or confidence scoring — it only knows how to
hand a ComparisonResult to an InflectionDetectionEngine and return the
InflectionReport. Real orchestration logic lives in
InflectionDetectionEngine; this is the stable seam a future API/CLI layer
calls.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.dto.comparison_models import ComparisonResult
from lead_intelligence.application.dto.inflection_models import InflectionReport
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine


class DetectInflectionsUseCase:
    """Detects inflections in one ComparisonResult using a pre-configured
    engine."""

    def __init__(self, engine: InflectionDetectionEngine) -> None:
        """Bind this use case to one already-configured engine.

        Args:
            engine: An InflectionDetectionEngine already constructed with
                its InflectionRuleRegistry and InflectionProfile.
        """

        self._engine = engine

    def execute(self, comparison_result: ComparisonResult) -> InflectionReport:
        """Detect inflections in `comparison_result` and return the full
        InflectionReport.

        Args:
            comparison_result: The ComparisonResult produced by the
                Executive Comparison Engine for one record.

        Returns:
            An InflectionReport containing every detected Inflection.
        """

        logger.info(
            "Detect inflections use case starting (record_reference={})",
            comparison_result.record_reference,
        )
        report = self._engine.detect(comparison_result)
        logger.info(
            "Detect inflections use case finished: {} inflection(s) detected",
            report.inflection_count,
        )
        return report
