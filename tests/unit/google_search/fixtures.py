"""Shared HTTP fixtures for the Google Search provider's tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import httpx


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def build_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """An httpx.Client whose requests are answered entirely by `handler`,
    never touching the real network."""

    return httpx.Client(transport=httpx.MockTransport(handler))


def search_item(
    title: str,
    url: str,
    snippet: str = "",
    display_link: str | None = None,
    published_time: str | None = None,
) -> dict[str, Any]:
    """One Google Custom Search API result item."""

    item: dict[str, Any] = {
        "title": title,
        "link": url,
        "snippet": snippet,
        "displayLink": display_link or "",
    }
    if published_time:
        item["pagemap"] = {"metatags": [{"article:published_time": published_time}]}
    return item


def search_response_body(*items: dict[str, Any]) -> dict[str, Any]:
    return {"items": list(items)}


def json_query_router(
    responses: Mapping[str, tuple[int, dict[str, Any]]]
) -> Callable[[httpx.Request], httpx.Response]:
    """A handler keyed by the request's `q` query parameter, returning the
    configured (status_code, json_body) pair, or a 404 for anything
    unlisted."""

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("q", "")
        if query not in responses:
            return httpx.Response(404)
        status_code, body = responses[query]
        return httpx.Response(status_code, json=body)

    return handler
