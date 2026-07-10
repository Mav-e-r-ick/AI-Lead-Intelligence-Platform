"""CompanyCrawlerProvider: the Search Layer's primary provider, replacing
BrowserSearchProvider in that role — instead of querying a third-party
search engine, it crawls the executive's own company website (the URL
already on file, `known_attributes[fc.URL]`), prioritizing links whose
path/text suggest a leadership/press/news page, and reports each
successfully crawled priority page as a plain SearchResult. Implements
`application/ports/search_provider_port.py`'s `SearchProviderPort` —
returns SearchResults only, exactly like BrowserSearchProvider did; the
existing, unmodified SearchExtractionEngine is what turns those into
ObservationCandidates (see run_pipeline.py's wiring).

WHY SubjectType.PERSON, NOT SubjectType.COMPANY (UNLIKE CompanyWebsiteProvider):
CompanyWebsiteProvider is registered with EnrichmentCoordinator, invoked at
company granularity. This provider is registered with SearchCoordinator,
invoked once per *executive* (the same PERSON-scoped call
BrowserSearchProvider always answered) — the company's URL is simply one
of that person's `known_attributes`, not a separate subject in its own
right here.

WHY robots.txt IS RESPECTED HERE (UNLIKE BrowserSearchProvider's Google
target):
BrowserSearchProvider's target is a third-party search engine the
operator uses via their own real browser/account — a human-using-their-
own-tools case (see that provider's own module docstring for why its
robots.txt check no longer blocks execution). This provider instead
crawls arbitrary *third-party companies'* own websites, at dataset scale
— the textbook case robots.txt exists for, and exactly what
CompanyWebsiteProvider already does today. A robots.txt disallow is
policy-compliant behavior, not a failure — reported as SUCCESS with zero
results, browser never launched for that request, mirroring
CompanyWebsiteProvider's own precedent exactly.

WHY THE BROWSER USES launch(), NOT launch_persistent_context():
Crawling a company's own public site is not adversarial the way querying
Google is — there is no bot-detection/profile-realism problem to solve,
so none of BrowserSearchProvider's persistent-profile machinery (real
Chrome profile, default-profile redirection, human-like typing/scrolling)
applies or is needed here. A fresh, throwaway Chromium instance per
provider lifetime is simpler and exactly sufficient.

WHY THE BROWSER IS LAUNCHED LAZILY AND KEPT ALIVE ACROSS search() CALLS:
Same reasoning as BrowserSearchProvider: reusing one browser across many
executives in a run beats relaunching per request. `close()` must be
called once the caller is done with this provider.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Protocol
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SearchResponse,
    SubjectType,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.infrastructure.search.company_crawler.crawler import (
    BrowserLike,
    HomepageUnreachable,
    crawl_company_site,
)
from lead_intelligence.infrastructure.search.company_crawler.settings import (
    CompanyCrawlerProviderSettings,
)

PROVIDER_ID = "company_crawler"
_ROBOTS_PATH = "/robots.txt"


def _default_browser_factory(
    settings: CompanyCrawlerProviderSettings,
) -> Callable[[], BrowserLike]:
    """The real, Playwright-backed factory used in production. A plain
    function (not a method) so it has no hidden dependency on `self`,
    trivially replaced wholesale in tests via the `browser_factory`
    constructor argument."""

    def factory() -> BrowserLike:
        from playwright.sync_api import sync_playwright

        logger.info(
            "Launching crawler browser: headless={}, executable_path='{}'",
            settings.headless,
            settings.executable_path or "(Playwright default)",
        )
        driver = sync_playwright().start()
        try:
            browser = driver.chromium.launch(
                headless=settings.headless,
                executable_path=settings.executable_path,
            )
        except Exception:
            # See BrowserSearchProvider's own provider.py for why this
            # matters: an unstopped driver here would leak, and a
            # subsequent retry would start a second sync_playwright()
            # session while the first was still alive.
            driver.stop()
            raise
        logger.debug("Crawler browser launched.")
        return _PlaywrightBrowser(driver, browser)

    return factory


class _PlaywrightBrowser:
    """Adapts a real Playwright `(playwright_driver, browser)` pair to
    `BrowserLike`, so `close()` shuts down both the browser process and
    the driver connection it came from."""

    def __init__(self, driver: object, browser: object) -> None:
        self._driver = driver
        self._browser = browser

    def new_page(self):  # type: ignore[no-untyped-def]
        return self._browser.new_page()  # type: ignore[attr-defined]

    def close(self) -> None:
        self._browser.close()  # type: ignore[attr-defined]
        self._driver.stop()  # type: ignore[attr-defined]


class CompanyCrawlerProvider(SearchProviderPort):
    """Crawls one executive's company website for leadership/press/news
    pages and reports each as a plain SearchResult (Version 1 — see
    module docstring and README.md)."""

    def __init__(
        self,
        settings: CompanyCrawlerProviderSettings | None = None,
        http_client: httpx.Client | None = None,
        browser_factory: Callable[[], BrowserLike] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            settings: This provider's own configuration. Defaults to
                CompanyCrawlerProviderSettings()'s conservative defaults.
            http_client: The httpx.Client used only for robots.txt checks
                (a plain text fetch, not a browser navigation). Defaults
                to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            browser_factory: Builds the browser this provider drives.
                Defaults to a real, lazily-started Playwright Chromium
                instance; tests inject a fake `BrowserLike` so no test
                ever launches a real browser process.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
            sleep_fn: Called between retry attempts. Override with a
                no-op in tests to avoid real delays.
        """

        self._settings = settings or CompanyCrawlerProviderSettings()
        self._settings.validate()
        self._http_client = http_client or httpx.Client()
        self._browser_factory = browser_factory or _default_browser_factory(
            self._settings
        )
        self._browser: BrowserLike | None = None
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self._clock = clock
        self._sleep = sleep_fn

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Company Website Crawler"

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
        """Crawl `request`'s company website and report every priority
        page found, as plain SearchResults.

        Never raises for ordinary failure modes (no company URL on file,
        the homepage unreachable, robots.txt disallowing the site) —
        those are reported via `SearchResponse.status`/`error_message`,
        per SearchProviderPort's contract.
        """

        website_url = (request.known_attributes.get(fc.URL) or "").strip()
        if not website_url:
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=(
                    f"No company website URL provided in known_attributes['{fc.URL}']."
                ),
            )

        homepage_url = _normalize_url(website_url)
        logger.info(
            "Company Crawler provider starting: subject_id={}, url={}",
            request.subject_id,
            homepage_url,
        )

        if not self._robots_allow(homepage_url):
            logger.info(
                "robots.txt disallows crawling {}; reporting nothing.", homepage_url
            )
            return self._response(request, EnrichmentStatus.SUCCESS, ())

        try:
            results = crawl_company_site(
                self._get_browser(),
                homepage_url,
                self._settings,
                source=self.provider_id,
                robots_allow=self._robots_allow,
                sleep_fn=self._sleep,
            )
        except HomepageUnreachable as exc:
            logger.warning("Company crawl of {} failed: {}", homepage_url, exc)
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=f"Failed to fetch homepage: {homepage_url}",
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the coordinator
            logger.warning("Company crawl of {} failed: {}", homepage_url, exc)
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=f"Crawl failed for {homepage_url}: {exc}",
            )

        logger.info(
            "Company Crawler provider finished: subject_id={}, {} page(s) found",
            request.subject_id,
            len(results),
        )
        return self._response(request, EnrichmentStatus.SUCCESS, results)

    def _response(
        self,
        request: SearchRequest,
        status: EnrichmentStatus,
        results: tuple,
        error_message: str | None = None,
    ) -> SearchResponse:
        return SearchResponse(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=status,
            results=tuple(results),
            error_message=error_message,
            started_at=request.requested_at,
            completed_at=self._clock(),
        )

    def _get_browser(self) -> BrowserLike:
        if self._browser is None:
            self._browser = self._browser_factory()
        return self._browser

    def _robots_allow(self, url: str) -> bool:
        """Whether `settings.user_agent` may fetch `url`, per its domain's
        robots.txt — fetched and parsed once per domain, cached for this
        provider instance's lifetime. A missing/unreachable robots.txt is
        treated as "no restrictions," the standard crawler convention."""

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._robots_cache:
            self._robots_cache[domain] = self._load_robots(domain)

        parser = self._robots_cache[domain]
        if parser is None:
            return True
        return parser.can_fetch(self._settings.user_agent, url)

    def _load_robots(self, domain: str) -> RobotFileParser | None:
        robots_url = urljoin(domain, _ROBOTS_PATH)
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
            return None

        if response.status_code >= 400:
            logger.debug(
                "robots.txt at {} returned {}; proceeding as allowed.",
                robots_url,
                response.status_code,
            )
            return None

        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser


def _normalize_url(url: str) -> str:
    """Ensure `url` has a scheme, defaulting to https for a bare domain
    (e.g. an executive dataset's "acme.com" column value) — same
    normalization CompanyWebsiteProvider's own provider.py applies."""

    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url
