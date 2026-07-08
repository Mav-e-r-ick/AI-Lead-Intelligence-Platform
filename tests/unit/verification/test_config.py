"""Tests for VerificationProviderConfiguration / VerificationProfile."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.application.verification.config import (
    VerificationProfile,
    VerificationProviderConfiguration,
    default_profile,
)
from lead_intelligence.domain.exceptions import InvalidVerificationConfigurationError


class TestVerificationProfile:
    def test_unlisted_provider_falls_back_to_default_configuration(self) -> None:
        profile = default_profile()

        configuration = profile.configuration_for("neverbounce")

        assert configuration == VerificationProviderConfiguration()

    def test_is_enabled_true_by_default(self) -> None:
        profile = default_profile()

        assert profile.is_enabled("neverbounce") is True

    def test_is_enabled_respects_explicit_override(self) -> None:
        profile = VerificationProfile(
            name="t",
            provider_configurations={
                "neverbounce": VerificationProviderConfiguration(enabled=False)
            },
        )

        assert profile.is_enabled("neverbounce") is False
        assert profile.is_enabled("zerobounce") is True

    def test_configuration_for_returns_explicit_entry(self) -> None:
        configuration = VerificationProviderConfiguration(
            priority=ProviderPriority.HIGH
        )
        profile = VerificationProfile(
            name="t", provider_configurations={"neverbounce": configuration}
        )

        assert profile.configuration_for("neverbounce") is configuration

    def test_validate_passes_for_default_profile(self) -> None:
        default_profile().validate()

    def test_validate_rejects_non_positive_timeout_on_explicit_configuration(
        self,
    ) -> None:
        profile = VerificationProfile(
            name="broken",
            provider_configurations={
                "neverbounce": VerificationProviderConfiguration(timeout_seconds=0)
            },
        )

        with pytest.raises(InvalidVerificationConfigurationError):
            profile.validate()

    def test_validate_rejects_non_positive_timeout_on_default_configuration(
        self,
    ) -> None:
        profile = VerificationProfile(
            name="broken",
            default_configuration=VerificationProviderConfiguration(timeout_seconds=-1),
        )

        with pytest.raises(InvalidVerificationConfigurationError):
            profile.validate()

    def test_parameters_are_immutable(self) -> None:
        configuration = VerificationProviderConfiguration(parameters={"key": "value"})

        with pytest.raises(TypeError):
            configuration.parameters["key"] = "changed"  # type: ignore[index]
