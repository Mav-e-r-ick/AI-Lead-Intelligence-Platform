"""End-to-end unit tests for InflectionDetectionEngine.detect()."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.comparison_models import ComparisonStatus
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.inflection.config import (
    InflectionProfile,
    InflectionRuleOverride,
    default_profile,
)
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES
from lead_intelligence.domain.exceptions import InvalidInflectionConfigurationError
from tests.unit.inflection.fixtures import (
    fixed_clock,
    make_all_match_comparisons,
    make_comparison_result,
    make_field_comparison,
)


def _engine(profile: InflectionProfile | None = None) -> InflectionDetectionEngine:
    registry = InflectionRuleRegistry(ALL_RULES)
    return InflectionDetectionEngine(
        registry, profile or default_profile(), clock=fixed_clock
    )


class TestInflectionDetectionEngine:
    def test_no_inflections_when_everything_matches(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        report = _engine().detect(result)

        assert report.inflections == ()
        assert report.inflection_count == 0
        assert report.detected_types == frozenset()

    def test_detects_promotion(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        report = _engine().detect(result)

        assert report.inflection_count == 1
        assert report.detected_types == frozenset({InflectionType.PROMOTION})

    def test_report_carries_record_reference(self) -> None:
        result = make_comparison_result(
            make_all_match_comparisons(), record_reference="row:42"
        )

        report = _engine().detect(result)

        assert report.record_reference == "row:42"

    def test_report_generated_at_uses_injected_clock(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        report = _engine().detect(result)

        assert report.generated_at == fixed_clock()

    def test_inflection_detected_at_uses_injected_clock(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        report = _engine().detect(result)

        assert report.inflections[0].detected_at == fixed_clock()

    def test_inflection_carries_rule_id(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        report = _engine().detect(result)

        assert report.inflections[0].rule_id == "INF-001"

    def test_confidence_is_base_confidence_times_summary_confidence(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title), confidence=0.5
        )

        report = _engine().detect(result)

        # PromotionRule base_confidence is 0.90.
        assert report.inflections[0].confidence == pytest.approx(0.90 * 0.5)

    def test_confidence_is_clamped_to_one(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title), confidence=1.0
        )
        profile = InflectionProfile(
            name="test",
            rule_overrides={"INF-001": InflectionRuleOverride(base_confidence=1.0)},
        )

        report = _engine(profile).detect(result)

        assert report.inflections[0].confidence == 1.0

    def test_disabled_rule_never_fires(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))
        profile = InflectionProfile(
            name="test",
            rule_overrides={"INF-001": InflectionRuleOverride(enabled=False)},
        )

        report = _engine(profile).detect(result)

        assert report.inflection_count == 0

    def test_multiple_rules_can_fire_together(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        email = make_field_comparison(
            "email", "old@example.com", "new@example.com", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title, email=email)
        )

        report = _engine().detect(result)

        assert report.inflection_count == 2
        assert report.detected_types == frozenset(
            {InflectionType.PROMOTION, InflectionType.CONTACT_INFO_CHANGED}
        )

    def test_invalid_profile_raises_before_any_rule_runs(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())
        profile = InflectionProfile(
            name="broken",
            rule_overrides={"INF-001": InflectionRuleOverride(base_confidence=2.0)},
        )

        with pytest.raises(InvalidInflectionConfigurationError):
            _engine(profile).detect(result)

    def test_deterministic_across_repeated_runs(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        report_one = _engine().detect(result)
        report_two = _engine().detect(result)

        assert report_one == report_two
