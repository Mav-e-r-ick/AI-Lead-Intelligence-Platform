"""Unit tests for NewsProviderSettings and site_restriction_clause."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.search.google.settings import (
    GOOGLE_SEARCH_API_KEY_ENV_VAR,
    GOOGLE_SEARCH_ENGINE_ID_ENV_VAR,
)
from lead_intelligence.infrastructure.search.news.settings import (
    NewsProviderSettings,
    TRUSTED_NEWS_DOMAINS,
    site_restriction_clause,
)


def _settings(**overrides: object) -> NewsProviderSettings:
    base = {"api_key": "key", "search_engine_id": "cx"}
    base.update(overrides)
    return NewsProviderSettings(**base)  # type: ignore[arg-type]


def test_defaults_pass_validation() -> None:
    _settings().validate()


def test_blank_api_key_raises() -> None:
    with pytest.raises(ValueError, match="api_key"):
        _settings(api_key="").validate()


def test_empty_trusted_domains_raises() -> None:
    with pytest.raises(ValueError, match="trusted_domains"):
        _settings(trusted_domains=()).validate()


def test_empty_query_templates_raises() -> None:
    with pytest.raises(ValueError, match="query_templates"):
        _settings(query_templates=()).validate()


def test_trusted_news_domains_includes_every_outlet_this_task_names() -> None:
    assert TRUSTED_NEWS_DOMAINS == (
        "reuters.com",
        "bloomberg.com",
        "finance.yahoo.com",
        "businesswire.com",
        "prnewswire.com",
        "globenewswire.com",
    )


def test_site_restriction_clause_joins_domains_with_or() -> None:
    clause = site_restriction_clause(("a.com", "b.com"))

    assert clause == "(site:a.com OR site:b.com)"


def test_from_env_reads_the_shared_google_search_variables() -> None:
    env = {
        GOOGLE_SEARCH_API_KEY_ENV_VAR: "env-key",
        GOOGLE_SEARCH_ENGINE_ID_ENV_VAR: "env-cx",
    }
    settings = NewsProviderSettings.from_env(env)

    assert settings.api_key == "env-key"
    assert settings.search_engine_id == "env-cx"
