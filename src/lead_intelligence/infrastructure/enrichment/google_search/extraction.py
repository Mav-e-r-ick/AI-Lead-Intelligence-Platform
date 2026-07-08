"""Parses a Google Custom Search JSON API response into plain SearchResults.

WHY published_at IS A RAW STRING, NEVER A PARSED datetime:
Google's Custom Search API doesn't return a dedicated, reliable
publication-date field — at best, a page's own metadata (exposed under
`pagemap.metatags`) sometimes includes one, in whatever format that page's
author chose. Parsing every real-world date format a web page might use is
its own significant (and error-prone) undertaking, well beyond "gather
evidence." This module reports whatever raw value it finds, verbatim, or
None if nothing usable is present — an honest reflection of what's
actually available, never a guessed or reformatted date.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

#: Metatag keys, checked in order, that commonly carry a page's
#: publication or last-updated date. Not exhaustive — an honestly-scoped
#: Version 1 limitation, not a bug.
_PUBLISHED_TIME_METATAG_KEYS: tuple[str, ...] = (
    "article:published_time",
    "og:article:published_time",
    "datepublished",
    "date",
    "og:updated_time",
)


@dataclass(frozen=True)
class SearchResult:
    """One organic result from a Google Custom Search query.

    Attributes:
        title: The result's page title.
        url: The result's URL.
        snippet: The result's search-snippet excerpt.
        published_at: A raw, unparsed publication/last-updated date string
            found in the page's own metadata, or None if unavailable.
        source_domain: The result's source domain (e.g. "example.com").
    """

    title: str
    url: str
    snippet: str
    published_at: str | None
    source_domain: str


def parse_search_response(payload: Mapping[str, Any]) -> tuple[SearchResult, ...]:
    """Extract every usable result from one Google Custom Search JSON
    response body.

    Args:
        payload: The parsed JSON response body (`response.json()`).

    Returns:
        One SearchResult per item in `payload["items"]` that has both a
        title and a URL. Items missing either are skipped — there is
        nothing usable to report about them.
    """

    results = []
    for item in payload.get("items") or ():
        title = (item.get("title") or "").strip()
        url = (item.get("link") or "").strip()
        if not title or not url:
            continue

        snippet = (item.get("snippet") or "").strip()
        source_domain = (item.get("displayLink") or _domain_from_url(url)).strip()

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                published_at=_extract_published_at(item),
                source_domain=source_domain,
            )
        )
    return tuple(results)


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
