"""SearchResultCache: a small TTL cache for one query's search results,
keyed by the query string.

WHY THIS MIRRORS infrastructure/enrichment/google_search/cache.py:
Same rationale as that module's own docstring — the same query can
legitimately be searched more than once in a short window, and a real
browser navigation is far more expensive to repeat than a JSON API call,
making caching even more valuable here. The only difference from Google's
cache is the cached value's type: the canonical, shared
`application.dto.search_models.SearchResult`, not a provider-private one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from lead_intelligence.application.dto.search_models import SearchResult


class SearchResultCache(ABC):
    """Where BrowserSearchProvider stores and reuses one query's results."""

    @abstractmethod
    def get(self, query: str, now: datetime) -> tuple[SearchResult, ...] | None:
        """The cached results for `query`, or None if absent or expired."""

    @abstractmethod
    def set(self, query: str, results: tuple[SearchResult, ...], now: datetime) -> None:
        """Cache `results` for `query`, timestamped as of `now`."""


@dataclass(frozen=True)
class _CacheEntry:
    results: tuple[SearchResult, ...]
    cached_at: datetime


class InMemorySearchResultCache(SearchResultCache):
    """A plain in-memory SearchResultCache with a fixed TTL, applied per
    lookup."""

    def __init__(self, ttl: timedelta) -> None:
        """Configure a cache whose entries expire after `ttl` has elapsed."""

        self._ttl = ttl
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, query: str, now: datetime) -> tuple[SearchResult, ...] | None:
        entry = self._entries.get(query)
        if entry is None:
            return None
        if now - entry.cached_at >= self._ttl:
            return None
        return entry.results

    def set(self, query: str, results: tuple[SearchResult, ...], now: datetime) -> None:
        self._entries[query] = _CacheEntry(results=results, cached_at=now)
