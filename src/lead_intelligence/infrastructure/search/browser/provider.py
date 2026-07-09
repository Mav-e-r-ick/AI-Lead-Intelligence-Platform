"""BrowserSearchProvider: searches for one executive's public web presence
by driving a real, headless browser (via Playwright) against a
configured search-results page, gathering result URLs the same way a
person clicking through a search engine would.

WHY THIS PROVIDER EXISTS ALONGSIDE GoogleSearchProvider:
GoogleSearchProvider calls the Google Custom Search JSON API — reliable,
sanctioned, but limited to whatever that one API's coverage/quota allows.
BrowserSearchProvider is the "when there's no API, drive a real browser"
fallback: any search engine that has a normal HTML results page (a
self-hosted metasearch instance, an internal enterprise search tool, or a
public engine the operator has confirmed they're authorized to automate
against) becomes usable via the same SearchProviderPort contract, without
this platform depending on that engine ever publishing an API.

WHY search_url_template/CSS SELECTORS HAVE NO BUILT-IN DEFAULT VALUE:
See settings.py's module docstring. Automating a real browser against a
search engine's own web UI is a decision only the operator can make for
their chosen target (terms of service, robots.txt, rate limits) — this
provider refuses to guess one on their behalf.

WHY THIS PROVIDER RETURNS SearchResults ONLY, NEVER OBSERVATIONS:
Per the approved Search Layer RFC, search and extraction are separate
stages. This provider's job ends at "here are the URLs this query
surfaced" — it never fetches a result's destination page and never
decides what a result means. (It does fetch the search engine's own
results page, which is not the same thing as fetching a result's
destination page — see the robots.txt note below.)

WHY ROBOTS.TXT IS CHECKED AGAINST THE SEARCH ENGINE'S OWN DOMAIN, NOT
EVERY RESULT'S DESTINATION:
This provider never crawls a result's destination page (see above) — the
only page it ever navigates to is the configured search engine's own
results page. That is the one place "respect robots.txt for pages you
crawl" applies to this class, and it is checked the same way
CompanyWebsiteProvider checks a company's robots.txt: fetched once (via a
plain HTTP request, not the browser) and checked with
`RobotFileParser.can_fetch(user_agent, url)` before ever launching a page
navigation there.

WHY QUERY BUILDING REUSES infrastructure/enrichment/google_search/query_builder.py
DIRECTLY, RATHER THAN A SECOND IMPLEMENTATION:
`build_queries()` is a pure, engine-agnostic function (name/company/title
placeholder substitution) with zero Google-specific logic — reusing it
here is exactly what "reuse the existing Search/Enrichment architecture"
means in practice, and avoids a second, drifting copy of the same
templating rules.

WHY THE BROWSER IS LAUNCHED LAZILY AND KEPT ALIVE ACROSS search() CALLS:
Launching a fresh Chromium process per query would be far slower than
reusing one already-running browser across many executives in the same
evaluation run — the same reasoning `httpx.Client()` reuse already
follows elsewhere in this codebase. `close()` must be called once the
caller is done with this provider (there is no `__del__`-based cleanup —
implicit cleanup on garbage collection is unreliable and this codebase
does not rely on it anywhere else).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SubjectType,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.infrastructure.enrichment.google_search.query_builder import (
    build_queries,
)
from lead_intelligence.infrastructure.search.browser.cache import (
    InMemorySearchResultCache,
    SearchResultCache,
)
from lead_intelligence.infrastructure.search.browser.extraction import (
    PageLike,
    extract_results,
)
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)

PROVIDER_ID = "browser_search"


class NavigablePage(PageLike, Protocol):
    """The subset of Playwright's `Page` this provider needs beyond what
    extraction.py already requires (PageLike): actually navigating, plus
    (for zero-result debugging, see `_save_debug_artifacts`) reading back
    the rendered HTML and taking a screenshot."""

    def goto(self, url: str, timeout: float | None = None) -> object: ...

    def close(self) -> None: ...

    def content(self) -> str: ...

    def screenshot(self, path: str) -> object: ...


class BrowserLike(Protocol):
    """The subset of Playwright's `Browser` this provider needs — kept
    minimal and structural so tests can fake it without importing
    Playwright at all."""

    def new_page(self) -> NavigablePage: ...

    def close(self) -> None: ...


def _default_browser_factory(
    settings: BrowserSearchProviderSettings,
) -> Callable[[], BrowserLike]:
    """The real, Playwright-backed factory used in production.

    Deliberately a plain function, not a method, so it has no hidden
    dependency on `self` — it only needs `settings`, making it trivial to
    replace wholesale in tests via the `browser_factory` constructor
    argument (see module docstring on why the browser is mockable at
    all).
    """

    def factory() -> BrowserLike:
        from playwright.sync_api import sync_playwright

        driver = sync_playwright().start()
        browser = driver.chromium.launch(
            headless=settings.headless,
            executable_path=settings.executable_path,
        )
        return _PlaywrightBrowser(driver, browser)

    return factory


class _PlaywrightBrowser:
    """Adapts a real Playwright `(playwright_driver, browser)` pair to
    `BrowserLike`, so `close()` shuts down both the browser process and
    the driver connection it came from."""

    def __init__(self, driver: object, browser: object) -> None:
        self._driver = driver
        self._browser = browser

    def new_page(self) -> NavigablePage:
        return self._browser.new_page()  # type: ignore[no-any-return,attr-defined]

    def close(self) -> None:
        self._browser.close()  # type: ignore[attr-defined]
        self._driver.stop()  # type: ignore[attr-defined]


class BrowserSearchProvider(SearchProviderPort):
    """Gathers public web search results about one executive by driving a
    real, headless browser against a configured search engine (Version 1
    — see module docstring and README.md)."""

    def __init__(
        self,
        settings: BrowserSearchProviderSettings,
        http_client: httpx.Client | None = None,
        cache: SearchResultCache | None = None,
        browser_factory: Callable[[], BrowserLike] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            settings: This provider's own configuration (search URL
                template, CSS selectors, query templates, retry/timeout/
                cache policy, headless flag). Typically built via
                `BrowserSearchProviderSettings.from_env()`.
            http_client: The httpx.Client used only for the robots.txt
                check (a plain text fetch, not a browser navigation).
                Defaults to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            cache: Where each query's results are reused from. Defaults to
                a fresh InMemorySearchResultCache sized from
                `settings.cache_ttl`.
            browser_factory: Builds the browser this provider drives.
                Defaults to a real, lazily-started Playwright Chromium
                instance; tests inject a fake `BrowserLike` so no test
                ever launches a real browser process.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps and cache
                behavior.
            sleep_fn: Called between retry attempts. Override with a
                no-op in tests to avoid real delays.
        """

        settings.validate()
        self._settings = settings
        self._http_client = http_client or httpx.Client()
        self._cache = cache or InMemorySearchResultCache(ttl=settings.cache_ttl)
        self._browser_factory = browser_factory or _default_browser_factory(settings)
        self._browser: BrowserLike | None = None
        self._robots_checked = False
        self._robots_parser: RobotFileParser | None = None
        self._clock = clock
        self._sleep = sleep_fn
        # Set by _search_single_query() immediately before it returns None,
        # so search() can report *why* every query failed instead of just
        # that they did — same pattern as CompanyWebsiteProvider's
        # _last_fetch_failure.
        self._last_query_failure: str | None = None

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Browser Search"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.PERSON})

    def close(self) -> None:
        """Shut down the underlying browser (and its Playwright driver
        connection), if one was ever launched. Safe to call even if
        `search()` was never called."""

        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def search(self, request: SearchRequest) -> SearchResponse:
        """Search for `request`'s executive and report every result found,
        across every configured query template, as plain SearchResults.

        Never raises for ordinary failure modes (no name available, every
        query failing, robots.txt disallowing the search engine) — those
        are reported via `SearchResponse.status`/`error_message`, per
        SearchProviderPort's contract.
        """

        name = _executive_name(request)
        company = request.known_attributes.get(fc.COMPANY_NAME)
        title = request.known_attributes.get(fc.TITLE)

        if not name:
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=(
                    "No executive name provided in known_attributes "
                    f"['{fc.FIRST_NAME}'/'{fc.LAST_NAME}']."
                ),
            )

        queries = build_queries(name, company, title, self._settings.query_templates)
        if not queries:
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message="No search queries could be built for this executive.",
            )

        if not self._robots_allow_search():
            logger.info(
                "robots.txt disallows querying the configured search engine; "
                "reporting nothing."
            )
            return self._response(request, EnrichmentStatus.SUCCESS, ())

        logger.info(
            "Browser Search provider starting: executive='{}', {} quer(y/ies)",
            name,
            len(queries),
        )

        results: list[SearchResult] = []
        queries_succeeded = 0
        queries_failed = 0

        for query in queries:
            query_results = self._search_single_query(query)
            if query_results is None:
                queries_failed += 1
                continue
            queries_succeeded += 1
            results.extend(query_results)

        error_message = None
        if queries_succeeded == 0:
            status = EnrichmentStatus.FAILURE
            reason = (
                f" ({self._last_query_failure})" if self._last_query_failure else ""
            )
            error_message = f"All {len(queries)} quer(y/ies) failed{reason}."
        elif queries_failed > 0:
            status = EnrichmentStatus.PARTIAL
        else:
            status = EnrichmentStatus.SUCCESS

        logger.info(
            "Browser Search provider finished: executive='{}', {} quer(y/ies) "
            "succeeded, {} failed, {} result(s)",
            name,
            queries_succeeded,
            queries_failed,
            len(results),
        )
        return self._response(
            request, status, tuple(results), error_message=error_message
        )

    def _response(
        self,
        request: SearchRequest,
        status: EnrichmentStatus,
        results: tuple[SearchResult, ...],
        error_message: str | None = None,
    ) -> SearchResponse:
        return SearchResponse(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=status,
            results=results,
            error_message=error_message,
            started_at=request.requested_at,
            completed_at=self._clock(),
        )

    def _search_single_query(self, query: str) -> tuple[SearchResult, ...] | None:
        """Fetch `query`'s results, via cache first, then retrying
        transient navigation failures (timeouts, navigation errors) up to
        `settings.max_retries` additional times. Returns None if results
        could not be obtained.
        """

        cached = self._cache.get(query, self._clock())
        if cached is not None:
            logger.debug("Cache hit for query '{}'", query)
            return cached

        url = self._settings.search_url_template.format(query=quote_plus(query))
        attempts = self._settings.max_retries + 1
        logger.info("Search query: '{}'", query)
        logger.info("Search URL: {}", url)

        for attempt in range(1, attempts + 1):
            page: NavigablePage | None = None
            try:
                page = self._get_browser().new_page()
                page.goto(url, timeout=self._settings.timeout_seconds * 1000)
                results = extract_results(page, self._settings, source=self.provider_id)
                if not results:
                    self._save_debug_artifacts(page, query)
            except Exception as exc:  # noqa: BLE001 - any navigation failure is retried
                logger.warning(
                    "Error searching '{}' (attempt {}/{}): {}",
                    query,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    self._last_query_failure = f"navigation error: {exc}"
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue
            finally:
                if page is not None:
                    page.close()

            logger.info("URLs collected for '{}': {} result(s)", query, len(results))
            self._cache.set(query, results, self._clock())
            return results

        return None

    def _save_debug_artifacts(self, page: NavigablePage, query: str) -> None:
        """Save the rendered page's HTML and a screenshot when a query's
        selectors yielded zero results, so a stale selector or a bot-
        check/rate-limit page (page loads, but has no real results) can be
        told apart after the fact — see settings.debug_dir. Best-effort:
        a failure here must never take down an otherwise-successful
        search, so any error is logged and swallowed, not raised.
        """

        if not self._settings.debug_dir:
            return
        try:
            debug_dir = Path(self._settings.debug_dir)
            debug_dir.mkdir(parents=True, exist_ok=True)
            stem = (
                f"{self._clock().strftime('%Y%m%dT%H%M%S%f')}_"
                f"{_sanitize_for_filename(query)}"
            )
            html_path = debug_dir / f"{stem}.html"
            screenshot_path = debug_dir / f"{stem}.png"
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(screenshot_path))
            logger.warning(
                "Zero results for '{}' — saved page HTML to {} and a screenshot "
                "to {} for selector debugging.",
                query,
                html_path,
                screenshot_path,
            )
        except Exception as exc:  # noqa: BLE001 - a debugging aid must never break search
            logger.debug("Could not save debug artifacts for '{}': {}", query, exc)

    def _get_browser(self) -> BrowserLike:
        if self._browser is None:
            self._browser = self._browser_factory()
        return self._browser

    def _robots_allow_search(self) -> bool:
        """Whether `settings.user_agent` is allowed, per the search
        engine's own robots.txt, to fetch its results page. Checked once
        (via a plain HTTP request, never the browser) and cached for this
        provider instance's lifetime — the search engine's domain never
        changes for a given provider instance. A robots.txt that can't be
        fetched at all is treated as "no restrictions," the standard
        crawler convention for a missing/unreachable robots.txt.
        """

        if self._robots_checked:
            return self._can_fetch_configured_url()

        self._robots_checked = True
        parsed = urlparse(self._settings.search_url_template)
        robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")

        try:
            response = self._http_client.get(
                robots_url,
                headers={"User-Agent": self._settings.user_agent},
                timeout=self._settings.timeout_seconds,
            )
        except httpx.RequestError as exc:
            logger.debug(
                "No robots.txt available at {} ({}); proceeding as allowed.",
                robots_url,
                exc,
            )
            return True

        if response.status_code >= 400:
            logger.debug(
                "robots.txt at {} returned {}; proceeding as allowed.",
                robots_url,
                response.status_code,
            )
            return True

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        self._robots_parser = parser
        return self._can_fetch_configured_url()

    def _can_fetch_configured_url(self) -> bool:
        if self._robots_parser is None:
            return True
        example_url = self._settings.search_url_template.format(query="")
        return self._robots_parser.can_fetch(self._settings.user_agent, example_url)


def _sanitize_for_filename(text: str, max_length: int = 60) -> str:
    """A version of `text` safe to use as (part of) a filename on both
    POSIX and Windows: only word characters, spaces, and hyphens survive."""

    cleaned = re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")
    return cleaned[:max_length] or "query"


def _executive_name(request: SearchRequest) -> str:
    first_name = (request.known_attributes.get(fc.FIRST_NAME) or "").strip()
    last_name = (request.known_attributes.get(fc.LAST_NAME) or "").strip()
    return " ".join(part for part in (first_name, last_name) if part)
