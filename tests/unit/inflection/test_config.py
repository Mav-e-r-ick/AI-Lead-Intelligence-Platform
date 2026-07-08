"""Tests for InflectionProfile / InflectionRuleOverride."""

from __future__ import annotations

import pytest

from lead_intelligence.application.inflection.config import (
    InflectionProfile,
    InflectionRuleOverride,
    default_profile,
)
from lead_intelligence.application.inflection.rules import PromotionRule
from lead_intelligence.domain.exceptions import InvalidInflectionConfigurationError


class TestInflectionProfile:
    def test_default_profile_enables_every_rule(self) -> None:
        profile = default_profile()
        rule = PromotionRule()

        assert profile.is_enabled(rule) is True
        assert profile.confidence_for(rule) == rule.metadata.base_confidence

    def test_override_can_disable_a_rule(self) -> None:
        rule = PromotionRule()
        profile = InflectionProfile(
            name="test",
            rule_overrides={
                rule.metadata.rule_id: InflectionRuleOverride(enabled=False)
            },
        )

        assert profile.is_enabled(rule) is False

    def test_override_can_replace_base_confidence(self) -> None:
        rule = PromotionRule()
        profile = InflectionProfile(
            name="test",
            rule_overrides={
                rule.metadata.rule_id: InflectionRuleOverride(base_confidence=0.42)
            },
        )

        assert profile.confidence_for(rule) == 0.42

    def test_override_with_no_confidence_falls_back_to_rule_default(self) -> None:
        rule = PromotionRule()
        profile = InflectionProfile(
            name="test",
            rule_overrides={
                rule.metadata.rule_id: InflectionRuleOverride(enabled=False)
            },
        )

        assert profile.confidence_for(rule) == rule.metadata.base_confidence

    def test_validate_passes_for_default_profile(self) -> None:
        default_profile().validate()

    def test_validate_rejects_out_of_range_confidence_override(self) -> None:
        profile = InflectionProfile(
            name="test",
            rule_overrides={"INF-001": InflectionRuleOverride(base_confidence=1.5)},
        )

        with pytest.raises(InvalidInflectionConfigurationError):
            profile.validate()

    def test_validate_rejects_negative_confidence_override(self) -> None:
        profile = InflectionProfile(
            name="test",
            rule_overrides={"INF-001": InflectionRuleOverride(base_confidence=-0.1)},
        )

        with pytest.raises(InvalidInflectionConfigurationError):
            profile.validate()
