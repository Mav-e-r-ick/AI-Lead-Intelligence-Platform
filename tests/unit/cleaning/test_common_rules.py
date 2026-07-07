"""Unit tests for the generic, reusable rule base classes in
application/cleaning/rules/common.py — since most CLN-### rules are thin
instantiations of these, testing the generics thoroughly covers most of
the registry's actual logic in one place.
"""

from __future__ import annotations

import re

from lead_intelligence.application.cleaning.config import CleaningProfile, RuleOverride
from lead_intelligence.application.cleaning.rules.common import (
    AllFieldsAbsentWarningRule,
    BooleanRepresentationNormalizationRule,
    CrossFieldGreaterThanWarningRule,
    DigitCountWarningRule,
    FieldPresentWarningRule,
    IdenticalFieldsWarningRule,
    MissingFieldWarningRuleSet,
    MissingValueRepresentationRule,
    NegativeValueWarningRule,
    PairedFieldsConsistencyWarningRule,
    PassthroughRule,
    PresenceConsistencyWarningRule,
    PrimarySelectionRule,
    ReferenceTableMembershipWarningRule,
    ReferenceTableStandardizationRule,
    RegexShapeWarningRule,
    ThresholdWarningRule,
    WhitespaceNormalizationRule,
    WhitespaceOnlyTrimRule,
)
from lead_intelligence.application.ports.cleaning_rule_port import RuleCategory

_CAT = RuleCategory.METADATA
_PROFILE = CleaningProfile(name="test")


def test_whitespace_normalization_trims_collapses_and_strips_artifact() -> None:
    rule = WhitespaceNormalizationRule(
        "CLN-T1", "t", _CAT, ("a",), artifact_pattern=re.compile(r"^'+")
    )
    # The artifact marker is always the literal first character (Excel's
    # own force-text convention never puts whitespace before it).
    assert rule.apply({"a": "'+1 949  722 3647  "}, _PROFILE) == {
        "a": "+1 949 722 3647"
    }


def test_whitespace_normalization_removes_all_whitespace_when_configured() -> None:
    rule = WhitespaceNormalizationRule(
        "CLN-T2", "t", _CAT, ("a",), remove_internal_whitespace=True
    )
    assert rule.apply({"a": " a b @c .com "}, _PROFILE) == {"a": "ab@c.com"}


def test_whitespace_normalization_no_op_when_already_clean() -> None:
    rule = WhitespaceNormalizationRule("CLN-T3", "t", _CAT, ("a",))
    assert rule.apply({"a": "Clean"}, _PROFILE) == {}


def test_whitespace_only_trim_never_touches_internal_characters() -> None:
    rule = WhitespaceOnlyTrimRule("CLN-T4", "t", _CAT, ("duns",))
    assert rule.apply({"duns": " 036611498 "}, _PROFILE) == {"duns": "036611498"}
    assert rule.apply({"duns": "036611498"}, _PROFILE) == {}


def test_missing_value_representation_normalizes_sentinel_to_none() -> None:
    rule = MissingValueRepresentationRule(
        "CLN-T5", "t", _CAT, ("a",), sentinels=frozenset({""})
    )
    assert rule.apply({"a": ""}, _PROFILE) == {"a": None}
    assert rule.apply({"a": "real value"}, _PROFILE) == {}


def test_passthrough_rule_never_changes_anything() -> None:
    rule = PassthroughRule("CLN-T6", "t", _CAT, ("a", "b"))
    assert rule.apply({"a": 1, "b": 2}, _PROFILE) == {}


def test_boolean_representation_normalization_maps_known_strings() -> None:
    rule = BooleanRepresentationNormalizationRule("CLN-T7", "t", _CAT, ("flag",))
    assert rule.apply({"flag": "Y"}, _PROFILE) == {"flag": True}
    assert rule.apply({"flag": "n"}, _PROFILE) == {"flag": False}
    assert rule.apply({"flag": True}, _PROFILE) == {}
    assert rule.apply({"flag": "maybe"}, _PROFILE) == {}


