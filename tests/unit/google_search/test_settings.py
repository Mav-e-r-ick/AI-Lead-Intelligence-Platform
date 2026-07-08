"""Tests for GoogleSearchProviderSettings."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    GOOGLE_SEARCH_API_KEY_ENV_VAR,
    GOOGLE_SEARCH_ENGINE_ID_ENV_VAR,
    GoogleSearchProviderSettings,
)


def _settings(**overrides: object) -> GoogleSearchProviderSettings:
    defaults: dict[str, object] = {"api_key": "key", "search_engine_id": "cx"}
    defaults.update(overrides)
    return GoogleSearchProviderSettings(**defaults)  # type: ignore[arg-type]


class TestGoogleSearchProviderSettingsValidate:
    def test_valid_settings_pass(self) -> None:
        _settings().validate()

    def test_blank_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            _settings(api_key="").validate()

    def test_blank_search_engine_id_raises(self) -> None:
        with pytest.raises(ValueError, match="search_engine_id"):
            _settings(search_engine_id="").validate()

    def test_blank_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="base_url"):
            _settings(base_url=" ").validate()

    def test_non_positive_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds"):
            _settings(timeout_seconds=0).validate()

    def test_negative_max_retries_raises(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):
            _settings(max_retries=-1).validate()

    def test_negative_retry_backoff_raises(self) -> None:
        with pytest.raises(ValueError, match="retry_backoff_seconds"):
            _settings(retry_backoff_seconds=-0.1).validate()

    def test_max_results_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="max_results"):
            _settings(max_results=0).validate()

    def test_max_results_above_ten_raises(self) -> None:
        with pytest.raises(ValueError, match="max_results"):
            _settings(max_results=11).validate()

    def test_max_results_at_bounds_pass(self) -> None:
        _settings(max_results=1).validate()
        _settings(max_results=10).validate()

    def test_negative_cache_ttl_raises(self) -> None:
        with pytest.raises(ValueError, match="cache_ttl"):
            _settings(cache_ttl=timedelta(seconds=-1)).validate()

    def test_empty_query_templates_raises(self) -> None:
        with pytest.raises(ValueError, match="query_templates"):
            _settings(query_templates=()).validate()


class TestGoogleSearchProviderSettingsFromEnv:
    def test_reads_credentials_from_given_mapping(self) -> None:
        settings = GoogleSearchProviderSettings.from_env(
            {
                GOOGLE_SEARCH_API_KEY_ENV_VAR: "abc123",
                GOOGLE_SEARCH_ENGINE_ID_ENV_VAR: "cx-1",
            }
        )

        assert settings.api_key == "abc123"
        assert settings.search_engine_id == "cx-1"

    def test_missing_env_vars_yield_blank_credentials(self) -> None:
        settings = GoogleSearchProviderSettings.from_env({})

        assert settings.api_key == ""
        assert settings.search_engine_id == ""

    def test_accepts_field_overrides(self) -> None:
        settings = GoogleSearchProviderSettings.from_env(
            {
                GOOGLE_SEARCH_API_KEY_ENV_VAR: "abc123",
                GOOGLE_SEARCH_ENGINE_ID_ENV_VAR: "cx-1",
            },
            max_results=3,
        )

        assert settings.max_results == 3

    def test_defaults_to_real_os_environ_when_no_mapping_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(GOOGLE_SEARCH_API_KEY_ENV_VAR, "from-real-env")
        monkeypatch.setenv(GOOGLE_SEARCH_ENGINE_ID_ENV_VAR, "cx-real")

        settings = GoogleSearchProviderSettings.from_env()

        assert settings.api_key == "from-real-env"
        assert settings.search_engine_id == "cx-real"
