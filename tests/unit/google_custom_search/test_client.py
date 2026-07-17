"""Unit tests for GoogleCustomSearchClient, using a mocked httpx transport.
No test here makes a real network call."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from lead_intelligence.infrastructure.search.google_custom_search.client import (
    GoogleCustomSearchClient,
    parse_items,
)

_ITEMS_PAYLOAD = {
    "items": [
        {
            "title": "Ada Lovelace named CEO",
            "link": "https://example.com/a",
            "snippet": "Ada Lovelace was named CEO of Acme.",
            "displayLink": "example.com",
        },
        {
            "title": "No link, skipped",
            "snippet": "missing link",
        },
    ]
}


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _client(handler, **overrides) -> GoogleCustomSearchClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    kwargs: dict[str, object] = {
        "api_key": "key",
        "search_engine_id": "cx",
        "http_client": http_client,
        "clock": _fixed_clock,
        "sleep_fn": lambda seconds: None,
    }
    kwargs.update(overrides)
    return GoogleCustomSearchClient(**kwargs)  # type: ignore[arg-type]


def test_parse_items_skips_entries_missing_title_or_link() -> None:
    items = parse_items(_ITEMS_PAYLOAD)

    assert len(items) == 1
    assert items[0].title == "Ada Lovelace named CEO"
    assert items[0].source_domain == "example.com"


def test_successful_search_returns_parsed_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ITEMS_PAYLOAD)

    client = _client(handler)

    items = client.search("Ada Lovelace CEO")

    assert items is not None
    assert len(items) == 1


def test_site_restrict_is_sent_as_sitesearch_param() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    client = _client(handler)

    client.search("Ada Lovelace", site_restrict="linkedin.com")

    assert captured["params"]["siteSearch"] == "linkedin.com"
    assert captured["params"]["siteSearchFilter"] == "i"


def test_no_site_restrict_omits_sitesearch_param() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    client = _client(handler)

    client.search("Ada Lovelace")

    assert "siteSearch" not in captured["params"]


def test_num_is_capped_at_ten() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    client = _client(handler, max_results=25)

    client.search("Ada Lovelace")

    assert captured["params"]["num"] == "10"


def test_transient_5xx_is_retried_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json=_ITEMS_PAYLOAD)

    client = _client(handler, max_retries=2)

    items = client.search("Ada Lovelace")

    assert items is not None
    assert attempts["count"] == 2


def test_client_error_is_not_retried() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400)

    client = _client(handler, max_retries=2)

    items = client.search("Ada Lovelace")

    assert items is None
    assert attempts["count"] == 1


def test_exhausted_retries_return_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client(handler, max_retries=1)

    items = client.search("Ada Lovelace")

    assert items is None


def test_connection_error_is_retried_then_gives_up() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler, max_retries=1)

    items = client.search("Ada Lovelace")

    assert items is None


def test_non_json_response_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = _client(handler)

    items = client.search("Ada Lovelace")

    assert items is None


def test_results_are_cached_by_query_and_site_restrict() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json=_ITEMS_PAYLOAD)

    client = _client(handler)

    client.search("Ada Lovelace")
    client.search("Ada Lovelace")

    assert attempts["count"] == 1


def test_same_query_with_different_site_restrict_is_not_the_same_cache_entry() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json=_ITEMS_PAYLOAD)

    client = _client(handler)

    client.search("Ada Lovelace", site_restrict="linkedin.com")
    client.search("Ada Lovelace", site_restrict="reuters.com")

    assert attempts["count"] == 2


def test_cache_expires_after_ttl() -> None:
    attempts = {"count": 0}
    now = {"value": _fixed_clock()}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json=_ITEMS_PAYLOAD)

    client = _client(handler, cache_ttl=timedelta(seconds=1), clock=lambda: now["value"])

    client.search("Ada Lovelace")
    now["value"] = now["value"] + timedelta(seconds=2)
    client.search("Ada Lovelace")

    assert attempts["count"] == 2
