"""Unit tests for CompanyWebsiteProviderSettings.validate()."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lead_intelligence.infrastructure.enrichment.company_website.settings import (
    CompanyWebsiteProviderSettings,
)


def test_default_settings_validate_cleanly() -> None:
    CompanyWebsiteProviderSettings().validate()


def test_blank_user_agent_is_invalid() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProviderSettings(user_agent="   ").validate()


def test_non_positive_timeout_is_invalid() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProviderSettings(timeout_seconds=0).validate()


def test_negative_max_retries_is_invalid() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProviderSettings(max_retries=-1).validate()


def test_negative_retry_backoff_is_invalid() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProviderSettings(retry_backoff_seconds=-0.1).validate()


def test_non_positive_max_leadership_pages_is_invalid() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProviderSettings(max_leadership_pages=0).validate()


def test_negative_cache_ttl_is_invalid() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProviderSettings(cache_ttl=timedelta(seconds=-1)).validate()


def test_zero_retries_and_zero_cache_ttl_are_valid_edge_cases() -> None:
    CompanyWebsiteProviderSettings(max_retries=0, cache_ttl=timedelta(0)).validate()
