"""Shared fixtures for the Search Extraction Engine's tests — an httpx
mock-transport builder and HTML page builders, so no test here ever
touches the real network."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Mapping

import httpx

from lead_intelligence.application.dto.search_models import SearchResult


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def make_search_result(
    url: str = "https://news.example.com/article",
    title: str = "Search result title",
    snippet: str = "Search result snippet.",
    source: str = "browser_search",
    rank: int = 1,
) -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet, source=source, rank=rank)


def announcement_page(
    headline: str = "Ada Lovelace named CTO of Acme Corp",
    body: str = (
        "Acme Corp announced today that Ada Lovelace has been appointed "
        "Chief Technology Officer of Acme Corp."
    ),
    published_at: str | None = "2024-05-30T09:00:00Z",
) -> str:
    """A representative announcement page, with script/style noise the
    content extractor must strip."""

    published_meta = (
        f'<meta property="article:published_time" content="{published_at}">'
        if published_at
        else ""
    )
    return f"""
    <html><head>
      <title>{headline}</title>
      {published_meta}
      <script>var tracking = true;</script>
    </head><body>
      <nav>Home | News | Contact</nav>
      <h1>{headline}</h1>
      <p>{body}</p>
      <style>.footer {{ color: gray; }}</style>
    </body></html>
    """


def build_http_client(
    pages: Mapping[str, httpx.Response] | None = None,
    default: httpx.Response | None = None,
    robots_txt: str | None = None,
    request_log: list[str] | None = None,
) -> httpx.Client:
    """An httpx.Client answering entirely from an in-memory routing table.

    Args:
        pages: URL path -> response.
        default: Response for any unlisted path (defaults to 404).
        robots_txt: Body served at /robots.txt; None serves a 404 there
            (the "no robots.txt, treat as allowed" case).
        request_log: If given, every requested URL is appended to it —
            lets tests assert which requests were (not) made.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request_log is not None:
            request_log.append(str(request.url))
        if request.url.path == "/robots.txt":
            if robots_txt is None:
                return httpx.Response(404)
            return httpx.Response(200, text=robots_txt)
        if pages and request.url.path in pages:
            return pages[request.url.path]
        return default if default is not None else httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def html_response(html: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, text=html)


def pdf_response() -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4"
    )


def make_flaky_handler(
    failures_before_success: int, success_html: str
) -> Callable[[httpx.Request], httpx.Response]:
    """A handler that returns 500 for the first N page requests, then the
    given HTML — robots.txt always 404s (treated as allowed)."""

    state = {"failures_left": failures_before_success}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if state["failures_left"] > 0:
            state["failures_left"] -= 1
            return httpx.Response(500)
        return html_response(success_html)

    return handler
