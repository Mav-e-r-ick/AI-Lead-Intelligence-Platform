"""Unit tests for BrowserSearchProviderSettings."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)
from tests.unit.browser_search.fixtures import build_settings


def test_valid_settings_pass_validation() -> None:
    build_settings().validate()


def test_blank_search_url_template_raises() -> None:
    with pytest.raises(ValueError, match="search_url_template"):
        build_settings(search_url_template="").validate()


def test_search_url_template_missing_query_placeholder_raises() -> None:
    with pytest.raises(ValueError, match="query"):
        build_settings(
            search_url_template="https://search.example.org/search?q=fixed"
        ).validate()


def test_blank_result_container_selector_raises() -> None:
    with pytest.raises(ValueError, match="result_container_selector"):
        build_settings(result_container_selector="").validate()


def test_blank_title_selector_raises() -> None:
    with pytest.raises(ValueError, match="title_selector"):
        build_settings(title_selector="").validate()


def test_blank_url_selector_raises() -> None:
    with pytest.raises(ValueError, match="url_selector"):
        build_settings(url_selector="").validate()


def test_blank_user_data_dir_raises() -> None:
    with pytest.raises(ValueError, match="user_data_dir"):
        build_settings(user_data_dir="").validate()


def test_blank_snippet_selector_is_allowed() -> None:
    build_settings(snippet_selector="").validate()


def test_non_positive_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_settings(timeout_seconds=0).validate()


def test_negative_max_retries_raises() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        build_settings(max_retries=-1).validate()


def test_negative_retry_backoff_raises() -> None:
    with pytest.raises(ValueError, match="retry_backoff_seconds"):
        build_settings(retry_backoff_seconds=-1).validate()


def test_max_results_below_one_raises() -> None:
    with pytest.raises(ValueError, match="max_results"):
        build_settings(max_results=0).validate()


def test_empty_query_templates_raises() -> None:
    with pytest.raises(ValueError, match="query_templates"):
        build_settings(query_templates=()).validate()


def test_default_headless_is_true() -> None:
    assert build_settings().headless is True


def test_from_env_reads_every_variable() -> None:
    env = {
        "BROWSER_SEARCH_URL_TEMPLATE": "https://x.example/search?q={query}",
        "BROWSER_SEARCH_RESULT_SELECTOR": ".res",
        "BROWSER_SEARCH_TITLE_SELECTOR": ".title",
        "BROWSER_SEARCH_URL_SELECTOR": "a.link",
        "BROWSER_SEARCH_USER_DATA_DIR": "/home/user/chrome-profile",
        "BROWSER_SEARCH_SNIPPET_SELECTOR": ".snippet",
        "BROWSER_SEARCH_MAX_RESULTS": "5",
        "BROWSER_SEARCH_HEADLESS": "false",
        "BROWSER_SEARCH_EXECUTABLE_PATH": "/opt/chromium/chrome",
    }

    settings = BrowserSearchProviderSettings.from_env(env)

    assert settings.search_url_template == "https://x.example/search?q={query}"
    assert settings.result_container_selector == ".res"
    assert settings.title_selector == ".title"
    assert settings.url_selector == "a.link"
    assert settings.user_data_dir == "/home/user/chrome-profile"
    assert settings.snippet_selector == ".snippet"
    assert settings.max_results == 5
    assert settings.headless is False
    assert settings.executable_path == "/opt/chromium/chrome"


def test_from_env_missing_variables_yields_blank_fields_that_fail_validate() -> None:
    settings = BrowserSearchProviderSettings.from_env({})

    with pytest.raises(ValueError):
        settings.validate()


def test_from_env_headless_defaults_to_true_when_unset() -> None:
    settings = BrowserSearchProviderSettings.from_env(
        {
            "BROWSER_SEARCH_URL_TEMPLATE": "https://x.example/search?q={query}",
            "BROWSER_SEARCH_RESULT_SELECTOR": ".res",
            "BROWSER_SEARCH_TITLE_SELECTOR": ".title",
            "BROWSER_SEARCH_URL_SELECTOR": "a",
        }
    )

    assert settings.headless is True


def test_from_env_accepts_overrides() -> None:
    settings = BrowserSearchProviderSettings.from_env(
        {
            "BROWSER_SEARCH_URL_TEMPLATE": "https://x.example/search?q={query}",
            "BROWSER_SEARCH_RESULT_SELECTOR": ".res",
            "BROWSER_SEARCH_TITLE_SELECTOR": ".title",
            "BROWSER_SEARCH_URL_SELECTOR": "a",
        },
        max_results=3,
    )

    assert settings.max_results == 3


def test_query_templates_default_to_the_shared_google_search_defaults() -> None:
    from lead_intelligence.infrastructure.enrichment.google_search.settings import (
        DEFAULT_QUERY_TEMPLATES,
    )

    assert build_settings().query_templates == DEFAULT_QUERY_TEMPLATES
