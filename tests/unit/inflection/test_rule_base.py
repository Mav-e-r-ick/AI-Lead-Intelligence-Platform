"""Tests for the InflectionRule contract's shared helper."""

from __future__ import annotations

from lead_intelligence.application.dto.comparison_models import ComparisonStatus
from lead_intelligence.application.inflection.rule_base import get_field_comparison
from tests.unit.inflection.fixtures import (
    make_all_match_comparisons,
    make_comparison_result,
)


class TestGetFieldComparison:
    def test_returns_matching_field(self) -> None:
        comparisons = make_all_match_comparisons()
        result = make_comparison_result(comparisons)

        found = get_field_comparison(result, "title")

        assert found is not None
        assert found.field_name == "title"
        assert found.status is ComparisonStatus.MATCH

    def test_returns_none_when_field_absent(self) -> None:
        comparisons = make_all_match_comparisons()
        result = make_comparison_result(comparisons)

        assert get_field_comparison(result, "not_a_real_field") is None
