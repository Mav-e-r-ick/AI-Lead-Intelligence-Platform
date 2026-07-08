"""PageCache: a small TTL cache for fetched page content, keyed by URL.

WHY THIS EXISTS:
A single company enrichment run legitimately fetches the same homepage
and the same leadership page more than once — e.g. once per executive at
that company, since EnrichmentRequest is per-Subject and this provider is
invoked once per Person, but many people share one employer. Without a
cache, that would mean re-fetching (and re-parsing) the same pages
repeatedly for no new information. The cache is deliberately in-memory
only and keyed by URL, not by request or subject — the same URL, however
it's reached, is the same page.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta


class PageCache(ABC):
    """Where CompanyWebsiteProvider stores and reuses fetched page content."""

    @abstractmethod
    def get(self, url: str, now: datetime) -> str | None:
        """The cached content for `url`, or None if absent or expired."""

    @abstractmethod
    def set(self, url: str, content: str, now: datetime) -> None:
        """Cache `content` for `url`, timestamped as of `now`."""


@dataclass(frozen=True)
class _CacheEntry:
    content: str
    cached_at: datetime


class InMemoryPageCache(PageCache):
    """A plain in-memory PageCache with a fixed TTL, applied per lookup."""

    def __init__(self, ttl: timedelta) -> None:
        """Configure a cache whose entries expire after `ttl` has elapsed."""

        self._ttl = ttl
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, url: str, now: datetime) -> str | None:
        entry = self._entries.get(url)
        if entry is None:
            return None
        if now - entry.cached_at >= self._ttl:
            return None
        return entry.content

    def set(self, url: str, content: str, now: datetime) -> None:
        self._entries[url] = _CacheEntry(content=content, cached_at=now)
