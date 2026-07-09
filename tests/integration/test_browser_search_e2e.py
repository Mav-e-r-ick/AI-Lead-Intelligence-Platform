"""End-to-end test for BrowserSearchProvider: a REAL headless browser
(Playwright + Chromium) against a REAL, local, static HTML page served
over localhost — never a live third-party search engine (see this
module's docstring in infrastructure/search/browser/README.md for why).

WHY THIS IS SKIPPED BY DEFAULT:
Every other test in this repository is a fast, dependency-free unit test.
This one launches a real browser process and a real (local) HTTP server,
which is slower and requires the `playwright` package's browser binaries
to actually be installed on the machine running it — not guaranteed in
every CI environment. It only runs when `RUN_BROWSER_SEARCH_E2E=1` is set
in the environment. See infrastructure/search/browser/README.md for exact
instructions.
"""

from __future__ import annotations

import http.server
import os
import threading
from datetime import datetime, timezone

import pytest

from lead_intelligence.application.dto.search_models import SearchRequest, SubjectType
from lead_intelligence.infrastructure.search.browser.provider import (
    BrowserSearchProvider,
)
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_SEARCH_E2E") != "1",
    reason=(
        "Real-browser end-to-end test. Set RUN_BROWSER_SEARCH_E2E=1 to run it "
        "(see infrastructure/search/browser/README.md)."
    ),
)

_RESULTS_PAGE = """
<!doctype html>
<html>
<body>
  <div class="result">
    <h3>Ada Lovelace named CTO of Acme Corp</h3>
    <a href="/articles/ada-lovelace-cto">read more</a>
    <p class="snippet">Acme Corp announced today that Ada Lovelace has been
    appointed Chief Technology Officer.</p>
  </div>
  <div class="result">
    <h3>Ada Lovelace speaks at conference</h3>
    <a href="https://example.org/articles/ada-conference">read more</a>
    <p class="snippet">Ada Lovelace gave a keynote address.</p>
  </div>
</body>
</html>
"""

# A page shaped like DuckDuckGo's real html.duckduckgo.com/html/ results
# markup (the classic .result / .result__a / .result__snippet template this
# repo's .env.local.example is configured for) — used to regression-guard
# those exact selectors with a REAL browser, since automating queries
# against the live, third-party duckduckgo.com is deliberately not done in
# this test suite (see module docstring).
_DUCKDUCKGO_SHAPED_RESULTS_PAGE = """
<!doctype html>
<html>
<body>
  <div id="links" class="results">
    <div class="result results_links results_links_deep web-result">
      <div class="links_main links_deep result__body">
        <h2 class="result__title">
          <a rel="nofollow" class="result__a" href="/articles/ada-lovelace-cto">
            Ada Lovelace named CTO of Acme Corp
          </a>
        </h2>
        <a class="result__snippet" href="/articles/ada-lovelace-cto">
          Acme Corp announced today that Ada Lovelace has been appointed
          Chief Technology Officer.
        </a>
      </div>
    </div>
    <div class="result results_links results_links_deep web-result">
      <div class="links_main links_deep result__body">
        <h2 class="result__title">
          <a rel="nofollow" class="result__a" href="https://example.org/articles/ada-conference">
            Ada Lovelace speaks at conference
          </a>
        </h2>
        <a class="result__snippet" href="https://example.org/articles/ada-conference">
          Ada Lovelace gave a keynote address.
        </a>
      </div>
    </div>
  </div>
</body>
</html>
"""


class _StaticResultsHandler(http.server.BaseHTTPRequestHandler):
    page_body = _RESULTS_PAGE

    def do_GET(self) -> None:  # noqa: N802 - required name by http.server
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
        else:
            body = type(self).page_body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # keep test output quiet


class _DuckDuckGoShapedResultsHandler(_StaticResultsHandler):
    page_body = _DUCKDUCKGO_SHAPED_RESULTS_PAGE


@pytest.fixture
def local_results_server() -> object:
    server = http.server.HTTPServer(("127.0.0.1", 0), _StaticResultsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def local_duckduckgo_shaped_server() -> object:
    server = http.server.HTTPServer(
        ("127.0.0.1", 0), _DuckDuckGoShapedResultsHandler
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_real_browser_collects_results_from_a_local_static_page(
    local_results_server: http.server.HTTPServer,
) -> None:
    port = local_results_server.server_address[1]
    settings = BrowserSearchProviderSettings(
        search_url_template=f"http://127.0.0.1:{port}/search?q={{query}}",
        result_container_selector="div.result",
        title_selector="h3",
        url_selector="a",
        snippet_selector="p.snippet",
        query_templates=('"{name}"',),
        headless=True,
        executable_path=os.environ.get("BROWSER_SEARCH_EXECUTABLE_PATH"),
    )
    provider = BrowserSearchProvider(settings)
    try:
        request = SearchRequest(
            request_id="e2e-1",
            subject_type=SubjectType.PERSON,
            subject_id="row:1",
            known_attributes={"first_name": "Ada", "last_name": "Lovelace"},
            requested_at=datetime.now(timezone.utc),
        )

        response = provider.search(request)

        assert len(response.results) == 2
        assert response.results[0].title == "Ada Lovelace named CTO of Acme Corp"
        assert response.results[0].url.endswith("/articles/ada-lovelace-cto")
        assert "Chief Technology Officer" in response.results[0].snippet
    finally:
        provider.close()


def test_real_browser_collects_results_using_the_configured_duckduckgo_selectors(
    local_duckduckgo_shaped_server: http.server.HTTPServer,
) -> None:
    """Regression guard for the exact selectors .env.local.example ships
    (BROWSER_SEARCH_RESULT_SELECTOR=.result, TITLE/URL_SELECTOR=.result__a,
    SNIPPET_SELECTOR=.result__snippet) against a REAL headless browser and a
    page shaped like DuckDuckGo's actual html.duckduckgo.com/html/ markup —
    catches a selector/markup mismatch without ever querying the live,
    third-party duckduckgo.com (see module docstring)."""

    port = local_duckduckgo_shaped_server.server_address[1]
    settings = BrowserSearchProviderSettings(
        search_url_template=f"http://127.0.0.1:{port}/html/?q={{query}}",
        result_container_selector=".result",
        title_selector=".result__a",
        url_selector=".result__a",
        snippet_selector=".result__snippet",
        query_templates=('"{name}"',),
        headless=True,
        executable_path=os.environ.get("BROWSER_SEARCH_EXECUTABLE_PATH"),
    )
    provider = BrowserSearchProvider(settings)
    try:
        request = SearchRequest(
            request_id="e2e-2",
            subject_type=SubjectType.PERSON,
            subject_id="row:1",
            known_attributes={"first_name": "Ada", "last_name": "Lovelace"},
            requested_at=datetime.now(timezone.utc),
        )

        response = provider.search(request)

        assert len(response.results) == 2
        assert response.results[0].title == "Ada Lovelace named CTO of Acme Corp"
        assert response.results[0].url.endswith("/articles/ada-lovelace-cto")
        assert "Chief Technology Officer" in response.results[0].snippet
    finally:
        provider.close()
