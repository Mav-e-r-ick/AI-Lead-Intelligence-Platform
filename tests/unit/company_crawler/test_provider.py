"""End-to-end unit tests for CompanyCrawlerProvider.search(), using a fake
Playwright Browser/Page (fixtures.py) and a mocked httpx transport for
robots.txt checks. No test here launches a real browser or touches the
real network."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
from lead_intelligence.infrastructure.search.company_crawler.provider import (
    CompanyCrawlerProvider,
)
from lead_intelligence.infrastructure.search.company_crawler.settings import (
    CompanyCrawlerProviderSettings,
)
from tests.unit.company_crawler.fixtures import (
    FakeBrowser,
    build_http_client,
    build_settings,
    fixed_clock,
    robots_allow_all_transport,
    robots_disallow_all_transport,
    robots_not_found_transport,
)

_HOMEPAGE = """
<html><head><title>Acme Corp</title></head><body>
  <a href="/leadership">Leadership</a>
  <a href="/contact">Contact</a>
</body></html>
"""

_LEADERSHIP_PAGE = """
<html><head><title>Acme Corp Leadership</title>
<meta name="description" content="Meet our executive team.">
</head><body><p>Ada Lovelace is our CEO.</p></body></html>
"""


def _request(known_attributes: dict[str, str] | None = None) -> SearchRequest:
    return SearchRequest(
        request_id="req-1",
        subject_type=SubjectType.PERSON,
        subject_id="row:1",
        known_attributes=(
            known_attributes
            if known_attributes is not None
            else {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "url": "https://acme.com",
            }
        ),
        requested_at=fixed_clock(),
    )


def _provider(
    browser: FakeBrowser,
    settings: CompanyCrawlerProviderSettings | None = None,
    robots_handler: Callable[
        [httpx.Request], httpx.Response
    ] = robots_allow_all_transport,
) -> CompanyCrawlerProvider:
    return CompanyCrawlerProvider(
        settings or build_settings(),
        http_client=build_http_client(robots_handler),
        browser_factory=lambda: browser,
        clock=fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def _browser() -> FakeBrowser:
    return FakeBrowser(
        pages={
            # No trailing slash: _normalize_url only adds a scheme when
            # missing, so "https://acme.com" (this fixture's default
            # known_attributes["url"]) is passed to the crawler exactly
            # as-is, never rewritten to "https://acme.com/".
            "https://acme.com": _HOMEPAGE,
            "https://acme.com/leadership": _LEADERSHIP_PAGE,
        }
    )


def test_provider_id_and_display_name() -> None:
    provider = _provider(_browser())

    assert provider.provider_id == "company_crawler"
    assert provider.display_name == "Company Website Crawler"


def test_supports_only_person_subject_type() -> None:
    provider = _provider(_browser())

    assert provider.supported_subject_types == frozenset({SubjectType.PERSON})


def test_no_url_yields_failure_without_launching_browser() -> None:
    browser = _browser()
    provider = _provider(browser)

    response = provider.search(_request(known_attributes={"first_name": "Ada"}))

    assert response.status is EnrichmentStatus.FAILURE
    assert "url" in (response.error_message or "").lower()
    assert browser.opened_pages == []


def test_successful_crawl_returns_priority_pages() -> None:
    provider = _provider(_browser())

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1
    assert response.results[0].url == "https://acme.com/leadership"
    assert response.results[0].source == "company_crawler"


def test_bare_domain_is_normalized_to_https(monkeypatch: object) -> None:
    provider = _provider(_browser())

    response = provider.search(
        _request(known_attributes={"first_name": "Ada", "url": "acme.com"})
    )

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1


def test_robots_disallow_yields_success_with_no_results_and_no_browser_launch() -> (
    None
):
    browser = _browser()
    provider = _provider(browser, robots_handler=robots_disallow_all_transport)

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert response.results == ()
    assert browser.opened_pages == []


def test_missing_robots_txt_is_treated_as_allowed() -> None:
    browser = _browser()
    provider = _provider(browser, robots_handler=robots_not_found_transport)

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1


def test_unreachable_homepage_yields_failure() -> None:
    browser = FakeBrowser(pages={"https://acme.com": RuntimeError("boom")})
    provider = _provider(browser, settings=build_settings(max_retries=0))

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.FAILURE


def test_response_carries_request_and_subject_identifiers() -> None:
    provider = _provider(_browser())

    response = provider.search(_request())

    assert response.provider_id == "company_crawler"
    assert response.request_id == "req-1"
    assert response.subject_id == "row:1"


def test_every_page_opened_is_closed() -> None:
    browser = _browser()
    provider = _provider(browser)

    provider.search(_request())

    assert len(browser.opened_pages) > 0
    assert all(page.closed for page in browser.opened_pages)


def test_robots_txt_is_only_fetched_once_per_provider_instance() -> None:
    fetch_count = {"count": 0}

    def counting_transport(request: httpx.Request) -> httpx.Response:
        fetch_count["count"] += 1
        return robots_allow_all_transport(request)

    provider = _provider(_browser(), robots_handler=counting_transport)

    provider.search(_request())
    provider.search(_request(known_attributes={"first_name": "Bob", "url": "acme.com"}))

    assert fetch_count["count"] == 1


def test_close_shuts_down_the_browser() -> None:
    browser = _browser()
    provider = _provider(browser)
    provider.search(_request())

    provider.close()

    assert browser.closed is True


def test_close_is_safe_when_the_browser_was_never_launched() -> None:
    provider = _provider(_browser())

    provider.close()  # must not raise
