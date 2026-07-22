"""End-to-end unit tests for ComparisonEngine.compare()."""

from __future__ import annotations

import pytest

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison.config import (
    ComparisonFieldRule,
    ComparisonProfile,
    default_profile,
)
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.dto.comparison_models import (
    ComparisonStatus,
    ComparisonStrategy,
)
from lead_intelligence.domain.exceptions import InvalidComparisonConfigurationError
from tests.unit.comparison.fixtures import (
    fixed_clock,
    make_existing_record,
    make_observation,
)


def _engine(profile: ComparisonProfile | None = None) -> ComparisonEngine:
    return ComparisonEngine(profile or default_profile(), clock=fixed_clock)


def _field(result, field_name: str):
    return next(c for c in result.field_comparisons if c.field_name == field_name)


def test_fuzzy_field_matches_on_minor_formatting_difference() -> None:
    record = make_existing_record({fc.FIRST_NAME: "Ada", fc.LAST_NAME: "Lovelace"})
    observations = [make_observation("full_name", "ada   lovelace")]

    result = _engine().compare(record, observations, "row:1")

    name = _field(result, "name")
    assert name.status is ComparisonStatus.MATCH
    assert name.similarity_score == 1.0


def test_fuzzy_field_changed_on_substantially_different_value() -> None:
    record = make_existing_record({fc.TITLE: "VP Engineering"})
    observations = [make_observation("title", "Chief Financial Officer")]

    result = _engine().compare(record, observations, "row:1")

    title = _field(result, "title")
    assert title.status is ComparisonStatus.CHANGED
    assert title.similarity_score is not None
    assert title.similarity_score < 0.80


