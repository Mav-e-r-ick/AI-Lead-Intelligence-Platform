"""BrowserSearchProvider: searches for one executive's public web presence
by driving the operator's own, real Google Chrome (via Playwright's
`launch_persistent_context()`, against that Chrome's real user-data
directory — cookies, browsing history, existing signed-in sessions
included) against a configured search-results page, gathering result URLs
the same way a person clicking through a search engine would.

WHY THIS PROVIDER EXISTS ALONGSIDE GoogleSearchProvider:
GoogleSearchProvider calls the Google Custom Search JSON API — reliable,
sanctioned, but limited to whatever that one API's coverage/quota allows.
BrowserSearchProvider is the "when there's no API, drive a real browser"
fallback: any search engine that has a normal HTML results page (a
self-hosted metasearch instance, an internal enterprise search tool, or a
public engine the operator has confirmed they're authorized to automate
against) becomes usable via the same SearchProviderPort contract, without
this platform depending on that engine ever publishing an API. As
configured by `.env.local.example`, that target is Google's own results
page (`https://www.google.com/search?q={query}`) — see the module
docstring caveat below on why that specific target very likely still
needs an explicit robots.txt/authorization decision from the operator.

WHY search_url_template/CSS SELECTORS HAVE NO BUILT-IN DEFAULT VALUE:
See settings.py's module docstring. Automating a real browser against a
search engine's own web UI is a decision only the operator can make for
their chosen target (terms of service, robots.txt, rate limits) — this
provider refuses to guess one on their behalf.

WHY launch_persistent_context() INSTEAD OF launch():
`launch()` starts a fresh, throwaway browser profile every time — no
cookies, no history, always logged out, and far more obviously automated
to a search engine's bot-detection than a real person's browser. Google
in particular treats a browser with a real, aged, signed-in profile very
differently from a bare-fresh Chromium instance.
`launch_persistent_context(user_data_dir, ...)` launches directly against
a real Chrome profile directory and returns a `BrowserContext` (not a
`Browser` — there is no separate Browser object for a persistent
context); everywhere else in this provider that previously held a
`Browser` now holds that `BrowserContext` instead, via the same
`BrowserLike` seam (see `_PlaywrightBrowser`). WARNING: Chrome will not
launch a second time against a `user_data_dir` that already has a running
Chrome instance open on it — see settings.py's `user_data_dir` docstring.

WHY robots.txt IS CHECKED BUT NO LONGER BLOCKS EXECUTION (CHANGED):
Google's real robots.txt has, for many years, disallowed `/search` for
generic crawlers — a rule aimed at automated bots hitting Google
programmatically, not at a human using their own browser and account.
Now that this provider drives the operator's own real, signed-in Chrome
through the same homepage → type → click sequence a person would use
(see below), `_robots_allow_search()`/`_can_fetch_configured_url()` are
kept UNCHANGED and still called — but `search()` now only logs a warning
when the target disallows it, and proceeds anyway, rather than returning
early with zero results. This is a deliberate, explicit choice made by
the operator running this code, not a default: robots.txt is a voluntary
convention for automated crawlers, not law, and this class's own
`user_agent` string is never sent to Google at all in the browser-driven
flow (only the plain-HTTP robots.txt fetch uses it) — but Google's Terms
of Service separately restrict automated querying regardless of
robots.txt, and the operator remains solely responsible for confirming
they are authorized to do this against their chosen target and account.

WHY THE HOMEPAGE IS VISITED FIRST, NOT A DIRECT RESULTS URL (CHANGED):
The previous version navigated straight to
`search_url_template.format(query=...)` (e.g.
`https://www.google.com/search?q=...`) — a referrerless, no-interaction-
history navigation that (especially against a persistent profile Google
hasn't seen search from before) reliably lands on a consent interstitial
instead of results; the old code detected that consent page but only
ever treated it as a failure to retry-then-give-up on, never attempted to
accept it. `_search_single_query()` now drives `page` through
`_perform_human_like_search()`: open the configured target's homepage
(derived from `search_url_template`'s own scheme+host — no new setting),
wait for it to load, detect and click through a consent page if one
appears, locate the search box, type the query character by character
with randomized delays, press Enter, wait for results, then do a little
randomized scrolling — all *before* `extract_results()` runs, unchanged,
against whatever `result_container_selector`/`title_selector`/
`url_selector`/`snippet_selector` are configured. A CAPTCHA/"unusual
traffic" page (or a consent page that couldn't be dismissed) appearing
after this sequence is still detected by the same `_detect_interstitial()`
as before and still funneled into the existing retry-then-fail path.

WHY CONSENT/CAPTCHA/"UNUSUAL TRAFFIC" PAGES ARE DETECTED EXPLICITLY:
Google serves these in place of real results, but still returns HTTP 200
and a normal-looking page — `extract_results()` would otherwise just
report "zero results" with no indication *why*, and every subsequent
query in the same run would likely hit the exact same interstitial. See
`_detect_interstitial()`.

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

import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol, Sequence
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
    ElementLike,
    PageLike,
    extract_results,
)
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)

PROVIDER_ID = "browser_search"

#: Candidate search-box selectors, tried in order, on the target's
#: homepage — covers Google's current ("textarea[name='q']") and legacy
#: ("input[name='q']") markup plus the generic HTML5 "input[type=search]"
#: most other engines use, so this stays usable for a non-Google
#: `search_url_template` too (see settings.py's "no built-in, hardcoded
#: target search engine").
_SEARCH_BOX_SELECTORS: tuple[str, ...] = (
    "textarea[name='q']",
    "input[name='q']",
    "input[type='search']",
)

#: Candidate "accept"/"agree" controls on a consent interstitial, tried in
#: order. "#L2AGLb" is Google's own long-stable id for its "Accept all"
#: button; the two :has-text() selectors are a generic fallback for other
#: consent-management platforms' wording.
_CONSENT_ACCEPT_SELECTORS: tuple[str, ...] = (
    "#L2AGLb",
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
)

#: Randomized delay bounds (seconds, passed through self._sleep so tests
#: can no-op them) for each stage of the human-like search flow. Not
#: exposed as settings — see module docstring on keeping this the
#: smallest change necessary; these can graduate to settings later if an
#: operator needs to tune them.
_POST_LOAD_WAIT_RANGE_S = (0.8, 2.0)
_POST_CONSENT_WAIT_RANGE_S = (0.4, 1.0)
_TYPING_DELAY_RANGE_S = (0.05, 0.25)
_POST_RESULTS_WAIT_RANGE_S = (0.6, 1.5)
_SCROLL_STEPS_RANGE = (2, 4)
_SCROLL_DELTA_RANGE = (150.0, 500.0)
_SCROLL_PAUSE_RANGE_S = (0.2, 0.6)


class _InterstitialPageDetected(Exception):
    """Raised internally when a search-results navigation lands on a
    consent/CAPTCHA/"unusual traffic" page instead of real results —
    caught by `_search_single_query`'s existing retry handling, exactly
    like a navigation timeout, so no separate retry path is needed."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"{reason.replace('_', ' ')} encountered")
        self.reason = reason


