"""Tests for DetectInflectionsUseCase."""

from __future__ import annotations

from lead_intelligence.application.dto.comparison_models import ComparisonStatus
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.inflection.config import default_profile
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES
from lead_intelligence.application.use_cases.detect_inflections import (
    DetectInflectionsUseCase,
)
from tests.unit.inflection.fixtures import (
    fixed_clock,
    make_all_match_comparisons,
    make_comparison_result,
    make_field_comparison,
)


def _use_case() -> DetectInflectionsUseCase:
    registry = InflectionRuleRegistry(ALL_RULES)
    engine = InflectionDetectionEngine(registry, default_profile(), clock=fixed_clock)
    return DetectInflectionsUseCase(engine)


class TestDetectInflectionsUseCase:
    def test_delegates_to_engine_and_returns_report(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        report = _use_case().execute(result)

        assert report.inflection_count == 1
        assert report.detected_types == frozenset({InflectionType.PROMOTION})

    def test_empty_report_for_no_op_comparison(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        report = _use_case().execute(result)

        assert report.inflection_count == 0
