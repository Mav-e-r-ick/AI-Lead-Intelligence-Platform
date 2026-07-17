"""Unit tests for LinkedInSearchProviderSettings."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.search.google.settings import (
    GOOGLE_SEARCH_API_KEY_ENV_VAR,
    GOOGLE_SEARCH_ENGINE_ID_ENV_VAR,
)
from lead_intelligence.infrastructure.search.linkedin.settings import (
    LinkedInSearchProviderSettings,
)


def _settings(**overrides: object) -> LinkedInSearchProviderSettings:
    base = {"api_key": "key", "search_engine_id": "cx"}
    base.update(overrides)
    return LinkedInSearchProviderSettings(**base)  # type: ignore[arg-type]


def test_defaults_pass_validation() -> None:
    _settings().validate()


def test_blank_api_key_raises() -> None:
    with pytest.raises(ValueError, match="api_key"):
        _settings(api_key="").validate()


def test_max_results_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="max_results"):
        _settings(max_results=0).validate()


def test_empty_query_templates_raises() -> None:
    with pytest.raises(ValueError, match="query_templates"):
        _settings(query_templates=()).validate()


def test_from_env_reads_the_shared_google_search_variables() -> None:
    env = {
        GOOGLE_SEARCH_API_KEY_ENV_VAR: "env-key",
        GOOGLE_SEARCH_ENGINE_ID_ENV_VAR: "env-cx",
    }
    settings = LinkedInSearchProviderSettings.from_env(env)

    assert settings.api_key == "env-key"
    assert settings.search_engine_id == "env-cx"
