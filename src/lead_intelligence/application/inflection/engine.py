"""InflectionDetectionEngine: the Inflection Detection Engine's single
orchestration point.

Given one ComparisonResult, runs every enabled rule in the injected
InflectionRuleRegistry, stamps each rule's InflectionDraft into a full,
timestamped Inflection (rule_id + detected_at — see rule_base.py's
docstring for why rules never stamp these themselves), and returns one
InflectionReport. This engine only detects the seven Version 1 business
events — no AI, no Google Search, no LinkedIn, no email/phone
verification, no outreach messaging.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from loguru import logger

from lead_intelligence.application.dto.comparison_models import ComparisonResult
from lead_intelligence.application.dto.inflection_models import (
    Inflection,
    InflectionReport,
)
from lead_intelligence.application.inflection.config import InflectionProfile
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry


class InflectionDetectionEngine:
    """Detects business-event inflections in one ComparisonResult, using a
    pre-configured registry and profile."""

    def __init__(
        self,
        registry: InflectionRuleRegistry,
        profile: InflectionProfile,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure an engine bound to one registry and profile.

        Args:
            registry: Every InflectionRule this engine may run.
            profile: The active InflectionProfile (which rules are
                enabled, at what confidence).
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._registry = registry
        self._profile = profile
        self._clock = clock

    def detect(self, comparison_result: ComparisonResult) -> InflectionReport:
        """Run every enabled rule against `comparison_result` and return
        one InflectionReport.

        Raises:
            InvalidInflectionConfigurationError: If the profile itself is
                invalid — raised before any rule runs.
        """

        self._profile.validate()

        logger.info(
            "Inflection detection starting: profile='{}', record_reference={}",
            self._profile.name,
            comparison_result.record_reference,
        )

        inflections: list[Inflection] = []
        for rule in self._registry.all_rules():
            if not self._profile.is_enabled(rule):
                logger.debug("Rule '{}' is disabled; skipping.", rule.metadata.rule_id)
                continue

            draft = rule.detect(comparison_result)
            if draft is None:
                continue

            base_confidence = self._profile.confidence_for(rule)
            confidence = _clamp(base_confidence * comparison_result.summary.confidence)

            inflection = Inflection(
                type=rule.metadata.inflection_type,
                confidence=confidence,
                supporting_comparisons=draft.supporting_comparisons,
                explanation=draft.explanation,
                detected_at=self._clock(),
                rule_id=rule.metadata.rule_id,
            )
            inflections.append(inflection)
            logger.debug(
                "Rule '{}' fired: type={}, confidence={:.3f}",
                rule.metadata.rule_id,
                inflection.type.value,
                inflection.confidence,
            )

        report = InflectionReport(
            record_reference=comparison_result.record_reference,
            inflections=tuple(inflections),
            generated_at=self._clock(),
        )

        logger.info(
            "Inflection detection complete: record_reference={}, {} inflection(s) "
            "detected: {}",
            report.record_reference,
            report.inflection_count,
            ", ".join(sorted(t.value for t in report.detected_types)) or "none",
        )

        return report


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