def test_exact_field_matches_after_normalization() -> None:
    record = make_existing_record({fc.PRIMARY_EMAIL: "ada@acme.com"})
    observations = [make_observation("email", "ADA@ACME.COM")]

    result = _engine().compare(record, observations, "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.MATCH
    assert email.similarity_score == 1.0


def test_exact_field_changed_when_truly_different() -> None:
    record = make_existing_record({fc.PRIMARY_EMAIL: "ada@acme.com"})
    observations = [make_observation("email", "grace@acme.com")]

    result = _engine().compare(record, observations, "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.CHANGED
    assert email.similarity_score == 0.0


def test_exact_phone_field_matches_despite_formatting_differences() -> None:
    record = make_existing_record({fc.PRIMARY_PHONE: "+15551234567"})
    observations = [make_observation("phone", "+1 (555) 123-4567")]

    result = _engine().compare(record, observations, "row:1")

    phone = _field(result, "phone")
    assert phone.status is ComparisonStatus.MATCH


def test_missing_when_existing_present_and_no_observation() -> None:
    record = make_existing_record({fc.PRIMARY_EMAIL: "ada@acme.com"})

    result = _engine().compare(record, [], "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.MISSING
    assert email.existing_value == "ada@acme.com"
    assert email.new_value is None


def test_new_when_existing_absent_and_observation_present() -> None:
    record = make_existing_record()
    observations = [make_observation("email", "ada@acme.com")]

    result = _engine().compare(record, observations, "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.NEW
    assert email.existing_value is None
    assert email.new_value == "ada@acme.com"


def test_unknown_when_both_absent() -> None:
    record = make_existing_record()

    result = _engine().compare(record, [], "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.UNKNOWN
    assert email.existing_value is None
    assert email.new_value is None
    assert email.similarity_score is None


def test_conflict_when_multiple_distinct_new_values_found() -> None:
    record = make_existing_record()
    observations = [
        make_observation("title", "CEO"),
        make_observation("title", "President"),
    ]

    result = _engine().compare(record, observations, "row:1")

    title = _field(result, "title")
    assert title.status is ComparisonStatus.CONFLICT
    assert title.new_value is None
    assert title.conflicting_values == ("CEO", "President")


def test_conflict_not_triggered_by_trivial_casing_or_whitespace_differences() -> None:
    record = make_existing_record()
    observations = [
        make_observation("title", "Chief Executive Officer"),
        make_observation("title", "  chief   executive officer "),
    ]

    result = _engine().compare(record, observations, "row:1")

    title = _field(result, "title")
    assert title.status is ComparisonStatus.NEW
    assert title.new_value == "Chief Executive Officer"


def test_exact_field_conflict_dedup_uses_exact_normalizer() -> None:
    record = make_existing_record()
    observations = [
        make_observation("email", "Ada@Acme.com"),
        make_observation("email", "ada@acme.com"),
    ]

    result = _engine().compare(record, observations, "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.NEW


def test_company_field_is_missing_when_no_company_observation_given() -> None:
    record = make_existing_record({fc.COMPANY_NAME: "Acme Corp"})

    result = _engine().compare(
        record, [make_observation("full_name", "Ada Lovelace")], "row:1"
    )

    company = _field(result, "company")
    assert company.status is ComparisonStatus.MISSING


def test_company_field_detects_a_changed_company_name() -> None:
    record = make_existing_record({fc.COMPANY_NAME: "Acme Corp"})

    result = _engine().compare(
        record, [make_observation("company_name", "Globex Inc")], "row:1"
    )

    company = _field(result, "company")
    assert company.status is ComparisonStatus.CHANGED
    assert company.new_value == "Globex Inc"


def test_company_field_matches_an_unchanged_company_name() -> None:
    record = make_existing_record({fc.COMPANY_NAME: "Acme Corp"})

    result = _engine().compare(
        record, [make_observation("company_name", "Acme Corp")], "row:1"
    )

    company = _field(result, "company")
    assert company.status is ComparisonStatus.MATCH


def test_field_comparisons_follow_profile_order() -> None:
    record = make_existing_record()

    result = _engine().compare(record, [], "row:1")

    assert [c.field_name for c in result.field_comparisons] == [
        "name",
        "title",
        "company",
        "email",
        "phone",
    ]


def test_summary_counts_match_field_statuses() -> None:
    record = make_existing_record(
        {
            fc.FIRST_NAME: "Ada",
            fc.LAST_NAME: "Lovelace",
            fc.PRIMARY_EMAIL: "ada@acme.com",
            fc.COMPANY_NAME: "Acme Corp",
        }
    )
    observations = [
        make_observation("full_name", "Ada Lovelace"),  # MATCH
        make_observation("email", "grace@acme.com"),  # CHANGED
        make_observation("title", "CEO"),  # NEW (existing title absent)
        make_observation("phone", "+15551111111"),  # two distinct values -> CONFLICT
        make_observation("phone", "+15552222222"),
    ]

    result = _engine().compare(record, observations, "row:1")

    summary = result.summary
    assert summary.fields_matched == 1  # name
    assert summary.fields_changed == 1  # email
    assert summary.fields_new == 1  # title
    assert summary.fields_conflict == 1  # phone
    assert summary.fields_missing == 1  # company
    assert summary.fields_unknown == 0
    assert summary.total_fields == 5
    assert summary.compared_at == fixed_clock()


def test_confidence_is_one_when_nothing_is_unknown_or_conflicted() -> None:
    record = make_existing_record({fc.PRIMARY_EMAIL: "ada@acme.com"})
    observations = [make_observation("email", "ada@acme.com")]
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule("email", ("email",), ComparisonStrategy.EXACT),
        ),
    )

    result = _engine(profile).compare(record, observations, "row:1")

    assert result.summary.confidence == 1.0


def test_confidence_excludes_unknown_fields_from_denominator() -> None:
    record = make_existing_record()  # everything absent -> all UNKNOWN
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule("email", ("email",), ComparisonStrategy.EXACT),
        ),
    )

    result = _engine(profile).compare(record, [], "row:1")

    assert result.summary.fields_unknown == 1
    assert result.summary.confidence == 0.0


def test_confidence_is_reduced_by_conflicts() -> None:
    record = make_existing_record()
    observations = [
        make_observation("title", "CEO"),
        make_observation("title", "President"),
    ]
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule(
                "email", ("email",), ComparisonStrategy.EXACT
            ),  # UNKNOWN
            ComparisonFieldRule(
                "title", ("title",), ComparisonStrategy.FUZZY
            ),  # CONFLICT
        ),
    )

    result = _engine(profile).compare(record, observations, "row:1")

    # 1 comparable field (title; email is UNKNOWN and excluded), 0 clean verdicts.
    assert result.summary.confidence == 0.0


def test_invalid_profile_raises_before_any_field_is_compared() -> None:
    invalid_profile = ComparisonProfile(name="broken", field_rules=())
    engine = _engine(invalid_profile)
    record = make_existing_record()

    with pytest.raises(InvalidComparisonConfigurationError):
        engine.compare(record, [], "row:1")


def test_engine_is_deterministic_given_the_same_inputs() -> None:
    record = make_existing_record(
        {
            fc.FIRST_NAME: "Ada",
            fc.LAST_NAME: "Lovelace",
            fc.PRIMARY_EMAIL: "ada@acme.com",
        }
    )
    observations = [
        make_observation("full_name", "Ada Lovelace"),
        make_observation("email", "grace@acme.com"),
    ]

    result_a = _engine().compare(record, observations, "row:1")
    result_b = _engine().compare(record, observations, "row:1")

    assert result_a == result_b


def test_observations_for_unrelated_attributes_are_ignored() -> None:
    record = make_existing_record({fc.PRIMARY_EMAIL: "ada@acme.com"})
    observations = [
        make_observation("biography", "A long biography text that is irrelevant.")
    ]

    result = _engine().compare(record, observations, "row:1")

    email = _field(result, "email")
    assert email.status is ComparisonStatus.MISSING
