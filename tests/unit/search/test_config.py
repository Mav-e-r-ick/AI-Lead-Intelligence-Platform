"""Unit tests for SearchProviderConfiguration / SearchProfile."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.application.search.config import (
    SearchProfile,
    SearchProviderConfiguration,
    default_profile,
)
from lead_intelligence.domain.exceptions import InvalidSearchConfigurationError


def test_default_profile_validates_cleanly() -> None:
    default_profile().validate()


def test_provider_configuration_parameters_are_immutable() -> None:
    configuration = SearchProviderConfiguration(parameters={"a": 1})

    with pytest.raises(TypeError):
        configuration.parameters["b"] = 2  # type: ignore[index]


def test_profile_configuration_for_falls_back_to_default() -> None:
    default_configuration = SearchProviderConfiguration(priority=ProviderPriority.LOW)
    profile = SearchProfile(name="t", default_configuration=default_configuration)

    assert profile.configuration_for("unregistered_provider") is default_configuration


def test_profile_configuration_for_returns_explicit_entry_when_present() -> None:
    explicit = SearchProviderConfiguration(priority=ProviderPriority.CRITICAL)
    profile = SearchProfile(
        name="t", provider_configurations={"browser_search": explicit}
    )

    assert profile.configuration_for("browser_search") is explicit
    assert profile.configuration_for("google_search") is profile.default_configuration


def test_is_enabled_reflects_configuration() -> None:
    profile = SearchProfile(
        name="t",
        provider_configurations={
            "browser_search": SearchProviderConfiguration(enabled=False)
        },
    )

    assert profile.is_enabled("browser_search") is False
    assert profile.is_enabled("unregistered_provider") is True


def test_validate_rejects_non_positive_timeout_on_explicit_configuration() -> None:
    profile = SearchProfile(
        name="t",
        provider_configurations={
            "browser_search": SearchProviderConfiguration(timeout_seconds=0)
        },
    )

    with pytest.raises(InvalidSearchConfigurationError):
        profile.validate()


def test_validate_rejects_non_positive_timeout_on_default_configuration() -> None:
    profile = SearchProfile(
        name="t",
        default_configuration=SearchProviderConfiguration(timeout_seconds=-1),
    )

    with pytest.raises(InvalidSearchConfigurationError):
        profile.validate()


def test_provider_configurations_mapping_is_immutable() -> None:
    profile = default_profile()

    with pytest.raises(TypeError):
        profile.provider_configurations["browser_search"] = (  # type: ignore[index]
            SearchProviderConfiguration()
        )
