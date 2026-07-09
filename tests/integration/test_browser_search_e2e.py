"""End-to-end test for BrowserSearchProvider: a REAL browser (Playwright +
Chromium, via `launch_persistent_context()`) against a REAL, local, static
HTML page served over localhost — never a live third-party search engine
(see this module's docstring in infrastructure/search/browser/README.md
for why).

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
from pathlib import Path

import pytest

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
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

# A page shaped like Google's real www.google.com/search results markup
# (div.g result containers, an <a> wrapping an <h3> title, a .VwiC3b
# snippet — the template this repo's .env.local.example is configured
# for) — used to regression-guard those exact selectors with a REAL
# browser, since automating queries against the live, third-party
# google.com is deliberately not done in this test suite (see module
# docstring).
_GOOGLE_SHAPED_RESULTS_PAGE = """
<!doctype html>
<html>
<body>
  <div id="search">
    <div class="g">
      <div class="tF2Cxc">
        <a href="/articles/ada-lovelace-cto">
          <h3 class="LC20lb">Ada Lovelace named CTO of Acme Corp</h3>
        </a>
        <div class="VwiC3b">Acme Corp announced today that Ada Lovelace has
        been appointed Chief Technology Officer.</div>
      </div>
    </div>
    <div class="g">
      <div class="tF2Cxc">
        <a href="https://example.org/articles/ada-conference">
          <h3 class="LC20lb">Ada Lovelace speaks at conference</h3>
        </a>
        <div class="VwiC3b">Ada Lovelace gave a keynote address.</div>
      </div>
    </div>
  </div>