class _SearchBoxNotFound(Exception):
    """Raised internally when none of `_SEARCH_BOX_SELECTORS` matched the
    homepage — caught by `_search_single_query`'s existing retry handling,
    exactly like a navigation timeout."""

    def __init__(self, homepage_url: str) -> None:
        super().__init__(f"no search box found on {homepage_url}")


class KeyboardLike(Protocol):
    """The subset of Playwright's `Keyboard` this provider needs, for
    typing the query and pressing Enter like a person would."""

    def type(self, text: str, delay: float | None = None) -> None: ...

    def press(self, key: str) -> None: ...


class MouseLike(Protocol):
    """The subset of Playwright's `Mouse` this provider needs, for the
    small randomized scroll before extraction."""

    def wheel(self, delta_x: float, delta_y: float) -> None: ...


class NavigablePage(PageLike, Protocol):
    """The subset of Playwright's `Page` this provider needs beyond what
    extraction.py already requires (PageLike): navigating, reading back
    rendered HTML/a screenshot (for debug-artifact capture), and — for the
    human-like homepage → type → click search flow (see module docstring)
    — locating/clicking elements, waiting for load state/a selector,
    typing, and scrolling."""

    def goto(self, url: str, timeout: float | None = None) -> object: ...

    def close(self) -> None: ...

    def content(self) -> str: ...

    def screenshot(self, path: str) -> object: ...

    def title(self) -> str: ...

    def query_selector(self, selector: str) -> ElementLike | None: ...

    def click(self, selector: str, timeout: float | None = None) -> object: ...

    def wait_for_load_state(
        self, state: str = "load", timeout: float | None = None
    ) -> object: ...

    def wait_for_selector(
        self, selector: str, timeout: float | None = None
    ) -> object: ...

    @property
    def keyboard(self) -> KeyboardLike: ...

    @property
    def mouse(self) -> MouseLike: ...


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

        logger.info(
            "Launching browser: user_data_dir='{}', headless={}, "
            "executable_path='{}'",
            settings.user_data_dir,
            settings.headless,
            settings.executable_path or "(Playwright default)",
        )
        driver = sync_playwright().start()
        context = driver.chromium.launch_persistent_context(
            settings.user_data_dir,
            headless=settings.headless,
            executable_path=settings.executable_path,
        )
        logger.debug("Browser launched.")
        return _PlaywrightBrowser(driver, context)

    return factory


