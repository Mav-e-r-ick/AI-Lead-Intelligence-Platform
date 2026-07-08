"""Unit tests for CompareExecutiveUseCase — a thin wrapper, tested as such."""

from __future__ import annotations

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison.config import default_profile
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.use_cases.compare_executive import (
    CompareExecutiveUseCase,
)
from tests.unit.comparison.fixtures import (
    fixed_clock,
    make_existing_record,
    make_observation,
)


def test_execute_returns_a_comparison_result_from_the_engine() -> None:
    engine = ComparisonEngine(default_profile(), clock=fixed_clock)
    use_case = CompareExecutiveUseCase(engine)
    record = make_existing_record({fc.PRIMARY_EMAIL: "ada@acme.com"})
    observations = [make_observation("email", "ada@acme.com")]

    result = use_case.execute(record, observations, "row:1")

    assert result.record_reference == "row:1"
    assert result.summary.fields_matched == 1
    assert len(result.field_comparisons) == 5
