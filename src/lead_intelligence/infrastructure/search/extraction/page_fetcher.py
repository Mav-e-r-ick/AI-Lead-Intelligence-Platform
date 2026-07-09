"""PageFetcher: downloads one search result's destination page, safely.

This is the "Page Fetcher" stage from the approved Search Layer RFC —
the piece that was deliberately out of scope while the Search Layer only
*found* URLs, and is now in scope because the Search Extraction Engine's
whole job is to read what those URLs point at.

WHY ROBOTS.TXT IS CHECKED PER DESTINATION DOMAIN:
Unlike BrowserSearchProvider (which only ever navigates to one configured
search engine, so checks one robots.txt once), this fetcher visits
arbitrary third-party domains — whatever the search turned up. Every
domain gets its own robots.txt check, parsed once and cached for this
fetcher instance's lifetime, using the same
`RobotFileParser.can_fetch(user_agent, url)` convention
CompanyWebsiteProvider established. A missing/unreachable robots.txt is
treated as "no restrictions" — the standard crawler convention.

WHY PDFs ARE SKIPPED, TWICE:
Version 1's scope explicitly excludes PDFs — extracting text from PDF
requires a separate parsing stack and none of the deterministic HTML
rules below it apply. The skip happens at two layers: a URL whose path
ends in `.pdf` is never even requested, and a response whose
Content-Type declares PDF is discarded after the fact (a URL doesn't
have to end in `.pdf` to serve one). Both are logged, never silent.

WHY THE PAGE CACHE IS REUSED FROM company_website/cache.py:
`InMemoryPageCache` is already exactly "URL -> page text with a TTL,"
with zero Company-Website-specific logic. The same URL can legitimately
appear in multiple executives' search results (a shared press release, a
company news page), and re-downloading it per executive would be pure
waste — same reasoning, same class, no second copy.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from loguru import logger

from lead_intelligence.infrastructure.enrichment.company_website.cache import (
    InMemoryPageCache,
    PageCache,
)
from lead_intelligence.infrastructure.search.extraction.settings import (
    SearchExtractionSettings,
)

_ROBOTS_PATH = "/robots.txt"
_PDF_SUFFIX = ".pdf"
_PDF_CONTENT_TYPE = "application/pdf"


class PageFetcher:
    """Fetches one destination page's HTML text, or None when it can't or
    shouldn't be fetched (PDF, robots.txt disallow, exhausted retries)."""

    def __init__(
        self,
        settings: SearchExtractionSettings,
        http_client: httpx.Client | None = None,
        cache: PageCache | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a fetcher instance.

        Args:
            settings: Timeout/retry/backoff/cache policy and the
                user_agent used for both fetching and robots.txt checks.
            http_client: The httpx.Client used for every request. Defaults
                to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            cache: Where fetched page content is reused from. Defaults to
                a fresh InMemoryPageCache sized from `settings.cache_ttl`.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible cache behavior.
            sleep_fn: Called between retry attempts. Override with a no-op
                in tests to avoid real delays.
        """

        settings.validate()
        self._settings = settings
        self._http_client = http_client or httpx.Client(follow_redirects=True)
        self._cache = cache or InMemoryPageCache(ttl=settings.cache_ttl)
        self._clock = clock
        self._sleep = sleep_fn
        #: domain -> parsed robots.txt, or None for "unavailable, treat as
        #: allowed." Populated lazily, once per domain per fetcher instance.
        self._robots: dict[str, RobotFileParser | None] = {}

    def fetch(self, url: str) -> str | None:
        """The page text at `url`, or None if it was skipped or unfetchable.

        Skips (all logged, never silent): a `.pdf` URL, a URL the
        destination's robots.txt disallows for this user agent, and a
        response whose Content-Type declares PDF. Failures: timeouts,
        connection errors, and 5xx responses are retried per settings;
        4xx responses are never retried.
        """

        if urlparse(url).path.lower().endswith(_PDF_SUFFIX):
            logger.info("Skipping PDF URL (out of Version 1 scope): {}", url)
            return None

        if not self._robots_allow(url):
            logger.info("robots.txt disallows fetching {}; skipping.", url)
            return None

        return self._get(url)

    def _robots_allow(self, url: str) -> bool:
        """Whether `settings.user_agent` may fetch `url`, per its domain's
        robots.txt — fetched and parsed once per domain."""

        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"

        if domain not in self._robots:
            self._robots[domain] = self._load_robots(domain)

        parser = self._robots[domain]
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

    def _get(self, url: str) -> str | None:
        """Fetch `url`'s text content, via cache first, then retrying
        transient failures up to `settings.max_retries` additional times.
        Returns None if the content could not be obtained (or turned out
        to be a PDF)."""

        cached = self._cache.get(url, self._clock())
        if cached is not None:
            logger.debug("Cache hit for {}", url)
            return cached

        attempts = self._settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._http_client.get(
                    url,
                    headers={"User-Agent": self._settings.user_agent},
                    timeout=self._settings.timeout_seconds,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Request error fetching {} (attempt {}/{}): {}",
                    url,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 500:
                logger.warning(
                    "Server error {} fetching {} (attempt {}/{})",
                    response.status_code,
                    url,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 400:
                logger.info(
                    "Client error {} fetching {}; not retrying.",
                    response.status_code,
                    url,
                )
                return None

            content_type = response.headers.get("content-type", "")
            if _PDF_CONTENT_TYPE in content_type.lower():
                logger.info(
                    "Skipping PDF response (Content-Type: {}) from {} "
                    "(out of Version 1 scope).",
                    content_type,
                    url,
                )
                return None

            self._cache.set(url, response.text, self._clock())
            return response.text

        return None
