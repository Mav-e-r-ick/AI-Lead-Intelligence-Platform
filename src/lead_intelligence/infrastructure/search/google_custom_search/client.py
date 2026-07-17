"""GoogleCustomSearchClient: one shared, retry/cache-guarded HTTP client
for the Google Custom Search JSON API — the same API
`infrastructure/enrichment/google_search/provider.py` already uses for
`EnrichmentCoordinator`.

WHY THIS IS ITS OWN, SHARED MODULE INSTEAD OF THREE COPIES:
The Federated Search redesign adds three Search Layer providers that all
need the exact same low-level capability — "call the Google Custom Search
JSON API for one query, optionally restricted to one site, with retry and
caching" — `google/` (general web search), `linkedin/` (LinkedIn-profile
search, restricted to linkedin.com), and `news/` (trusted-newswire search,
restricted to a small set of domains). Copying the retry/backoff/caching
logic (already proven in `enrichment/google_search/provider.py`) three
times would triple the surface area for the exact same bug to hide in.
This module is the one place that logic lives; each of the three
providers is a thin layer on top that only supplies its own query
templates, site restriction, and confidence scoring.

WHY THIS IS NOT A MODIFICATION OF `enrichment/google_search/`:
That package is `EnrichmentProviderPort`-shaped (`EnrichmentRequest` in,
`ObservationCandidate`s out) and is explicitly out of this redesign's
scope — it keeps powering `EnrichmentCoordinator` unmodified. This module
has no dependency on it and vice versa; the two independently call the
same public Google API with the same request shape because that is simply
what the API looks like, not because either reuses the other's code.

WHY `site_restrict` IS A PLAIN PARAMETER, NOT A THIRD PROVIDER-SPECIFIC
CLIENT SUBCLASS:
Google's Custom Search API supports scoping one request to a single
site via the `siteSearch`/`siteSearchFilter` parameters — no extra
capability is needed for `linkedin_search"`'s "only linkedin.com" or
`news_search`'s "only these newswire domains" (the latter uses a `q`-level
`(site:a.com OR site:b.com OR ...)` clause instead, since `siteSearch`
only accepts one domain — see `infrastructure/search/news/provider.py`).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx
from loguru import logger

#: Metatag keys, checked in order, that commonly carry a page's
#: publication or last-updated date. Same deliberately non-exhaustive list
#: `enrichment/google_search/extraction.py` already uses — one shared
#: vocabulary of "where dates live," not two drifting copies.
_PUBLISHED_TIME_METATAG_KEYS: tuple[str, ...] = (
    "article:published_time",
    "og:article:published_time",
    "datepublished",
    "date",
    "og:updated_time",
)


@dataclass(frozen=True)
class GoogleCustomSearchItem:
    """One organic result from a Google Custom Search query.

    Attributes:
        title: The result's page title.
        url: The result's URL.
        snippet: The result's search-snippet excerpt.
        published_at: A raw, unparsed publication/last-updated date string
            found in the page's own metadata, or None if unavailable —
            same "never guess a format" rule as every other raw date in
            this codebase.
        source_domain: The result's source domain (e.g. "example.com").
    """

    title: str
    url: str
    snippet: str
    published_at: str | None
    source_domain: str


def parse_items(payload: Mapping[str, Any]) -> tuple[GoogleCustomSearchItem, ...]:
    """Extract every usable result from one Google Custom Search JSON
    response body. Items missing a title or URL are skipped."""

    items = []
    for item in payload.get("items") or ():
        title = (item.get("title") or "").strip()
        url = (item.get("link") or "").strip()
        if not title or not url:
            continue

        snippet = (item.get("snippet") or "").strip()
        source_domain = (item.get("displayLink") or _domain_from_url(url)).strip()

        items.append(
            GoogleCustomSearchItem(
                title=title,
                url=url,
                snippet=snippet,
                published_at=_extract_published_at(item),
                source_domain=source_domain,
            )
        )
    return tuple(items)


def _extract_published_at(item: Mapping[str, Any]) -> str | None:
    pagemap = item.get("pagemap") or {}
    metatags = pagemap.get("metatags") or ()
    for tags in metatags:
        for key in _PUBLISHED_TIME_METATAG_KEYS:
            value = tags.get(key)
            if value:
                return str(value).strip()
    return None


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc


class GoogleCustomSearchCache(ABC):
    """Where GoogleCustomSearchClient stores and reuses one (query,
    site_restrict) pair's results."""

    @abstractmethod
    def get(self, cache_key: str, now: datetime) -> tuple[GoogleCustomSearchItem, ...] | None:
        """The cached items for `cache_key`, or None if absent or expired."""

    @abstractmethod
    def set(
        self, cache_key: str, items: tuple[GoogleCustomSearchItem, ...], now: datetime
    ) -> None:
        """Cache `items` for `cache_key`, timestamped as of `now`."""


@dataclass(frozen=True)
class _CacheEntry:
    items: tuple[GoogleCustomSearchItem, ...]
    cached_at: datetime


