"""Unit tests for GoogleSearchProviderSettings (Search Layer)."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.search.google.settings import (
    GOOGLE_SEARCH_API_KEY_ENV_VAR,
    GOOGLE_SEARCH_ENGINE_ID_ENV_VAR,
    GoogleSearchProviderSettings,
)


def _settings(**overrides: object) -> GoogleSearchProviderSettings:
    base = {"api_key": "key", "search_engine_id": "cx"}
    base.update(overrides)
    return GoogleSearchProviderSettings(**base)  # type: ignore[arg-type]


def test_defaults_pass_validation() -> None:
    _settings().validate()


def test_blank_api_key_raises() -> None:
    with pytest.raises(ValueError, match="api_key"):
        _settings(api_key="").validate()


def test_blank_search_engine_id_raises() -> None:
    with pytest.raises(ValueError, match="search_engine_id"):
        _settings(search_engine_id="").validate()


def test_non_positive_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        _settings(timeout_seconds=0).validate()


def test_max_results_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="max_results"):
        _settings(max_results=11).validate()


def test_empty_query_templates_raises() -> None:
    with pytest.raises(ValueError, match="query_templates"):
        _settings(query_templates=()).validate()


def test_from_env_reads_the_shared_google_search_variables() -> None:
    env = {
        GOOGLE_SEARCH_API_KEY_ENV_VAR: "env-key",
        GOOGLE_SEARCH_ENGINE_ID_ENV_VAR: "env-cx",
    }
    settings = GoogleSearchProviderSettings.from_env(env)

    assert settings.api_key == "env-key"
    assert settings.search_engine_id == "env-cx"


def test_from_env_accepts_overrides() -> None:
    settings = GoogleSearchProviderSettings.from_env({}, max_results=3)

    assert settings.max_results == 3