</body>
</html>
"""

_CONSENT_PAGE = """
<!doctype html>
<html><body><h1>Before you continue to Google Search</h1></body></html>
"""

_UNUSUAL_TRAFFIC_PAGE = """
<!doctype html>
<html><body>
<p>Our systems have detected unusual traffic from your computer network.</p>
</body></html>
"""

_CAPTCHA_PAGE = """
<!doctype html>
<html><body><form id="captcha-form">solve this puzzle</form></body></html>
"""


class _StaticResultsHandler(http.server.BaseHTTPRequestHandler):
    page_body = _RESULTS_PAGE
    path_prefix = ""

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


class _GoogleShapedResultsHandler(_StaticResultsHandler):
    page_body = _GOOGLE_SHAPED_RESULTS_PAGE


class _ConsentPageHandler(_StaticResultsHandler):
    page_body = _CONSENT_PAGE


class _UnusualTrafficPageHandler(_StaticResultsHandler):
    page_body = _UNUSUAL_TRAFFIC_PAGE


class _CaptchaPageHandler(_StaticResultsHandler):
    page_body = _CAPTCHA_PAGE


def _run_server(handler: type[http.server.BaseHTTPRequestHandler]) -> object:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def local_results_server() -> object:
    yield from _run_server(_StaticResultsHandler)


@pytest.fixture
def local_google_shaped_server() -> object:
    yield from _run_server(_GoogleShapedResultsHandler)


@pytest.fixture
def local_consent_page_server() -> object:
    yield from _run_server(_ConsentPageHandler)


@pytest.fixture
def local_unusual_traffic_server() -> object:
    yield from _run_server(_UnusualTrafficPageHandler)


@pytest.fixture
def local_captcha_server() -> object:
    yield from _run_server(_CaptchaPageHandler)


def _settings(
    port: int, tmp_path: Path, path: str = "/search", **overrides: object
) -> BrowserSearchProviderSettings:
    defaults: dict[str, object] = dict(
        search_url_template=f"http://127.0.0.1:{port}{path}?q={{query}}",
        result_container_selector="div.result",
        title_selector="h3",
        url_selector="a",
        snippet_selector="p.snippet",
        user_data_dir=str(tmp_path / "chrome-profile"),
        query_templates=('"{name}"',),
        max_retries=0,
        headless=True,
        executable_path=os.environ.get("BROWSER_SEARCH_EXECUTABLE_PATH"),
    )
    defaults.update(overrides)
    return BrowserSearchProviderSettings(**defaults)  # type: ignore[arg-type]


def _request() -> SearchRequest:
    return SearchRequest(
        request_id="e2e-1",
        subject_type=SubjectType.PERSON,
        subject_id="row:1",
        known_attributes={"first_name": "Ada", "last_name": "Lovelace"},
        requested_at=datetime.now(timezone.utc),
    )


def test_real_browser_collects_results_from_a_local_static_page(
    local_results_server: http.server.HTTPServer, tmp_path: Path
) -> None:
    port = local_results_server.server_address[1]
    settings = _settings(port, tmp_path)
    provider = BrowserSearchProvider(settings)
    try:
        response = provider.search(_request())

        assert len(response.results) == 2
        assert response.results[0].title == "Ada Lovelace named CTO of Acme Corp"
        assert response.results[0].url.endswith("/articles/ada-lovelace-cto")
        assert "Chief Technology Officer" in response.results[0].snippet
    finally:
        provider.close()


def test_real_browser_collects_results_using_the_configured_google_selectors(
    local_google_shaped_server: http.server.HTTPServer, tmp_path: Path
) -> None:
    """Regression guard for the exact selectors .env.local.example ships
    (BROWSER_SEARCH_RESULT_SELECTOR=div.g, TITLE_SELECTOR=h3,
    URL_SELECTOR=a:has(h3), SNIPPET_SELECTOR=.VwiC3b) against a REAL
    browser (launch_persistent_context) and a page shaped like Google's
    actual www.google.com/search markup — catches a selector/markup
    mismatch without ever querying the live, third-party google.com (see
    module docstring)."""

    port = local_google_shaped_server.server_address[1]
    settings = _settings(
        port,
        tmp_path,
        path="/search",
        result_container_selector="div.g",
        title_selector="h3",
        url_selector="a:has(h3)",
        snippet_selector=".VwiC3b",
    )
    provider = BrowserSearchProvider(settings)
    try:
        response = provider.search(_request())

        assert len(response.results) == 2
        assert response.results[0].title == "Ada Lovelace named CTO of Acme Corp"
        assert response.results[0].url.endswith("/articles/ada-lovelace-cto")
        assert "Chief Technology Officer" in response.results[0].snippet
    finally:
        provider.close()


def test_real_browser_detects_consent_page_and_saves_debug_artifacts(
    local_consent_page_server: http.server.HTTPServer, tmp_path: Path
) -> None:
    port = local_consent_page_server.server_address[1]
    debug_dir = tmp_path / "debug"
    settings = _settings(port, tmp_path, debug_dir=str(debug_dir))
    provider = BrowserSearchProvider(settings)
    try:
        response = provider.search(_request())

        assert response.status is EnrichmentStatus.FAILURE
        assert "consent" in (response.error_message or "").lower()
        assert list(debug_dir.glob("*consent_page*.html"))
        assert list(debug_dir.glob("*consent_page*.png"))
    finally:
        provider.close()


def test_real_browser_detects_unusual_traffic_page_and_saves_debug_artifacts(
    local_unusual_traffic_server: http.server.HTTPServer, tmp_path: Path
) -> None:
    port = local_unusual_traffic_server.server_address[1]
    debug_dir = tmp_path / "debug"
    settings = _settings(port, tmp_path, debug_dir=str(debug_dir))
    provider = BrowserSearchProvider(settings)
    try:
        response = provider.search(_request())

        assert response.status is EnrichmentStatus.FAILURE
        assert "unusual traffic" in (response.error_message or "").lower()
        assert list(debug_dir.glob("*unusual_traffic*.html"))
        assert list(debug_dir.glob("*unusual_traffic*.png"))
    finally:
        provider.close()


def test_real_browser_detects_captcha_page_and_saves_debug_artifacts(
    local_captcha_server: http.server.HTTPServer, tmp_path: Path
) -> None:
    port = local_captcha_server.server_address[1]
    debug_dir = tmp_path / "debug"
    settings = _settings(port, tmp_path, debug_dir=str(debug_dir))
    provider = BrowserSearchProvider(settings)
    try:
        response = provider.search(_request())

        assert response.status is EnrichmentStatus.FAILURE
        assert "captcha" in (response.error_message or "").lower()
        assert list(debug_dir.glob("*captcha*.html"))
        assert list(debug_dir.glob("*captcha*.png"))
    finally:
        provider.close()
