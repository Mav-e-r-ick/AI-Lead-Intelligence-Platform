"""End-to-end unit tests for PressReleaseProvider.search(), using a fake
Playwright Browser/Page (fixtures.py) and a mocked httpx transport for
robots.txt checks. No test here launches a real browser or touches the
real network."""

from __future__ import annotations

from typing import Callable

import httpx

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
from lead_intelligence.infrastructure.search.press_release.provider import (
    PressReleaseProvider,
)
from lead_intelligence.infrastructure.search.press_release.settings import (
    PressReleaseProviderSettings,
)
from tests.unit.press_release.fixtures import (
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
  <a href="/press">Press</a>
  <a href="/contact">Contact</a>
</body></html>
"""

_PRESS_PAGE = """
<html><head><title>Acme Corp Press Releases</title>
<meta name="description" content="Acme names new CEO.">
</head><body><p>Ada Lovelace has been named CEO.</p></body></html>
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
    settings: PressReleaseProviderSettings | None = None,
    robots_handler: Callable[[httpx.Request], httpx.Response] = robots_allow_all_transport,
) -> PressReleaseProvider:
    return PressReleaseProvider(
        settings or build_settings(),
        http_client=build_http_client(robots_handler),
        browser_factory=lambda: browser,
        clock=fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def _browser() -> FakeBrowser:
    return FakeBrowser(
        pages={
            "https://acme.com": _HOMEPAGE,
            "https://acme.com/press": _PRESS_PAGE,
        }
    )


def test_provider_id_and_display_name() -> None:
    provider = _provider(_browser())

    assert provider.provider_id == "press_release"
    assert provider.display_name == "Press Release Crawler"


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


def test_successful_crawl_returns_priority_pages_with_press_release_confidence() -> None:
    provider = _provider(_browser())

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1
    assert response.results[0].url == "https://acme.com/press"
    assert response.results[0].source == "press_release"
    assert response.results[0].confidence == 0.95


def test_bare_domain_is_normalized_to_https() -> None:
    provider = _provider(_browser())

    response = provider.search(
        _request(known_attributes={"first_name": "Ada", "url": "acme.com"})
    )

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1


def test_robots_disallow_yields_success_with_no_results_and_no_browser_launch() -> None:
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

    assert response.provider_id == "press_release"
    assert response.request_id == "req-1"
    assert response.subject_id == "row:1"


def test_every_page_opened_is_closed() -> None:
    browser = _browser()
    provider = _provider(browser)

    provider.search(_request())

    assert len(browser.opened_pages) > 0
    assert all(page.closed for page in browser.opened_pages)


def test_close_shuts_down_the_browser() -> None:
    browser = _browser()
    provider = _provider(browser)
    provider.search(_request())

    provider.close()

    assert browser.closed is True


def test_close_is_safe_when_the_browser_was_never_launched() -> None:
    provider = _provider(_browser())

    provider.close()  # must not raise
