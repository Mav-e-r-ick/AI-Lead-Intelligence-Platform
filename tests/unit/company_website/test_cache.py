"""Unit tests for InMemoryPageCache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lead_intelligence.infrastructure.enrichment.company_website.cache import (
    InMemoryPageCache,
)


def _now() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_get_returns_none_for_uncached_url() -> None:
    cache = InMemoryPageCache(ttl=timedelta(hours=1))

    assert cache.get("https://acme.com", _now()) is None


def test_set_then_get_returns_cached_content() -> None:
    cache = InMemoryPageCache(ttl=timedelta(hours=1))

    cache.set("https://acme.com", "<html></html>", _now())

    assert cache.get("https://acme.com", _now()) == "<html></html>"


def test_entry_expires_after_ttl_elapses() -> None:
    cache = InMemoryPageCache(ttl=timedelta(hours=1))
    cache.set("https://acme.com", "<html></html>", _now())

    later = _now() + timedelta(hours=1)

    assert cache.get("https://acme.com", later) is None


def test_entry_is_still_valid_just_before_ttl_elapses() -> None:
    cache = InMemoryPageCache(ttl=timedelta(hours=1))
    cache.set("https://acme.com", "<html></html>", _now())

    almost_expired = _now() + timedelta(minutes=59)

    assert cache.get("https://acme.com", almost_expired) == "<html></html>"


def test_urls_are_cached_independently() -> None:
    cache = InMemoryPageCache(ttl=timedelta(hours=1))
    cache.set("https://acme.com", "home", _now())

    assert cache.get("https://acme.com/leadership", _now()) is None
    assert cache.get("https://acme.com", _now()) == "home"
