"""Shared test fixtures for the Inflection Detection Engine's tests."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
    ComparisonStrategy,
    ComparisonSummary,
    FieldComparison,
)

FIELD_NAMES = ("name", "title", "company", "email", "phone")


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def make_field_comparison(
    field_name: str,
    existing_value: str | None,
    new_value: str | None,
    status: ComparisonStatus,
    strategy: ComparisonStrategy = ComparisonStrategy.FUZZY,
    similarity_score: float | None = None,
    conflicting_values: tuple[str, ...] = (),
    explanation: str = "test comparison",
) -> FieldComparison:
    return FieldComparison(
        field_name=field_name,
        existing_value=existing_value,
        new_value=new_value,
        status=status,
        strategy=strategy,
        similarity_score=similarity_score,
        conflicting_values=conflicting_values,
        explanation=explanation,
    )


def make_all_match_comparisons(
    **overrides: FieldComparison,
) -> tuple[FieldComparison, ...]:
    """One MATCH FieldComparison per FIELD_NAMES, with any `overrides`
    (keyed by field name) substituted in — the baseline "nothing happened"
    ComparisonResult that individual tests then perturb.
    """

    defaults = {
        field_name: make_field_comparison(
            field_name, "existing", "existing", ComparisonStatus.MATCH
        )
        for field_name in FIELD_NAMES
    }
    defaults.update(overrides)
    return tuple(defaults[field_name] for field_name in FIELD_NAMES)


def make_summary(
    field_comparisons: tuple[FieldComparison, ...],
    confidence: float = 1.0,
) -> ComparisonSummary:
    counts = {status: 0 for status in ComparisonStatus}
    for comparison in field_comparisons:
        counts[comparison.status] += 1
    return ComparisonSummary(
        fields_matched=counts[ComparisonStatus.MATCH],
        fields_changed=counts[ComparisonStatus.CHANGED],
        fields_missing=counts[ComparisonStatus.MISSING],
        fields_new=counts[ComparisonStatus.NEW],
        fields_conflict=counts[ComparisonStatus.CONFLICT],
        fields_unknown=counts[ComparisonStatus.UNKNOWN],
        confidence=confidence,
        compared_at=fixed_clock(),
    )


def make_comparison_result(
    field_comparisons: tuple[FieldComparison, ...],
    record_reference: str = "row:1",
    confidence: float = 1.0,
) -> ComparisonResult:
    return ComparisonResult(
        record_reference=record_reference,
        field_comparisons=field_comparisons,
        summary=make_summary(field_comparisons, confidence=confidence),
    )
