"""SearchResultCache: a small TTL cache for one query's search results,
keyed by the query string.

WHY THIS EXISTS:
The same query (e.g. `'"Ada Lovelace" "Acme Corp"'`) can legitimately be
searched more than once in a short window — e.g. the same executive
enriched again shortly after a previous run, or two different Digital
Twins that happen to share a query after deduplication upstream. Without a
cache, that would mean re-issuing (and re-paying for) the same Google
Custom Search API call for no new information. The cache is deliberately
in-memory only and keyed by the exact query string — the same query,
however it's reached, is the same search.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from lead_intelligence.infrastructure.enrichment.google_search.extraction import (
    SearchResult,
)


class SearchResultCache(ABC):
    """Where GoogleSearchProvider stores and reuses one query's results."""

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
