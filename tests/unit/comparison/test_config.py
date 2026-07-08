"""Unit tests for ComparisonFieldRule / ComparisonProfile."""

from __future__ import annotations

import pytest

from lead_intelligence.application.comparison.config import (
    ComparisonFieldRule,
    ComparisonProfile,
    default_profile,
)
from lead_intelligence.application.dto.comparison_models import ComparisonStrategy
from lead_intelligence.domain.exceptions import InvalidComparisonConfigurationError


def test_default_profile_validates_cleanly() -> None:
    default_profile().validate()


def test_default_profile_covers_the_five_required_fields() -> None:
    field_names = {rule.field_name for rule in default_profile().field_rules}

    assert field_names == {"name", "title", "company", "email", "phone"}


def test_empty_field_rules_is_invalid() -> None:
    profile = ComparisonProfile(name="t", field_rules=())

    with pytest.raises(InvalidComparisonConfigurationError):
        profile.validate()


def test_duplicate_field_name_is_invalid() -> None:
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule("name", (), ComparisonStrategy.FUZZY),
            ComparisonFieldRule("name", (), ComparisonStrategy.EXACT),
        ),
    )

    with pytest.raises(InvalidComparisonConfigurationError):
        profile.validate()


def test_unknown_field_name_with_no_resolver_is_invalid() -> None:
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule("not_a_real_field", (), ComparisonStrategy.EXACT),
        ),
    )

    with pytest.raises(InvalidComparisonConfigurationError):
        profile.validate()


def test_fuzzy_threshold_above_one_is_invalid() -> None:
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule(
                "name", (), ComparisonStrategy.FUZZY, fuzzy_threshold=1.5
            ),
        ),
    )

    with pytest.raises(InvalidComparisonConfigurationError):
        profile.validate()


def test_fuzzy_threshold_below_zero_is_invalid() -> None:
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule(
                "name", (), ComparisonStrategy.FUZZY, fuzzy_threshold=-0.1
            ),
        ),
    )

    with pytest.raises(InvalidComparisonConfigurationError):
        profile.validate()


def test_exact_field_ignores_out_of_range_fuzzy_threshold() -> None:
    # fuzzy_threshold is irrelevant for EXACT fields, so an out-of-range
    # value there must not fail validation.
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule(
                "email", (), ComparisonStrategy.EXACT, fuzzy_threshold=9.0
            ),
        ),
    )

    profile.validate()


def test_custom_profile_can_narrow_the_field_set() -> None:
    profile = ComparisonProfile(
        name="t",
        field_rules=(
            ComparisonFieldRule("email", ("email",), ComparisonStrategy.EXACT),
        ),
    )

    profile.validate()
    assert len(profile.field_rules) == 1
