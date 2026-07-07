"""Registry-wide consistency checks: every rule in ALL_RULES against the
structural invariants CLEANING_RULES.md promises.

These are not full behavior tests (see test_rules_behavior.py for that) —
they're a cheap, comprehensive sweep that would catch a typo'd Rule ID, a
duplicate, a stage/category mismatch, or an accidental default-enabled flip
across all 68 rules at once.
"""

from __future__ import annotations

import pytest

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.rules import ALL_RULES
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleStage,
)


def test_registry_has_exactly_68_rules() -> None:
    assert len(ALL_RULES) == 68


def test_every_rule_id_is_unique_and_sequential() -> None:
    ids = [rule.metadata.rule_id for rule in ALL_RULES]
    assert len(set(ids)) == len(ids), "duplicate Rule ID found"
    expected = [f"CLN-{i:03d}" for i in range(1, 69)]
    assert ids == expected


@pytest.mark.parametrize("rule", ALL_RULES, ids=[r.metadata.rule_id for r in ALL_RULES])
def test_every_rule_exposes_well_formed_metadata(rule) -> None:
    metadata = rule.metadata
    assert metadata.rule_id.startswith("CLN-")
    assert metadata.name
    assert isinstance(metadata.category, RuleCategory)
    assert isinstance(metadata.stage, RuleStage)
    assert metadata.version >= 1
    for dependency in metadata.dependencies:
        assert dependency.startswith("CLN-")


@pytest.mark.parametrize("rule", ALL_RULES, ids=[r.metadata.rule_id for r in ALL_RULES])
def test_safe_stage_rules_are_never_configurable_and_always_default_enabled(
    rule,
) -> None:
    if rule.metadata.stage == RuleStage.SAFE:
        assert rule.metadata.configurable is False
        assert rule.metadata.default_enabled is True


@pytest.mark.parametrize("rule", ALL_RULES, ids=[r.metadata.rule_id for r in ALL_RULES])
def test_rule_class_matches_its_declared_stage(rule) -> None:
    if rule.metadata.stage == RuleStage.WARNING:
        assert isinstance(rule, QualityCheckRule)
    else:
        assert isinstance(rule, NormalizationRule)


def test_dependency_rule_ids_all_exist_in_the_registry() -> None:
    known_ids = {rule.metadata.rule_id for rule in ALL_RULES}
    for rule in ALL_RULES:
        for dependency in rule.metadata.dependencies:
            assert (
                dependency in known_ids
            ), f"{rule.metadata.rule_id} depends on unknown {dependency}"


def test_cln_048_excludes_pre_tax_profit_and_liabilities() -> None:
    """Direct regression guard for the Part-1-evidenced exclusion: negative
    Pre Tax Profit is legitimate (140 real rows observed) and must never be
    flagged by the blanket negative-value warning.
    """

    rule = next(r for r in ALL_RULES if r.metadata.rule_id == "CLN-048")
    assert F.PRE_TAX_PROFIT_USD not in rule.metadata.fields
    assert F.LIABILITIES_USD not in rule.metadata.fields


@pytest.mark.parametrize(
    "rule_id", ["CLN-016", "CLN-067", "CLN-026", "CLN-027", "CLN-037", "CLN-038"]
)
def test_convention_choice_business_rules_default_off(rule_id: str) -> None:
    """Per CLEANING_RULES.md's Default-Enabled Policy: rules encoding a
    style/convention preference (not fixing an evidenced defect) default off.
    """

    rule = next(r for r in ALL_RULES if r.metadata.rule_id == rule_id)
    assert rule.metadata.default_enabled is False


def test_cln_004_acronym_fix_defaults_on() -> None:
    """CLN-004 fixes a specific, evidenced defect (Crm -> CRM), so per the
    Default-Enabled Policy it defaults on, unlike other Business rules."""

    rule = next(r for r in ALL_RULES if r.metadata.rule_id == "CLN-004")
    assert rule.metadata.default_enabled is True