def test_primary_selection_picks_first_populated_in_priority_order() -> None:
    rule = PrimarySelectionRule("CLN-T8", "t", _CAT, ("a", "b"), "primary")
    assert rule.apply({"a": None, "b": "value"}, _PROFILE) == {"primary": "value"}
    assert rule.apply({"a": "first", "b": "second"}, _PROFILE) == {"primary": "first"}


def test_primary_selection_never_removes_source_fields() -> None:
    rule = PrimarySelectionRule("CLN-T9", "t", _CAT, ("a", "b"), "primary")
    result = rule.apply({"a": "first", "b": "second"}, _PROFILE)
    assert "a" not in result and "b" not in result


def test_missing_field_warning_rule_set_fires_independently_per_field() -> None:
    rule = MissingFieldWarningRuleSet(
        "CLN-T10",
        "t",
        _CAT,
        (("a", "MISSING_A", "a missing"), ("b", "MISSING_B", "b missing")),
    )
    warnings = rule.apply({"a": None, "b": "present"}, _PROFILE)
    assert [w.code for w in warnings] == ["MISSING_A"]


def test_all_fields_absent_warning_requires_every_field_absent() -> None:
    rule = AllFieldsAbsentWarningRule("CLN-T11", "t", _CAT, ("a", "b"), "CODE", "msg")
    assert rule.apply({"a": None, "b": None}, _PROFILE) != []
    assert rule.apply({"a": "x", "b": None}, _PROFILE) == []


def test_field_present_warning_fires_only_when_populated() -> None:
    rule = FieldPresentWarningRule("CLN-T12", "t", _CAT, "a", "CODE", "msg")
    assert rule.apply({"a": "x"}, _PROFILE) != []
    assert rule.apply({"a": None}, _PROFILE) == []


def test_identical_fields_warning_handles_single_and_concatenated_left_side() -> None:
    single = IdenticalFieldsWarningRule(
        "CLN-T13", "t", _CAT, ("a",), "b", "CODE", "msg"
    )
    assert single.apply({"a": "Taylor", "b": "taylor"}, _PROFILE) != []

    concat = IdenticalFieldsWarningRule(
        "CLN-T14", "t", _CAT, ("first", "last"), "company", "CODE", "msg"
    )
    assert (
        concat.apply(
            {"first": "Acme", "last": "Corp", "company": "Acme Corp"}, _PROFILE
        )
        != []
    )
    assert (
        concat.apply(
            {"first": "Ada", "last": "Lovelace", "company": "Acme Corp"}, _PROFILE
        )
        == []
    )


def test_threshold_warning_rule_gt_and_lt() -> None:
    too_long = ThresholdWarningRule(
        "CLN-T15", "t", _CAT, "title", 5, "gt", "LONG", "{length}/{threshold}"
    )
    assert too_long.apply({"title": "x" * 10}, _PROFILE) != []
    assert too_long.apply({"title": "x" * 3}, _PROFILE) == []

    too_short = ThresholdWarningRule(
        "CLN-T16", "t", _CAT, "desc", 5, "lt", "SHORT", "{length}/{threshold}"
    )
    assert too_short.apply({"desc": "hi"}, _PROFILE) != []
    assert too_short.apply({"desc": "long enough"}, _PROFILE) == []


def test_threshold_warning_rule_respects_profile_override() -> None:
    rule = ThresholdWarningRule(
        "CLN-T17", "t", _CAT, "title", 100, "gt", "LONG", "{length}/{threshold}"
    )
    profile = CleaningProfile(
        name="t", rule_overrides={"CLN-T17": RuleOverride(parameters={"threshold": 3})}
    )
    assert rule.apply({"title": "abcdef"}, profile) != []


def test_digit_count_warning_rule() -> None:
    rule = DigitCountWarningRule(
        "CLN-T18", "t", _CAT, ("phone",), 7, "CODE", "{digit_count}/{min_digits}"
    )
    assert rule.apply({"phone": "+19497223647"}, _PROFILE) == []
    assert rule.apply({"phone": "555-12"}, _PROFILE) != []


