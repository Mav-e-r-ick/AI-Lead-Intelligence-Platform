"""Unit tests for InMemorySearchResultCache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lead_intelligence.infrastructure.enrichment.google_search.cache import (
    InMemorySearchResultCache,
)
from lead_intelligence.infrastructure.enrichment.google_search.extraction import (
    SearchResult,
)

_RESULT = SearchResult(
    title="Ada Lovelace promoted to CTO",
    url="https://example.com/ada",
    snippet="...",
    published_at=None,
    source_domain="example.com",
)


def _now() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_get_returns_none_for_uncached_query() -> None:
    cache = InMemorySearchResultCache(ttl=timedelta(hours=1))

    assert cache.get('"Ada Lovelace" promotion', _now()) is None


def test_set_then_get_returns_cached_results() -> None:
    cache = InMemorySearchResultCache(ttl=timedelta(hours=1))

    cache.set('"Ada Lovelace" promotion', (_RESULT,), _now())

    assert cache.get('"Ada Lovelace" promotion', _now()) == (_RESULT,)


def test_entry_expires_after_ttl_elapses() -> None:
    cache = InMemorySearchResultCache(ttl=timedelta(hours=1))
    cache.set('"Ada Lovelace" promotion', (_RESULT,), _now())

    later = _now() + timedelta(hours=1)

    assert cache.get('"Ada Lovelace" promotion', later) is None


def test_entry_is_still_valid_just_before_ttl_elapses() -> None:
    cache = InMemorySearchResultCache(ttl=timedelta(hours=1))
    cache.set('"Ada Lovelace" promotion', (_RESULT,), _now())

    almost_expired = _now() + timedelta(minutes=59)

    assert cache.get('"Ada Lovelace" promotion', almost_expired) == (_RESULT,)


def test_queries_are_cached_independently() -> None:
    cache = InMemorySearchResultCache(ttl=timedelta(hours=1))
    cache.set('"Ada Lovelace" promotion', (_RESULT,), _now())

    assert cache.get('"Ada Lovelace" resigned', _now()) is None
    assert cache.get('"Ada Lovelace" promotion', _now()) == (_RESULT,)


def test_empty_results_tuple_can_be_cached() -> None:
    cache = InMemorySearchResultCache(ttl=timedelta(hours=1))

    cache.set('"Ada Lovelace" promotion', (), _now())

    assert cache.get('"Ada Lovelace" promotion', _now()) == ()
