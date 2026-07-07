"""Unit tests for CleaningProfile / RuleOverride."""

from __future__ import annotations

import pytest

from lead_intelligence.application.cleaning.config import (
    CleaningProfile,
    RuleOverride,
    default_profile,
)
from lead_intelligence.application.ports.cleaning_rule_port import (
    RuleCategory,
    RuleMetadata,
    RuleStage,
)
from lead_intelligence.domain.exceptions import InvalidCleaningConfigurationError


def _metadata(stage: RuleStage, default_enabled: bool = True) -> RuleMetadata:
    return RuleMetadata(
        rule_id="CLN-999",
        name="Test Rule",
        category=RuleCategory.METADATA,
        stage=stage,
        fields=("x",),
        default_enabled=default_enabled,
    )


def test_safe_stage_rule_is_always_enabled_regardless_of_overrides() -> None:
    profile = CleaningProfile(
        name="t", rule_overrides={"CLN-999": RuleOverride(enabled=False)}
    )
    assert profile.is_enabled(_metadata(RuleStage.SAFE)) is True


def test_business_rule_uses_its_own_default_when_no_override_present() -> None:
    profile = CleaningProfile(name="t")
    assert (
        profile.is_enabled(_metadata(RuleStage.BUSINESS, default_enabled=False))
        is False
    )
    assert (
        profile.is_enabled(_metadata(RuleStage.BUSINESS, default_enabled=True)) is True
    )


def test_explicit_override_wins_over_default() -> None:
    profile = CleaningProfile(
        name="t", rule_overrides={"CLN-999": RuleOverride(enabled=True)}
    )
    assert (
        profile.is_enabled(_metadata(RuleStage.BUSINESS, default_enabled=False)) is True
    )


def test_parameters_for_returns_empty_mapping_when_no_override() -> None:
    profile = CleaningProfile(name="t")
    assert dict(profile.parameters_for("CLN-999")) == {}


def test_parameters_for_returns_configured_parameters() -> None:
    profile = CleaningProfile(
        name="t",
        rule_overrides={"CLN-999": RuleOverride(parameters={"threshold": 42})},
    )
    assert profile.parameters_for("CLN-999")["threshold"] == 42


def test_validate_raises_on_empty_field_mapping() -> None:
    profile = CleaningProfile(name="t", field_mapping={})
    with pytest.raises(InvalidCleaningConfigurationError):
        profile.validate()


def test_default_profile_validates_successfully() -> None:
    default_profile().validate()  # should not raise


def test_field_mapping_and_overrides_are_immutable() -> None:
    profile = CleaningProfile(name="t")
    with pytest.raises(TypeError):
        profile.field_mapping["x"] = "y"  # type: ignore[index]
