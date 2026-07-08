"""Tests for InflectionRuleRegistry."""

from __future__ import annotations

import pytest

from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES, PromotionRule
from lead_intelligence.domain.exceptions import DuplicateInflectionRuleError


class TestInflectionRuleRegistry:
    def test_registers_every_rule(self) -> None:
        registry = InflectionRuleRegistry(ALL_RULES)

        assert len(registry.all_rules()) == len(ALL_RULES)

    def test_get_returns_registered_rule(self) -> None:
        registry = InflectionRuleRegistry(ALL_RULES)

        rule = registry.get("INF-001")

        assert rule is not None
        assert rule.metadata.rule_id == "INF-001"

    def test_get_returns_none_for_unknown_rule_id(self) -> None:
        registry = InflectionRuleRegistry(ALL_RULES)

        assert registry.get("INF-999") is None

    def test_duplicate_rule_id_raises(self) -> None:
        with pytest.raises(DuplicateInflectionRuleError):
            InflectionRuleRegistry([PromotionRule(), PromotionRule()])
