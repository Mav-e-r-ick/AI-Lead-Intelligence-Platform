"""BrowserSearchProviderSettings: every knob BrowserSearchProvider needs.

WHY THIS PROVIDER HAS NO BUILT-IN, HARDCODED TARGET SEARCH ENGINE:
Unlike GoogleSearchProviderSettings (which is contractually bound to one
specific, documented API), BrowserSearchProvider drives a real browser
against whatever search results page the operator points it at.
Automating queries against a search engine's own web UI (rather than a
published API) is something only the operator can confirm they are
authorized to do for their chosen target — this settings object
deliberately requires `search_url_template` and every CSS selector to be
supplied explicitly (no default that silently points at a real, named
vendor), and fails fast in `validate()` if they're blank, exactly like
GoogleSearchProviderSettings.api_key/search_engine_id.

WHY QUERY TEMPLATES REUSE GoogleSearchProviderSettings' EXACT DEFAULTS:
`{name}`/`{company}`/`{title}` placeholder templates, filled by the same
`build_queries()` this platform already has (infrastructure/enrichment/
google_search/query_builder.py) — a search provider's job of "what
queries should I run for this executive" doesn't change based on which
engine executes them, so the default set stays identical rather than
inventing a second, parallel default.

WHY from_env() EXISTS, SEPARATE FROM THE DATACLASS ITSELF:
Mirrors GoogleSearchProviderSettings.from_env() / NeverBounceSettings.from_env():
reading `os.environ` directly inside the dataclass would make every test
either mutate real process environment variables or monkeypatch
`os.environ`. Instead, `from_env()` takes an injectable `env` mapping
(defaulting to `os.environ`), so tests can pass a plain dict.

WHY user_data_dir IS REQUIRED (LIKE search_url_template/THE SELECTORS):
provider.py launches via Playwright's `launch_persistent_context()`, not
`launch()` — see provider.py's module docstring for why (using the
operator's real, already-signed-in Chrome profile). A persistent context
launch takes `user_data_dir` as a required positional argument; there is
no meaningful default (pointing at nothing, or at a stranger's profile,
isn't a sane fallback the way DuckDuckGo's URL/selectors were before), so
this fails fast in `validate()` exactly like the other operator-supplied
fields.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Mapping

from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    DEFAULT_QUERY_TEMPLATES,
)

#: Environment variables this provider reads via from_env(). No default
#: value is provided for the first four — see module docstring for why.
BROWSER_SEARCH_URL_TEMPLATE_ENV_VAR = "BROWSER_SEARCH_URL_TEMPLATE"
BROWSER_SEARCH_RESULT_SELECTOR_ENV_VAR = "BROWSER_SEARCH_RESULT_SELECTOR"
BROWSER_SEARCH_TITLE_SELECTOR_ENV_VAR = "BROWSER_SEARCH_TITLE_SELECTOR"
BROWSER_SEARCH_URL_SELECTOR_ENV_VAR = "BROWSER_SEARCH_URL_SELECTOR"
BROWSER_SEARCH_SNIPPET_SELECTOR_ENV_VAR = "BROWSER_SEARCH_SNIPPET_SELECTOR"
BROWSER_SEARCH_MAX_RESULTS_ENV_VAR = "BROWSER_SEARCH_MAX_RESULTS"
BROWSER_SEARCH_HEADLESS_ENV_VAR = "BROWSER_SEARCH_HEADLESS"
BROWSER_SEARCH_EXECUTABLE_PATH_ENV_VAR = "BROWSER_SEARCH_EXECUTABLE_PATH"
BROWSER_SEARCH_DEBUG_DIR_ENV_VAR = "BROWSER_SEARCH_DEBUG_DIR"
BROWSER_SEARCH_USER_DATA_DIR_ENV_VAR = "BROWSER_SEARCH_USER_DATA_DIR"

#: The `{query}` placeholder every search_url_template must contain — the
#: fully-built query string (after query_templates substitution) is
#: URL-encoded and substituted in here.
_QUERY_PLACEHOLDER = "{query}"


@dataclass(frozen=True)
class BrowserSearchProviderSettings:
    """Immutable, typed configuration for one BrowserSearchProvider instance.

    Attributes:
        search_url_template: The search engine results page URL, with a
            literal `{query}` placeholder (e.g.
            "https://searx.example.org/search?q={query}"). The operator
            is responsible for confirming they are authorized to automate
            queries against whatever engine this points at, and that its
            robots.txt allows the configured `user_agent` to do so — this
            provider checks robots.txt (see provider.py) but cannot verify
            legal/contractual authorization on the operator's behalf.
        result_container_selector: CSS selector matching one repeated
            "result item" element on the results page (e.g.
            "div.result").
        title_selector: CSS selector, evaluated within each result
            container, for the result's title text.
        url_selector: CSS selector, evaluated within each result
            container, for the anchor element whose `href` is the
            result's URL.
        user_data_dir: Filesystem path to a real Chrome user-data
            directory (see provider.py's module docstring). Launched via
            `launch_persistent_context()`, not `launch()`, so the
            resulting session carries that profile's cookies, browsing
            history, and signed-in state. No default — see module
            docstring on why this is required. Safe to point at Chrome's
            actual default profile root (e.g. Windows' default
            Google/Chrome/"User Data" folder) — provider.py's
            `_resolve_automation_user_data_dir()` recognizes that exact
            directory and automatically launches against a dedicated
            "PlaywrightProfile" subdirectory instead, never the real
            default profile: Chrome itself refuses DevTools remote
            debugging against its default profile at all ("DevTools
            remote debugging requires a non-default data directory"),
            and this also sidesteps Chrome's "already running"
            single-instance lock, since that subdirectory starts out
            unused by any other Chrome instance.
        snippet_selector: CSS selector, evaluated within each result
            container, for the result's snippet text. Optional — a blank
            value means "this results page has no snippet text";
            `snippet` is then reported as an empty string, never omitted.
        query_templates: Which queries to generate per executive — see
            module docstring. Same placeholder rules as
            GoogleSearchProviderSettings.query_templates.
        max_results: Maximum number of result URLs collected per query.
        timeout_seconds: Per-page-navigation timeout (page load, not just
            the initial HTTP response — browser automation waits for the
            page to actually render).
        max_retries: How many additional attempts are made after an
            initial failed navigation (timeout, navigation error) before
            giving up on that one query.
        retry_backoff_seconds: Base delay before a retry; multiplied by
            the attempt number for simple linear backoff.
        cache_ttl: How long a query's results are reused from cache before
            being considered stale and re-searched.
        headless: Whether the browser runs without a visible window.
            Always True in production; togglable for local debugging.
        user_agent: Sent as the browser's User-Agent, and checked against
            the search engine's own robots.txt via the same
            `user_agent`/`can_fetch` pattern CompanyWebsiteProvider uses.
        executable_path: Explicit path to the browser executable
            `launch_persistent_context()` runs — for this provider's
            intended use (the operator's real, already-installed Google
            Chrome, not Playwright's bundled Chromium), this should point
            directly at that Chrome binary. Optional; blank falls back to
            Playwright's own resolution (its bundled Chromium).
        debug_dir: Directory a query's rendered page HTML and a
            screenshot are saved to whenever that query's selectors yield
            zero results (the page loaded, but nothing matched
            `result_container_selector`/`title_selector`/`url_selector`).
            This is what makes "the search engine changed its markup" or
            "the search engine served a bot-check/empty page" diagnosable
            after the fact, without re-running with a debugger attached.
            Blank disables saving. Default: "browser_search_debug"
            (created if missing).
    """

    search_url_template: str
    result_container_selector: str
    title_selector: str
    url_selector: str
    user_data_dir: str
    snippet_selector: str = ""
    query_templates: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_QUERY_TEMPLATES
    )
    max_results: int = 10
    timeout_seconds: float = 15.0
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    cache_ttl: timedelta = timedelta(hours=6)
    headless: bool = True
    user_agent: str = (
        "AILeadIntelligenceBot/1.0 (+https://example.com/bot; search research)"
    )
    executable_path: str | None = None
    debug_dir: str = "browser_search_debug"

    def validate(self) -> None:
        """Raise ValueError if this settings object is self-contradictory.

        Called once, at provider construction time — a misconfigured
        provider should fail immediately, not on its first search.
        """

        if not self.search_url_template.strip():
            raise ValueError(
                "BrowserSearchProviderSettings.search_url_template must not be "
                f"blank. Set the {BROWSER_SEARCH_URL_TEMPLATE_ENV_VAR} "
                "environment variable to a URL containing a '{query}' placeholder."
            )
        if _QUERY_PLACEHOLDER not in self.search_url_template:
            raise ValueError(
                "BrowserSearchProviderSettings.search_url_template must contain "
                f"a literal '{_QUERY_PLACEHOLDER}' placeholder, got: "
                f"{self.search_url_template!r}."
            )
        if not self.result_container_selector.strip():
            raise ValueError(
                "BrowserSearchProviderSettings.result_container_selector must "
                f"not be blank. Set the "
                f"{BROWSER_SEARCH_RESULT_SELECTOR_ENV_VAR} environment variable."
            )
        if not self.title_selector.strip():
            raise ValueError(
                "BrowserSearchProviderSettings.title_selector must not be "
                f"blank. Set the {BROWSER_SEARCH_TITLE_SELECTOR_ENV_VAR} "
                "environment variable."
            )
        if not self.url_selector.strip():
            raise ValueError(
                "BrowserSearchProviderSettings.url_selector must not be blank. "
                f"Set the {BROWSER_SEARCH_URL_SELECTOR_ENV_VAR} environment "
                "variable."
            )
        if not self.user_data_dir.strip():
            raise ValueError(
                "BrowserSearchProviderSettings.user_data_dir must not be blank "
                "— launch_persistent_context() requires a real Chrome user-data "
                f"directory. Set the {BROWSER_SEARCH_USER_DATA_DIR_ENV_VAR} "
                "environment variable."
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                "BrowserSearchProviderSettings.timeout_seconds must be > 0, "
                f"got {self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "BrowserSearchProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "BrowserSearchProviderSettings.retry_backoff_seconds must be "
                f">= 0, got {self.retry_backoff_seconds}."
            )
        if self.max_results < 1:
            raise ValueError(
                "BrowserSearchProviderSettings.max_results must be >= 1, got "
                f"{self.max_results}."
            )
        if self.cache_ttl < timedelta(0):
            raise ValueError(
                "BrowserSearchProviderSettings.cache_ttl must not be negative, "
                f"got {self.cache_ttl}."
            )
        if not self.query_templates:
            raise ValueError(
                "BrowserSearchProviderSettings.query_templates must not be empty."
            )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **overrides: object
    ) -> BrowserSearchProviderSettings:
        """Build settings from environment variables.

        Args:
            env: Mapping to read the `BROWSER_SEARCH_*` variables from.
                Defaults to the real process environment (`os.environ`);
                pass a plain dict in tests.
            **overrides: Any other `BrowserSearchProviderSettings` field
                (e.g. `max_results=5`), for callers who want everything
                else from the environment but one field overridden.

        Returns:
            A BrowserSearchProviderSettings built from whichever
            `BROWSER_SEARCH_*` variables are present. `validate()` is not
            called here — call it once the provider is constructed, same
            as every other settings object in this codebase.
        """

        source = env if env is not None else os.environ
        kwargs: dict[str, object] = {
            "search_url_template": source.get(BROWSER_SEARCH_URL_TEMPLATE_ENV_VAR, ""),
            "result_container_selector": source.get(
                BROWSER_SEARCH_RESULT_SELECTOR_ENV_VAR, ""
            ),
            "title_selector": source.get(BROWSER_SEARCH_TITLE_SELECTOR_ENV_VAR, ""),
            "url_selector": source.get(BROWSER_SEARCH_URL_SELECTOR_ENV_VAR, ""),
            "user_data_dir": source.get(BROWSER_SEARCH_USER_DATA_DIR_ENV_VAR, ""),
            "snippet_selector": source.get(BROWSER_SEARCH_SNIPPET_SELECTOR_ENV_VAR, ""),
        }
        max_results = source.get(BROWSER_SEARCH_MAX_RESULTS_ENV_VAR)
        if max_results is not None:
            kwargs["max_results"] = int(max_results)
        headless = source.get(BROWSER_SEARCH_HEADLESS_ENV_VAR)
        if headless is not None:
            kwargs["headless"] = headless.strip().lower() not in ("false", "0", "no")
        executable_path = source.get(BROWSER_SEARCH_EXECUTABLE_PATH_ENV_VAR)
        if executable_path:
            kwargs["executable_path"] = executable_path
        debug_dir = source.get(BROWSER_SEARCH_DEBUG_DIR_ENV_VAR)
        if debug_dir is not None:
            kwargs["debug_dir"] = debug_dir
        kwargs.update(overrides)
        return cls(**kwargs)  # type: ignore[arg-type]