class _PlaywrightBrowser:
    """Adapts a real Playwright `(playwright_driver, persistent
    BrowserContext)` pair to `BrowserLike`. A persistent context IS the
    browser session — `launch_persistent_context()` returns a
    `BrowserContext` directly, with no separate `Browser` object to hold
    (see module docstring on why persistent context, not `launch()`).
    `close()` shuts down both the context (and its Chrome process) and the
    driver connection it came from."""

    def __init__(self, driver: object, context: object) -> None:
        self._driver = driver
        self._context = context

    def new_page(self) -> NavigablePage:
        return self._context.new_page()  # type: ignore[no-any-return,attr-defined]

    def close(self) -> None:
        self._context.close()  # type: ignore[attr-defined]
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
            logger.warning(
                "robots.txt disallows user_agent '{}' from '{}'. Continuing "
                "anyway: this provider now drives the operator's own real, "
                "signed-in browser session rather than an automated crawler "
                "(see provider.py's module docstring) — the operator is "
                "responsible for confirming they are authorized to do this "
                "for their chosen target and account.",
                self._settings.user_agent,
                self._settings.search_url_template,
            )

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

        # No longer navigated to directly (see module docstring on why) —
        # kept only as an informational log line, for comparison against
        # wherever the human-like flow, below, actually ends up.
        equivalent_url = self._settings.search_url_template.format(
            query=quote_plus(query)
        )
        attempts = self._settings.max_retries + 1
        logger.info("Search query: '{}'", query)
        logger.debug("Equivalent direct results URL: {}", equivalent_url)

        for attempt in range(1, attempts + 1):
            page: NavigablePage | None = None
            try:
                page = self._get_browser().new_page()
                self._perform_human_like_search(page, query)
                interstitial = _detect_interstitial(page)
                if interstitial is not None:
                    self._save_debug_artifacts(page, query, reason=interstitial)
                    raise _InterstitialPageDetected(interstitial)
                logger.debug("Extraction started for '{}'", query)
                results = extract_results(page, self._settings, source=self.provider_id)
                if not results:
                    self._save_debug_artifacts(page, query, reason="zero_results")
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

    def _perform_human_like_search(self, page: NavigablePage, query: str) -> None:
        """Search `query` on `page` the way a person would: open the
        target's homepage, wait for it, accept a consent dialog if one
        appears, click the search box, type the query with randomized
        per-character delays, press Enter, wait for results, then a
        little randomized scrolling — see module docstring ("WHY THE
        HOMEPAGE IS VISITED FIRST..."). Leaves `page` on the results page
        for the caller's `_detect_interstitial()`/`extract_results()`
        calls; raises (caught by `_search_single_query`'s existing retry
        handling, same as a navigation timeout always has been) if no
        search box could be found.
        """

        homepage_url = self._homepage_url()
        logger.info("Opening homepage: {}", homepage_url)
        page.goto(homepage_url, timeout=self._settings.timeout_seconds * 1000)
        page.wait_for_load_state("load", timeout=self._settings.timeout_seconds * 1000)
        self._random_pause(_POST_LOAD_WAIT_RANGE_S)

        if _detect_interstitial(page) == "consent_page":
            logger.info("Consent page detected; attempting to accept.")
            if _accept_consent(page):
                logger.info("Consent accepted.")
                self._random_pause(_POST_CONSENT_WAIT_RANGE_S)
            else:
                logger.warning(
                    "Consent page detected but no accept control was found "
                    "among {}; continuing anyway.",
                    _CONSENT_ACCEPT_SELECTORS,
                )

        search_box_selector = _find_search_box(page, _SEARCH_BOX_SELECTORS)
        if search_box_selector is None:
            raise _SearchBoxNotFound(homepage_url)

        logger.debug("Search box located: '{}'", search_box_selector)
        page.click(search_box_selector, timeout=self._settings.timeout_seconds * 1000)
        logger.info("Typing query: '{}'", query)
        self._type_like_a_human(page, query)
        logger.info("Pressing Enter.")
        page.keyboard.press("Enter")

        logger.debug("Waiting for results to load.")
        self._wait_for_results(page)
        self._random_pause(_POST_RESULTS_WAIT_RANGE_S)

        logger.debug("Scrolling.")
        self._scroll_like_a_human(page)

        logger.debug("Current page URL: {}", page.url)
        logger.debug("Current page title: {}", _safe_title(page))

    def _homepage_url(self) -> str:
        """The configured target's homepage — derived from
        `search_url_template`'s own scheme+host, so this stays
        engine-agnostic (no new, Google-specific setting) exactly like
        `_robots_allow_search()` already derives that target's robots.txt
        URL the same way."""

        parsed = urlparse(self._settings.search_url_template)
        return f"{parsed.scheme}://{parsed.netloc}/"

    def _random_pause(self, bounds: tuple[float, float]) -> None:
        self._sleep(random.uniform(*bounds))

    def _type_like_a_human(self, page: NavigablePage, query: str) -> None:
        for character in query:
            page.keyboard.type(character)
            self._sleep(random.uniform(*_TYPING_DELAY_RANGE_S))

    def _wait_for_results(self, page: NavigablePage) -> None:
        try:
            page.wait_for_selector(
                self._settings.result_container_selector,
                timeout=self._settings.timeout_seconds * 1000,
            )
        except Exception as exc:  # noqa: BLE001 - absence is handled by the caller
            logger.debug("wait_for_selector for results did not resolve: {}", exc)

    def _scroll_like_a_human(self, page: NavigablePage) -> None:
        for _ in range(random.randint(*_SCROLL_STEPS_RANGE)):
            page.mouse.wheel(0, random.uniform(*_SCROLL_DELTA_RANGE))
            self._random_pause(_SCROLL_PAUSE_RANGE_S)

    def _save_debug_artifacts(
        self, page: NavigablePage, query: str, reason: str
    ) -> None:
        """Save the rendered page's HTML and a screenshot whenever a query
        didn't yield real results — either its selectors matched nothing
        (`reason="zero_results"`: a stale selector, or a bot-check/rate-
        limit page that still loaded but has no real results), or a
        consent/CAPTCHA/"unusual traffic" interstitial was detected
        outright (`reason` is `_detect_interstitial()`'s return value) —
        see settings.debug_dir. Best-effort: a failure here must never
        take down an otherwise-successful search, so any error is logged
        and swallowed, not raised.
        """

        if not self._settings.debug_dir:
            return
        try:
            debug_dir = Path(self._settings.debug_dir)
            debug_dir.mkdir(parents=True, exist_ok=True)
            stem = (
                f"{self._clock().strftime('%Y%m%dT%H%M%S%f')}_{reason}_"
                f"{_sanitize_for_filename(query)}"
            )
            html_path = debug_dir / f"{stem}.html"
            screenshot_path = debug_dir / f"{stem}.png"
            html_path.write_text(page.content(), encoding="utf-8")
            page.screenshot(path=str(screenshot_path))
            logger.warning(
                "{} for '{}' — saved page HTML to {} and a screenshot to {} "
                "for debugging.",
                reason,
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


def _detect_interstitial(page: NavigablePage) -> str | None:
    """Whether `page` (already navigated to) is a consent page, a CAPTCHA
    challenge, or an "unusual traffic" block instead of real results.
    Google returns HTTP 200 and a normal-looking page for every one of
    these — `extract_results()` alone would just report "zero results"
    with no indication why. Checked via `page.url`/`page.content()`
    (already required by `NavigablePage` for debug-artifact capture) —
    URL patterns first (most reliable), then well-known page text.

    Returns:
        "consent_page", "captcha", "unusual_traffic", or None if `page`
        looks like a normal results page.
    """

    url = (page.url or "").lower()
    html = page.content().lower()

    if "consent.google.com" in url or "before you continue to google" in html:
        return "consent_page"
    if "/sorry/" in url or "recaptcha" in html or "captcha-form" in html:
        return "unusual_traffic" if "unusual traffic" in html else "captcha"
    if "unusual traffic" in html:
        return "unusual_traffic"
    return None


def _find_search_box(page: NavigablePage, selectors: Sequence[str]) -> str | None:
    """The first of `selectors` present on `page`, or None if none match."""

    for selector in selectors:
        if page.query_selector(selector) is not None:
            return selector
    return None


def _accept_consent(page: NavigablePage) -> bool:
    """Click the first matching control in `_CONSENT_ACCEPT_SELECTORS`.
    Returns whether one was found and clicked. A click that itself raises
    (element detached, obscured, etc.) is treated the same as "not
    found" — the next candidate selector is tried rather than propagating
    the error, since failing to dismiss consent is handled by the caller
    (logged, then continuing anyway), not fatal to this attempt."""

    for selector in _CONSENT_ACCEPT_SELECTORS:
        if page.query_selector(selector) is None:
            continue
        try:
            page.click(selector)
            return True
        except Exception as exc:  # noqa: BLE001 - try the next candidate selector
            logger.debug("Could not click consent control '{}': {}", selector, exc)
    return False


def _safe_title(page: NavigablePage) -> str:
    """`page.title()`, or "" if it can't be read — a logging aid only,
    never worth failing a search over."""

    try:
        return page.title()
    except Exception:  # noqa: BLE001 - logging aid only
        return ""


def _sanitize_for_filename(text: str, max_length: int = 60) -> str:
    """A version of `text` safe to use as (part of) a filename on both
    POSIX and Windows: only word characters, spaces, and hyphens survive."""

    cleaned = re.sub(r"[^\w\s-]", "", text).strip().replace(" ", "_")
    return cleaned[:max_length] or "query"


def _executive_name(request: SearchRequest) -> str:
    first_name = (request.known_attributes.get(fc.FIRST_NAME) or "").strip()
    last_name = (request.known_attributes.get(fc.LAST_NAME) or "").strip()
    return " ".join(part for part in (first_name, last_name) if part)
