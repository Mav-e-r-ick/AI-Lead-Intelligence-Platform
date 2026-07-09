"""Unit tests for PageFetcher, against a mocked httpx transport — no test
here ever touches the real network."""

from __future__ import annotations

import httpx

from lead_intelligence.infrastructure.search.extraction.page_fetcher import PageFetcher
from lead_intelligence.infrastructure.search.extraction.settings import (
    SearchExtractionSettings,
)
from tests.unit.search_extraction.fixtures import (
    build_http_client,
    fixed_clock,
    html_response,
    make_flaky_handler,
    pdf_response,
)

_URL = "https://news.example.com/article"


def _fetcher(
    client: httpx.Client, settings: SearchExtractionSettings | None = None
) -> PageFetcher:
    return PageFetcher(
        settings or SearchExtractionSettings(retry_backoff_seconds=0),
        http_client=client,
        clock=fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def test_fetches_page_text() -> None:
    client = build_http_client(pages={"/article": html_response("<html>hi</html>")})

    assert _fetcher(client).fetch(_URL) == "<html>hi</html>"


def test_pdf_url_is_skipped_without_any_request() -> None:
    requests: list[str] = []
    client = build_http_client(request_log=requests)

    result = _fetcher(client).fetch("https://news.example.com/annual-report.PDF")

    assert result is None
    assert requests == []


def test_pdf_content_type_response_is_discarded() -> None:
    client = build_http_client(pages={"/article": pdf_response()})

    assert _fetcher(client).fetch(_URL) is None


def test_robots_disallow_skips_the_fetch() -> None:
    requests: list[str] = []
    client = build_http_client(
        pages={"/article": html_response("<html>hi</html>")},
        robots_txt="User-agent: *\nDisallow: /",
        request_log=requests,
    )

    result = _fetcher(client).fetch(_URL)

    assert result is None
    # Only robots.txt was requested — never the page itself.
    assert requests == ["https://news.example.com/robots.txt"]


def test_missing_robots_txt_is_treated_as_allowed() -> None:
    client = build_http_client(pages={"/article": html_response("<html>hi</html>")})

    assert _fetcher(client).fetch(_URL) == "<html>hi</html>"


def test_robots_txt_is_fetched_once_per_domain() -> None:
    requests: list[str] = []
    client = build_http_client(
        pages={
            "/a": html_response("<html>a</html>"),
            "/b": html_response("<html>b</html>"),
        },
        robots_txt="User-agent: *\nAllow: /",
        request_log=requests,
    )
    fetcher = _fetcher(client)

    fetcher.fetch("https://news.example.com/a")
    fetcher.fetch("https://news.example.com/b")

    robots_requests = [url for url in requests if url.endswith("/robots.txt")]
    assert len(robots_requests) == 1


def test_transient_server_error_is_retried_then_succeeds() -> None:
    handler = make_flaky_handler(
        failures_before_success=1, success_html="<html>recovered</html>"
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))

    assert _fetcher(client).fetch(_URL) == "<html>recovered</html>"


def test_retries_exhausted_returns_none() -> None:
    handler = make_flaky_handler(failures_before_success=99, success_html="unused")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = SearchExtractionSettings(max_retries=1, retry_backoff_seconds=0)

    assert _fetcher(client, settings).fetch(_URL) is None


def test_client_error_is_not_retried() -> None:
    requests: list[str] = []
    client = build_http_client(
        pages={"/article": httpx.Response(403)}, request_log=requests
    )

    result = _fetcher(client).fetch(_URL)

    assert result is None
    page_requests = [url for url in requests if url.endswith("/article")]
    assert len(page_requests) == 1


def test_request_error_is_retried_then_gives_up() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        attempts["count"] += 1
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = SearchExtractionSettings(max_retries=2, retry_backoff_seconds=0)

    result = _fetcher(client, settings).fetch(_URL)

    assert result is None
    assert attempts["count"] == 3  # 1 initial attempt + 2 retries


def test_fetched_page_is_cached_across_repeated_fetches() -> None:
    requests: list[str] = []
    client = build_http_client(
        pages={"/article": html_response("<html>hi</html>")}, request_log=requests
    )
    fetcher = _fetcher(client)

    fetcher.fetch(_URL)
    fetcher.fetch(_URL)

    page_requests = [url for url in requests if url.endswith("/article")]
    assert len(page_requests) == 1
