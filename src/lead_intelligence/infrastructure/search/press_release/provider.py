"""PressReleaseProvider: one of the five federated Search Layer
providers. Crawls the executive's own company website, prioritizing its
press/newsroom/media/investor-relations/announcements section
specifically, looking for executive appointment announcements. Implements
`SearchProviderPort` — returns SearchResults only.

WHY THIS IS A SEPARATE PROVIDER FROM CompanyCrawlerProvider, NOT A MODE
OF IT:
This task explicitly names both as distinct providers with distinct
search scopes (CompanyCrawlerProvider: leadership/management/board/about/
team/people/press/news; PressReleaseProvider: press/newsroom/media/
investor-relations/announcements specifically) and explicitly says "Keep
the existing implementation" for CompanyCrawlerProvider — so this is a
new, independent crawl of the same site with a narrower, differently-
weighted keyword set, not a parameter added to the provider that must stay
unmodified. Running both is intentional, federated redundancy: a
"Leadership" page and a "Press Releases" index often carry different,
complementary evidence about the same appointment.

WHY THIS SUPPORTS ONLY SubjectType.PERSON:
Same reasoning as CompanyCrawlerProvider — `SearchCoordinator` invokes it
once per executive; the company's URL is one of that person's
`known_attributes`.

WHY THE BROWSER USES launch(), NOT launch_persistent_context(), AND WHY
robots.txt IS RESPECTED:
Same reasoning as CompanyCrawlerProvider's own provider.py — crawling a
company's own public site at dataset scale is exactly the textbook case
robots.txt exists for, and there is no bot-detection/profile-realism
problem a persistent Chrome profile would solve here.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable
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
from lead_intelligence.application.search.confidence import score_confidence
from lead_intelligence.infrastructure.search.press_release.crawler import (
    BrowserLike,
    HomepageUnreachable,
    crawl_company_press_pages,
)
from lead_intelligence.infrastructure.search.press_release.settings import (
    PressReleaseProviderSettings,
)

PROVIDER_ID = "press_release"
_ROBOTS_PATH = "/robots.txt"


def _default_browser_factory(
    settings: PressReleaseProviderSettings,
) -> Callable[[], BrowserLike]:
    """The real, Playwright-backed factory used in production. Wraps
    `launch()` in try/except and stops the just-started driver before
    re-raising on any failure — the same driver-leak-safe pattern applied
    throughout this codebase's Playwright-based providers."""

    def factory() -> BrowserLike:
        from playwright.sync_api import sync_playwright

        logger.info(
            "Launching press release crawler browser: headless={}, executable_path='{}'",
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
            driver.stop()
            raise
        logger.debug("Press release crawler browser launched.")
        return _PlaywrightBrowser(driver, browser)

    return factory


class _PlaywrightBrowser:
    """Adapts a real Playwright `(playwright_driver, browser)` pair to
    `BrowserLike`."""

    def __init__(self, driver: object, browser: object) -> None:
        self._driver = driver
        self._browser = browser

    def new_page(self):  # type: ignore[no-untyped-def]
        return self._browser.new_page()  # type: ignore[attr-defined]

    def close(self) -> None:
        self._browser.close()  # type: ignore[attr-defined]
        self._driver.stop()  # type: ignore[attr-defined]


class PressReleaseProvider(SearchProviderPort):
    """Crawls one executive's company website for press/newsroom/media/
    investor-relations/announcements pages and reports each as a plain
    SearchResult (Version 1 — see module docstring)."""

    def __init__(
        self,
        settings: PressReleaseProviderSettings | None = None,
        http_client: httpx.Client | None = None,
        browser_factory: Callable[[], BrowserLike] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            settings: This provider's own configuration.
            http_client: The httpx.Client used only for robots.txt checks.
                Defaults to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            browser_factory: Builds the browser this provider drives.
                Defaults to a real, lazily-started Playwright Chromium
                instance; tests inject a fake `BrowserLike`.
            clock: Returns the current UTC time. Override with a fixed
                value in tests.
            sleep_fn: Called between retry attempts. Override with a
                no-op in tests.
        """

        self._settings = settings or PressReleaseProviderSettings()
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
        return "Press Release Crawler"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.PERSON})

    def close(self) -> None:
        """Shut down the underlying browser, if one was ever launched."""

        if self._browser is not None:
            self._browser.close()
            self._browser = None

    def search(self, request: SearchRequest) -> SearchResponse:
        """Crawl `request`'s company website's press section and report
        every priority page found, as plain SearchResults.

        Never raises for ordinary failure modes — reported via
        `SearchResponse.status`/`error_message`.
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
            "Press Release provider starting: subject_id={}, url={}",
            request.subject_id,
            homepage_url,
        )

        if not self._robots_allow(homepage_url):
            logger.info(
                "robots.txt disallows crawling {}; reporting nothing.", homepage_url
            )
            return self._response(request, EnrichmentStatus.SUCCESS, ())

        try:
            raw_results = crawl_company_press_pages(
                self._get_browser(),
                homepage_url,
                self._settings,
                source=self.provider_id,
                robots_allow=self._robots_allow,
                sleep_fn=self._sleep,
            )
        except HomepageUnreachable as exc:
            logger.warning("Press release crawl of {} failed: {}", homepage_url, exc)
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=f"Failed to fetch homepage: {homepage_url}",
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the coordinator
            logger.warning("Press release crawl of {} failed: {}", homepage_url, exc)
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=f"Crawl failed for {homepage_url}: {exc}",
            )

        results = tuple(
            replace(result, confidence=score_confidence(result.url, self.provider_id))
            for result in raw_results
        )

        logger.info(
            "Press Release provider finished: subject_id={}, {} page(s) found",
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
        provider instance's lifetime."""

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
    """Ensure `url` has a scheme, defaulting to https for a bare domain —
    same normalization CompanyCrawlerProvider's own provider.py applies."""

    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url
