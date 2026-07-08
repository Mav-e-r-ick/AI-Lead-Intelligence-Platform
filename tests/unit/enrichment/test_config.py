"""Unit tests for RefreshPolicy / ProviderConfiguration / EnrichmentProfile."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.application.enrichment.config import (
    EnrichmentProfile,
    ProviderConfiguration,
    RefreshPolicy,
    default_profile,
)
from lead_intelligence.domain.exceptions import InvalidEnrichmentConfigurationError


def _now() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_default_profile_validates_cleanly() -> None:
    default_profile().validate()


def test_refresh_policy_is_due_when_never_fetched() -> None:
    policy = RefreshPolicy(max_age=timedelta(days=30))

    assert policy.should_refresh(None, _now()) is True


def test_refresh_policy_is_not_due_when_recently_fetched() -> None:
    policy = RefreshPolicy(max_age=timedelta(days=30))
    last_fetched = _now() - timedelta(days=1)

    assert policy.should_refresh(last_fetched, _now()) is False


def test_refresh_policy_is_due_once_max_age_elapsed() -> None:
    policy = RefreshPolicy(max_age=timedelta(days=30))
    last_fetched = _now() - timedelta(days=31)

    assert policy.should_refresh(last_fetched, _now()) is True


def test_refresh_policy_boundary_is_inclusive() -> None:
    policy = RefreshPolicy(max_age=timedelta(days=30))
    last_fetched = _now() - timedelta(days=30)

    assert policy.should_refresh(last_fetched, _now()) is True


def test_provider_configuration_parameters_are_immutable() -> None:
    configuration = ProviderConfiguration(parameters={"a": 1})

    with pytest.raises(TypeError):
        configuration.parameters["b"] = 2  # type: ignore[index]


def test_profile_configuration_for_falls_back_to_default() -> None:
    default_configuration = ProviderConfiguration(priority=ProviderPriority.LOW)
    profile = EnrichmentProfile(name="t", default_configuration=default_configuration)

    assert profile.configuration_for("unregistered_provider") is default_configuration


def test_profile_configuration_for_returns_explicit_entry_when_present() -> None:
    explicit = ProviderConfiguration(priority=ProviderPriority.CRITICAL)
    profile = EnrichmentProfile(name="t", provider_configurations={"dnb": explicit})

    assert profile.configuration_for("dnb") is explicit
    assert profile.configuration_for("news") is profile.default_configuration


def test_is_enabled_reflects_configuration() -> None:
    profile = EnrichmentProfile(
        name="t", provider_configurations={"news": ProviderConfiguration(enabled=False)}
    )

    assert profile.is_enabled("news") is False
    assert profile.is_enabled("unregistered_provider") is True


def test_validate_rejects_non_positive_timeout_on_explicit_configuration() -> None:
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={"news": ProviderConfiguration(timeout_seconds=0)},
    )

    with pytest.raises(InvalidEnrichmentConfigurationError):
        profile.validate()


def test_validate_rejects_non_positive_timeout_on_default_configuration() -> None:
    profile = EnrichmentProfile(
        name="t", default_configuration=ProviderConfiguration(timeout_seconds=-1)
    )

    with pytest.raises(InvalidEnrichmentConfigurationError):
        profile.validate()


def test_validate_rejects_negative_refresh_max_age() -> None:
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={
            "news": ProviderConfiguration(
                refresh_policy=RefreshPolicy(max_age=timedelta(days=-1))
            )
        },
    )

    with pytest.raises(InvalidEnrichmentConfigurationError):
        profile.validate()


def test_provider_configurations_mapping_is_immutable() -> None:
    profile = default_profile()

    with pytest.raises(TypeError):
        profile.provider_configurations["news"] = ProviderConfiguration()  # type: ignore[index]
