"""Unit tests for run_pipeline.py's own helper functions (not part of the
lead_intelligence package, but plain functions in the CLI script)."""

from __future__ import annotations

from datetime import datetime, timezone

import run_pipeline
from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
    ComparisonStrategy,
    ComparisonSummary,
    FieldComparison,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _comparison_result(*field_comparisons: FieldComparison) -> ComparisonResult:
    summary = ComparisonSummary(
        fields_matched=len(
            [f for f in field_comparisons if f.status is ComparisonStatus.MATCH]
        ),
        fields_changed=len(
            [f for f in field_comparisons if f.status is ComparisonStatus.CHANGED]
        ),
        fields_missing=0,
        fields_new=len(
            [f for f in field_comparisons if f.status is ComparisonStatus.NEW]
        ),
        fields_conflict=0,
        fields_unknown=0,
        confidence=1.0,
        compared_at=_fixed_clock(),
    )
    return ComparisonResult(
        record_reference="row:1",
        field_comparisons=field_comparisons,
        summary=summary,
    )


def _field_comparison(
    field_name: str,
    existing_value: str | None,
    new_value: str | None,
    status: ComparisonStatus,
) -> FieldComparison:
    return FieldComparison(
        field_name=field_name,
        existing_value=existing_value,
        new_value=new_value,
        status=status,
        strategy=ComparisonStrategy.FUZZY,
        similarity_score=None,
        conflicting_values=(),
        explanation="test",
    )


class TestCurrentFieldValue:
    def test_none_comparison_result_returns_fallback(self) -> None:
        assert (
            run_pipeline._current_field_value(None, "title", "Old Title")
            == "Old Title"
        )

    def test_changed_field_returns_new_value(self) -> None:
        comparison = _comparison_result(
            _field_comparison(
                "title", "Old Title", "New Title", ComparisonStatus.CHANGED
            )
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "New Title"
        )

    def test_new_field_returns_new_value(self) -> None:
        comparison = _comparison_result(
            _field_comparison("title", None, "New Title", ComparisonStatus.NEW)
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", None)
            == "New Title"
        )

    def test_matched_field_returns_fallback_not_existing_value(self) -> None:
        comparison = _comparison_result(
            _field_comparison(
                "title", "Same Title", "Same Title", ComparisonStatus.MATCH
            )
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Same Title")
            == "Same Title"
        )

    def test_missing_field_returns_fallback(self) -> None:
        comparison = _comparison_result(
            _field_comparison("title", None, None, ComparisonStatus.MISSING)
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "Old Title"
        )

    def test_field_name_not_present_returns_fallback(self) -> None:
        comparison = _comparison_result(
            _field_comparison(
                "company", "Old Co", "New Co", ComparisonStatus.CHANGED
            )
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "Old Title"
        )

    def test_changed_field_with_no_new_value_falls_back(self) -> None:
        comparison = _comparison_result(
            _field_comparison("title", "Old Title", None, ComparisonStatus.CHANGED)
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "Old Title"
        )