def test_regex_shape_warning_rule_match_and_invert() -> None:
    has_letters = RegexShapeWarningRule(
        "CLN-T19", "t", _CAT, ("phone",), re.compile(r"[A-Za-z]"), False, "CODE", "msg"
    )
    assert has_letters.apply({"phone": "1-800-FLOWERS"}, _PROFILE) != []
    assert has_letters.apply({"phone": "19497223647"}, _PROFILE) == []

    nine_digits = RegexShapeWarningRule(
        "CLN-T20", "t", _CAT, ("duns",), re.compile(r"^\d{9}$"), True, "CODE", "msg"
    )
    assert nine_digits.apply({"duns": "036611498"}, _PROFILE) == []
    assert nine_digits.apply({"duns": "36611498"}, _PROFILE) != []


def test_negative_value_warning_only_checks_configured_fields() -> None:
    rule = NegativeValueWarningRule(
        "CLN-T21", "t", _CAT, ("sales",), "CODE", "{field}={value}"
    )
    assert rule.apply({"sales": -100, "profit": -999999}, _PROFILE) != []
    assert rule.apply({"sales": 100, "profit": -999999}, _PROFILE) == []


def test_cross_field_greater_than_warning() -> None:
    rule = CrossFieldGreaterThanWarningRule(
        "CLN-T22", "t", _CAT, "single_site", "total", "CODE", "msg"
    )
    assert rule.apply({"single_site": 500, "total": 100}, _PROFILE) != []
    assert rule.apply({"single_site": 50, "total": 100}, _PROFILE) == []


def test_presence_consistency_warning_any_any() -> None:
    rule = PresenceConsistencyWarningRule(
        "CLN-T23", "t", _CAT, ("assets",), "any", ("sales",), "any", "CODE", "msg"
    )
    assert rule.apply({"assets": 100, "sales": None}, _PROFILE) != []
    assert rule.apply({"assets": 100, "sales": 500}, _PROFILE) == []
    assert rule.apply({"assets": None, "sales": None}, _PROFILE) == []


def test_paired_fields_consistency_warning_fires_per_incomplete_pair() -> None:
    rule = PairedFieldsConsistencyWarningRule(
        "CLN-T24",
        "t",
        _CAT,
        (("code_a", "desc_a"), ("code_b", "desc_b")),
        "CODE",
        "{field_a}/{field_b}",
    )
    warnings = rule.apply(
        {"code_a": "123", "desc_a": None, "code_b": "x", "desc_b": "y"}, _PROFILE
    )
    assert len(warnings) == 1
    assert warnings[0].field_names == ("code_a", "desc_a")


def test_reference_table_membership_warning_skips_unconfigured_fields() -> None:
    rule = ReferenceTableMembershipWarningRule(
        "CLN-T25",
        "t",
        _CAT,
        {"naics": frozenset({"311111"})},
        "CODE",
        "{field}={value}",
    )
    assert rule.apply({"naics": "999999"}, _PROFILE) != []
    assert rule.apply({"naics": "311111"}, _PROFILE) == []
    assert rule.apply({"other_code": "999999"}, _PROFILE) == []


def test_reference_table_standardization_maps_both_directions() -> None:
    rule = ReferenceTableStandardizationRule(
        "CLN-T26", "t", _CAT, "state", {"california": "CA"}, {"CA": "California"}
    )
    abbreviation_profile = CleaningProfile(
        name="t",
        rule_overrides={
            "CLN-T26": RuleOverride(enabled=True, parameters={"target": "abbreviation"})
        },
    )
    assert rule.apply({"state": "California"}, abbreviation_profile) == {"state": "CA"}

    full_name_profile = CleaningProfile(
        name="t",
        rule_overrides={
            "CLN-T26": RuleOverride(enabled=True, parameters={"target": "full_name"})
        },
    )
    assert rule.apply({"state": "CA"}, full_name_profile) == {"state": "California"}


def test_reference_table_standardization_leaves_unmapped_value_unchanged() -> None:
    rule = ReferenceTableStandardizationRule("CLN-T27", "t", _CAT, "state", {}, {})
    assert rule.apply({"state": "Nowhere"}, _PROFILE) == {}
