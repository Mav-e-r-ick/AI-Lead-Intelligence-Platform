"""End-to-end unit tests for BrowserSearchProvider.search(), using a fake
Playwright Browser/Page (tests/unit/browser_search/fixtures.py) and a
mocked httpx transport for the robots.txt check. No test here launches a
real browser or touches the real network."""

from __future__ import annotations

from typing import Callable

import httpx

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
from lead_intelligence.infrastructure.search.browser.provider import (
    BrowserSearchProvider,
)
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)
from tests.unit.browser_search.fixtures import (
    FakeBrowser,
    FakePage,
    build_http_client,
    build_settings,
    fixed_clock,
    result_container,
    robots_allow_all_transport,
    robots_disallow_all_transport,
    robots_not_found_transport,
)


def _request(known_attributes: dict[str, str] | None = None) -> SearchRequest:
    return SearchRequest(
        request_id="req-1",
        subject_type=SubjectType.PERSON,
        subject_id="row:1",
        known_attributes=(
            known_attributes
            if known_attributes is not None
            else {"first_name": "Ada", "last_name": "Lovelace", "company_name": "Acme"}
        ),
        requested_at=fixed_clock(),
    )


def _provider(
    browser: FakeBrowser,
    settings: BrowserSearchProviderSettings | None = None,
    robots_handler: Callable[
        [httpx.Request], httpx.Response
    ] = robots_allow_all_transport,
) -> BrowserSearchProvider:
    return BrowserSearchProvider(
        settings or build_settings(),
        http_client=build_http_client(robots_handler),
        browser_factory=lambda: browser,
        clock=fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def test_provider_id_and_display_name() -> None:
    provider = _provider(FakeBrowser())

    assert provider.provider_id == "browser_search"
    assert provider.display_name == "Browser Search"


def test_supports_only_person_subject_type() -> None:
    provider = _provider(FakeBrowser())

    assert provider.supported_subject_types == frozenset({SubjectType.PERSON})


def test_no_name_yields_failure_without_launching_browser() -> None:
    browser = FakeBrowser()
    provider = _provider(browser)

    response = provider.search(_request(known_attributes={}))

    assert response.status is EnrichmentStatus.FAILURE
    assert "name" in (response.error_message or "").lower()
    assert browser.pages == []


def test_successful_search_returns_results_from_every_query() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(
            containers=[result_container("Ada Lovelace promoted", "/a")]
        )
    )
    provider = _provider(browser)

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) > 0
    assert all(result.source == "browser_search" for result in response.results)


def test_every_page_opened_is_closed() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser)

    provider.search(_request())

    assert len(browser.pages) > 0
    assert all(page.closed for page in browser.pages)


def test_results_are_cached_across_repeated_searches() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser)

    provider.search(_request())
    pages_after_first_call = len(browser.pages)
    provider.search(_request())

    assert len(browser.pages) == pages_after_first_call


def test_query_navigation_failure_retries_up_to_max_retries() -> None:
    attempts = {"count": 0}

    def failing_page_factory() -> FakePage:
        attempts["count"] += 1
        return FakePage(goto_raises=RuntimeError("navigation timeout"))

    browser = FakeBrowser(page_factory=failing_page_factory)
    provider = _provider(
        browser, settings=build_settings(max_retries=2, query_templates=('"{name}"',))
    )

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert attempts["count"] == 3  # 1 initial attempt + 2 retries


def test_query_succeeds_after_a_transient_failure() -> None:
    calls = {"count": 0}

    def flaky_page_factory() -> FakePage:
        calls["count"] += 1
        if calls["count"] == 1:
            return FakePage(goto_raises=RuntimeError("temporary error"))
        return FakePage(containers=[result_container("Title", "/a")])

    browser = FakeBrowser(page_factory=flaky_page_factory)
    provider = _provider(
        browser, settings=build_settings(max_retries=2, query_templates=('"{name}"',))
    )

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1


def test_partial_status_when_some_queries_fail_and_others_succeed() -> None:
    def page_factory() -> FakePage:
        # Every query after the first fails: query templates are executed
        # in a fixed, deterministic order, and this factory tracks how many
        # pages have been requested so far to make exactly one query fail.
        page_factory.calls += 1  # type: ignore[attr-defined]
        if page_factory.calls == 1:  # type: ignore[attr-defined]
            return FakePage(containers=[result_container("Title", "/a")])
        return FakePage(goto_raises=RuntimeError("boom"))

    page_factory.calls = 0  # type: ignore[attr-defined]
    browser = FakeBrowser(page_factory=page_factory)
    provider = _provider(
        browser,
        settings=build_settings(
            max_retries=0, query_templates=('"{name}"', '"{name}" promotion')
        ),
    )

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.PARTIAL
    assert len(response.results) == 1


def test_robots_disallow_yields_success_with_no_results_and_no_browser_launch() -> None:
    browser = FakeBrowser()
    provider = _provider(browser, robots_handler=robots_disallow_all_transport)

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert response.results == ()
    assert browser.pages == []


def test_missing_robots_txt_is_treated_as_allowed() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, robots_handler=robots_not_found_transport)

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(browser.pages) > 0


def test_robots_txt_is_only_fetched_once_per_provider_instance() -> None:
    fetch_count = {"count": 0}

    def counting_transport(request: httpx.Request) -> httpx.Response:
        fetch_count["count"] += 1
        return robots_allow_all_transport(request)

    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(
        browser,
        settings=build_settings(query_templates=('"{name}"', '"{name}" promotion')),
        robots_handler=counting_transport,
    )

    provider.search(_request())

    assert fetch_count["count"] == 1


def test_response_carries_request_and_subject_identifiers() -> None:
    browser = FakeBrowser()
    provider = _provider(browser)

    response = provider.search(_request())

    assert response.provider_id == "browser_search"
    assert response.request_id == "req-1"
    assert response.subject_id == "row:1"


def test_close_shuts_down_the_browser() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser)
    provider.search(_request())

    provider.close()

    assert browser.closed is True


def test_close_is_safe_when_the_browser_was_never_launched() -> None:
    provider = _provider(FakeBrowser())

    provider.close()  # must not raise
