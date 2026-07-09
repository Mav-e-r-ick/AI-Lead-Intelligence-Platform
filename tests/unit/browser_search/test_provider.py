"""End-to-end unit tests for BrowserSearchProvider.search(), using a fake
Playwright Browser/Page (tests/unit/browser_search/fixtures.py) and a
mocked httpx transport for the robots.txt check. No test here launches a
real browser or touches the real network."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import httpx

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
from lead_intelligence.infrastructure.search.browser.provider import (
    BrowserSearchProvider,
    _detect_interstitial,
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


def test_robots_disallow_no_longer_blocks_the_browser_search() -> None:
    """robots.txt disallowing the target is logged as a warning, not
    treated as a reason to skip searching — see provider.py's module
    docstring on why this changed (a human-operated browser session, not
    an automated crawler)."""

    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, robots_handler=robots_disallow_all_transport)

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) > 0
    assert len(browser.pages) > 0


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


def test_zero_results_saves_debug_html_and_screenshot(tmp_path: Path) -> None:
    browser = FakeBrowser(page_factory=lambda: FakePage(containers=[]))
    provider = _provider(
        browser,
        settings=build_settings(
            query_templates=('"{name}"',), debug_dir=str(tmp_path)
        ),
    )

    provider.search(_request())

    html_files = list(tmp_path.glob("*.html"))
    png_files = list(tmp_path.glob("*.png"))
    assert len(html_files) == 1
    assert len(png_files) == 1
    assert html_files[0].read_text() == "<html><body>fake page</body></html>"


def test_debug_artifacts_not_saved_when_results_are_found(tmp_path: Path) -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, settings=build_settings(debug_dir=str(tmp_path)))

    provider.search(_request())

    assert list(tmp_path.glob("*")) == []


def test_blank_debug_dir_disables_saving(tmp_path: Path) -> None:
    browser = FakeBrowser(page_factory=lambda: FakePage(containers=[]))
    provider = _provider(
        browser,
        settings=build_settings(query_templates=('"{name}"',), debug_dir=""),
    )

    provider.search(_request())

    assert list(tmp_path.glob("*")) == []


def test_detect_interstitial_consent_page_by_url() -> None:
    page = FakePage(url="https://consent.google.com/ml?continue=...")

    assert _detect_interstitial(page) == "consent_page"


def test_detect_interstitial_consent_page_by_text() -> None:
    page = FakePage(
        url="https://www.google.com/search?q=x",
        html="<html>Before you continue to Google Search</html>",
    )

    assert _detect_interstitial(page) == "consent_page"


def test_detect_interstitial_unusual_traffic_via_sorry_url() -> None:
    page = FakePage(
        url="https://www.google.com/sorry/index?continue=...",
        html="<html>Our systems have detected unusual traffic.</html>",
    )

    assert _detect_interstitial(page) == "unusual_traffic"


def test_detect_interstitial_captcha_via_sorry_url_without_unusual_traffic_text() -> (
    None
):
    page = FakePage(
        url="https://www.google.com/sorry/index?continue=...",
        html="<html><form id='captcha-form'>...</form></html>",
    )

    assert _detect_interstitial(page) == "captcha"


def test_detect_interstitial_unusual_traffic_via_text_alone() -> None:
    page = FakePage(
        url="https://www.google.com/search?q=x",
        html="<html>unusual traffic from your computer network</html>",
    )

    assert _detect_interstitial(page) == "unusual_traffic"


def test_detect_interstitial_none_for_a_normal_results_page() -> None:
    page = FakePage(
        url="https://www.google.com/search?q=x",
        html="<html><div class='g'>a real result</div></html>",
    )

    assert _detect_interstitial(page) is None


def test_interstitial_page_is_treated_as_a_failed_query_with_debug_capture(
    tmp_path: Path,
) -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(
            url="https://consent.google.com/ml?continue=...",
            html="<html>Before you continue to Google Search</html>",
        )
    )
    provider = _provider(
        browser,
        settings=build_settings(
            max_retries=0,
            query_templates=('"{name}"',),
            debug_dir=str(tmp_path),
        ),
    )

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert "consent" in (response.error_message or "").lower()
    html_files = list(tmp_path.glob("*consent_page*.html"))
    png_files = list(tmp_path.glob("*consent_page*.png"))
    assert len(html_files) == 1
    assert len(png_files) == 1


def test_search_opens_the_homepage_not_a_direct_results_url() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, settings=build_settings(query_templates=('"{name}"',)))

    provider.search(_request())

    page = browser.pages[0]
    assert page.goto_calls == ["https://search.example.org/"]


def test_search_types_the_query_character_by_character_and_presses_enter() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, settings=build_settings(query_templates=('"{name}"',)))

    provider.search(_request())

    page = browser.pages[0]
    assert page.keyboard.typed_text == '"Ada Lovelace"'
    assert page.keyboard.pressed_keys == ["Enter"]


def test_search_clicks_the_search_box_before_typing() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, settings=build_settings(query_templates=('"{name}"',)))

    provider.search(_request())

    page = browser.pages[0]
    assert page.click_calls == ["textarea[name='q']"]


def test_search_performs_randomized_scrolling() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    provider = _provider(browser, settings=build_settings(query_templates=('"{name}"',)))

    provider.search(_request())

    page = browser.pages[0]
    assert 2 <= len(page.mouse.wheel_calls) <= 4


def test_search_waits_for_load_state_and_for_the_results_selector() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(containers=[result_container("Title", "/a")])
    )
    settings = build_settings(
        query_templates=('"{name}"',), result_container_selector="div.result"
    )
    provider = _provider(browser, settings=settings)

    provider.search(_request())

    page = browser.pages[0]
    assert page.wait_for_load_state_calls == 1
    assert page.wait_for_selector_calls == ["div.result"]


def test_consent_page_is_accepted_and_search_continues_to_real_results() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(
            url="https://consent.google.com/ml?continue=...",
            html="<html>Before you continue to Google Search</html>",
            consent_accept_selector="#L2AGLb",
            post_consent_url="https://search.example.org/search?q=%22Ada+Lovelace%22",
            post_consent_html="<html><body>real results</body></html>",
            post_consent_containers=[result_container("Real result", "/a")],
        )
    )
    provider = _provider(browser, settings=build_settings(query_templates=('"{name}"',)))

    response = provider.search(_request())

    page = browser.pages[0]
    assert "#L2AGLb" in page.click_calls
    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1
    assert response.results[0].title == "Real result"


def test_missing_search_box_is_a_retryable_failure() -> None:
    browser = FakeBrowser(page_factory=lambda: FakePage(search_box_selector=None))
    provider = _provider(
        browser,
        settings=build_settings(max_retries=0, query_templates=('"{name}"',)),
    )

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert "search box" in (response.error_message or "").lower()


def test_wait_for_selector_timeout_does_not_abort_the_search() -> None:
    browser = FakeBrowser(
        page_factory=lambda: FakePage(
            containers=[result_container("Title", "/a")],
            wait_for_selector_raises=TimeoutError("no results selector yet"),
        )
    )
    provider = _provider(browser, settings=build_settings(query_templates=('"{name}"',)))

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) == 1