class InMemoryGoogleCustomSearchCache(GoogleCustomSearchCache):
    """A plain in-memory GoogleCustomSearchCache with a fixed TTL, applied
    per lookup — same shape as `enrichment/google_search/cache.py`'s
    `InMemorySearchResultCache`."""

    def __init__(self, ttl: timedelta) -> None:
        self._ttl = ttl
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, cache_key: str, now: datetime) -> tuple[GoogleCustomSearchItem, ...] | None:
        entry = self._entries.get(cache_key)
        if entry is None:
            return None
        if now - entry.cached_at >= self._ttl:
            return None
        return entry.items

    def set(
        self, cache_key: str, items: tuple[GoogleCustomSearchItem, ...], now: datetime
    ) -> None:
        self._entries[cache_key] = _CacheEntry(items=items, cached_at=now)


class GoogleCustomSearchClient:
    """One retry/cache-guarded connection to the Google Custom Search
    JSON API, shared by every Search Layer provider that queries it."""

    def __init__(
        self,
        api_key: str,
        search_engine_id: str,
        base_url: str = "https://www.googleapis.com/customsearch/v1",
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        max_results: int = 10,
        http_client: httpx.Client | None = None,
        cache: GoogleCustomSearchCache | None = None,
        cache_ttl: timedelta = timedelta(hours=6),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a client instance.

        Args:
            api_key: Google Custom Search JSON API key.
            search_engine_id: The Programmable Search Engine id ("cx").
            base_url: API base URL. Overridable for testing.
            timeout_seconds: Per-request timeout.
            max_retries: Additional attempts after an initial failed
                request (timeout, connection error, 5xx, or HTTP 429)
                before giving up. 4xx (other than 429) is never retried.
            retry_backoff_seconds: Base delay before a retry; multiplied
                by the attempt number for simple linear backoff.
            max_results: Default results requested per query (Google's own
                `num` parameter), capped at Google's per-request limit of
                10; a caller may request fewer via `search(..., num=...)`.
            http_client: The httpx.Client used for every request. Defaults
                to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            cache: Where each (query, site_restrict) pair's results are
                reused from. Defaults to a fresh
                InMemoryGoogleCustomSearchCache sized from `cache_ttl`.
            cache_ttl: Only used to build the default cache above; ignored
                if `cache` is supplied directly.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps and cache
                behavior.
            sleep_fn: Called between retry attempts. Override with a
                no-op in tests to avoid real delays.
        """

        self._api_key = api_key
        self._search_engine_id = search_engine_id
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._max_results = max_results
        self._http_client = http_client or httpx.Client()
        self._cache = cache or InMemoryGoogleCustomSearchCache(ttl=cache_ttl)
        self._clock = clock
        self._sleep = sleep_fn

    def search(
        self,
        query: str,
        site_restrict: str | None = None,
        num: int | None = None,
    ) -> tuple[GoogleCustomSearchItem, ...] | None:
        """Search `query`, via cache first, then retrying transient
        failures up to `max_retries` additional times.

        Args:
            query: The full query string (any `site:`/boolean operators a
                caller wants are just part of this string — Google's API
                treats them as ordinary query syntax).
            site_restrict: If given, scopes the search to this one domain
                via Google's own `siteSearch` parameter (e.g.
                "linkedin.com"). For scoping to *multiple* domains, build
                that into `query` itself (e.g.
                `"(site:a.com OR site:b.com) ..."`) — Google's
                `siteSearch` parameter only accepts one domain.
            num: Results requested for this call, overriding the client's
                own `max_results` default.

        Returns:
            None if every attempt failed (logged); otherwise every result
            Google returned (possibly empty — a legitimate "no results").
        """

        cache_key = f"{site_restrict or ''}::{query}"
        cached = self._cache.get(cache_key, self._clock())
        if cached is not None:
            logger.debug("Cache hit for query '{}' (site_restrict={})", query, site_restrict)
            return cached

        params: dict[str, str | int] = {
            "key": self._api_key,
            "cx": self._search_engine_id,
            "q": query,
            "num": min(num or self._max_results, 10),
        }
        if site_restrict:
            params["siteSearch"] = site_restrict
            params["siteSearchFilter"] = "i"

        attempts = self._max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._http_client.get(
                    self._base_url, params=params, timeout=self._timeout_seconds
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Request error searching '{}' (attempt {}/{}): {}",
                    query,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._retry_backoff_seconds * attempt)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "{} searching '{}' (attempt {}/{})",
                    response.status_code,
                    query,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 400:
                logger.info(
                    "Client error {} searching '{}'; not retrying.",
                    response.status_code,
                    query,
                )
                return None

            try:
                payload = response.json()
            except ValueError:
                logger.error("Non-JSON response searching '{}'", query)
                return None

            items = parse_items(payload)
            self._cache.set(cache_key, items, self._clock())
            return items

        return None
