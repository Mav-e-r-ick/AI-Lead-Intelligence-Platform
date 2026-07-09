# Browser Search Provider

`BrowserSearchProvider` — the Search Layer's first concrete provider
(Version 1). Drives the operator's own, real Google Chrome (via
Playwright's `launch_persistent_context()`, against that Chrome's real
user-data directory) against a search engine's own results page and
collects result URLs, for engines that have no published API. Implements
`application/ports/search_provider_port.py`'s `SearchProviderPort` —
returns `SearchResult`s only, never extracts observations or fetches a
result's destination page.

## Scope: what Version 1 does and does not do

**Does:** accept an executive's name/company/title, build a configurable
set of search queries (reusing `google_search`'s query-template engine
directly), launch the operator's real Chrome against their real profile
(`launch_persistent_context()`, cookies/history/signed-in state intact),
and — per query — search the way a person would: open the target's
homepage, wait for it, accept a consent dialog if one appears, click the
search box, type the query with randomized per-character delays, press
Enter, wait for results, and scroll a little before extraction (see "How
the human-like search flow works," below). Detects consent/CAPTCHA/
"unusual traffic" interstitial pages, extracts up to `max_results` results
per query via configured CSS selectors, retries transient navigation
failures, caches each query's results, logs every stage, saves debug
artifacts (HTML + screenshot) whenever a query doesn't yield real results,
and checks (but no longer acts on) the search engine's own `robots.txt` —
see "Why robots.txt is checked but no longer blocks execution," below.

**Does not:** interpret a result's meaning, extract observations, or
fetch/crawl a result's *destination* page — that boundary is deliberate
(see "Why this provider never fetches a result's destination page"
below). Does not ship with a working default search target — see
"Why there is no built-in search engine" below. Wired into
`ExecutiveProcessingOrchestrator` as of that module's Version 2 (see
`application/executive_pipeline/README.md`).

## Why there is no built-in search engine

Unlike `GoogleSearchProvider` (bound to one documented, sanctioned API),
this provider automates a real browser against a search engine's own web
UI. Only the operator can confirm they're authorized to do that for their
chosen target (terms of service, rate limits) — `settings.py` requires
`search_url_template` and every CSS selector to be supplied explicitly,
and fails fast (`ValueError`) if they're blank. There is no vendor named
"the" default; `.env.example` shows a self-hosted metasearch instance
(SearXNG) purely as a *shape* example, not an endorsed target.

## Why this provider never fetches a result's destination page

Per the approved Search Layer RFC, this is a deliberate Version 1 scope
boundary, not an oversight: fetching arbitrary third-party pages (news
sites, LinkedIn, press releases) that a search turns up has different
robots.txt/legal exposure than fetching a company's own homepage
(`CompanyWebsiteProvider`'s job), and is real new scope, not a refactor.
The only page this class itself ever navigates to is the configured
search engine's own results page.

## Why robots.txt is checked but no longer blocks execution (changed)

`_robots_allow_search()`/`_can_fetch_configured_url()` are unchanged —
still one plain HTTP request per provider instance (never the browser),
still `RobotFileParser.can_fetch(user_agent, url)`, still "missing/
unreachable robots.txt means no restrictions." What changed is what
`search()` *does* with the answer: previously, a disallowed target made
it return immediately with `EnrichmentStatus.SUCCESS` and zero results,
without ever launching the browser. Now it only logs a `WARNING` and
proceeds. This is a deliberate choice: robots.txt is a convention aimed
at automated crawlers, and this provider now drives the operator's own,
real, signed-in browser through the same interaction sequence a human
uses — not a bot hitting the target programmatically. It is still your
responsibility to confirm you're authorized to automate your chosen
target (and that doing so doesn't violate its Terms of Service, which is
a separate question from robots.txt) before relying on this.

## How the human-like search flow works

`_search_single_query()` no longer navigates straight to a pre-built
results URL. Instead, `_perform_human_like_search()` drives the page
through the same steps a person takes, before `extract_results()` (from
`extraction.py`, itself unchanged) ever runs:

1. Open the target's homepage — derived from `search_url_template`'s own
   scheme+host (e.g. `https://www.google.com/search?q={query}` →
   `https://www.google.com/`), so this needed no new, Google-specific
   setting.
2. Wait for it to load (`wait_for_load_state`), then a randomized pause.
3. If `_detect_interstitial()` reports a consent page, try clicking a
   known "accept" control (`_CONSENT_ACCEPT_SELECTORS` — Google's own
   long-stable `#L2AGLb` id, plus a couple of generic-wording fallbacks).
   Logs a warning and continues either way — a consent page that
   couldn't be dismissed is still caught by the interstitial check in
   step 7.
4. Locate the search box (`_SEARCH_BOX_SELECTORS` — Google's current
   `textarea[name='q']`, its legacy `input[name='q']`, and the generic
   `input[type='search']` most other engines use), click it.
5. Type the query one character at a time with a randomized delay per
   character (`_TYPING_DELAY_RANGE_S`), then press Enter.
6. Wait for the configured `result_container_selector` to appear
   (`wait_for_selector`, tolerant of a timeout — absence is handled by
   the interstitial check/`extract_results()` that follow, not treated
   as fatal here), then a randomized pause.
7. A small, randomized number of scroll steps (`page.mouse.wheel`).

Back in `_search_single_query()`: `_detect_interstitial()` is checked
again — a consent page that couldn't be dismissed, or a CAPTCHA/"unusual
traffic" page that appeared only after submitting the search, is still
funneled into the exact same retry-then-fail path as before (via
`_InterstitialPageDetected`), with debug artifacts saved the same way. A
homepage with no recognizable search box raises `_SearchBoxNotFound`,
which is handled identically to a navigation timeout — retried, then
reported as this query's failure reason.

None of the randomized delay ranges or the selector lists above are
settings — see "Only change what is necessary" in this feature's task
description; they're module-level constants in `provider.py`, easy to
promote to settings later if an operator needs to tune them.

## Why query building reuses `google_search.query_builder.build_queries`

That function is pure `{name}`/`{company}`/`{title}` placeholder
substitution with zero Google-specific logic — reusing it directly (no
second implementation) is exactly what "reuse the existing Search/
Enrichment architecture" means in practice. `query_templates` defaults to
the exact same set `GoogleSearchProviderSettings` ships with.

## Why the browser is launched lazily and stays alive across `search()` calls

Launching a fresh Chrome process per query would be far slower than
reusing one already-running browser across many executives in the same
run — the same reasoning `httpx.Client()` reuse already follows
elsewhere. Call `provider.close()` once done with a provider instance;
there is no `__del__`-based cleanup.

## Why `launch_persistent_context()` instead of `launch()`

`launch()` starts a fresh, throwaway profile every time — no cookies, no
history, always logged out, and far more obviously automated to a search
engine's bot detection than a real person's browser. Google in particular
treats a browser with a real, aged, signed-in profile very differently
from a bare-fresh instance. `launch_persistent_context(user_data_dir, ...)`
launches directly against a real Chrome profile directory and returns a
`BrowserContext` (there is no separate `Browser` object for a persistent
context) — see `provider.py`'s module docstring and `_PlaywrightBrowser`.

**Never against the operator's actual, default profile, though.** Chrome
itself refuses DevTools remote debugging against its own real default
profile directory ("DevTools remote debugging requires a non-default
data directory"), and even if it didn't, this provider shouldn't ever
require handing over an operator's everyday browsing session just to
search. `_resolve_automation_user_data_dir()` recognizes Chrome's actual
default profile-root basename on each platform ("User Data" on Windows,
"Chrome" on macOS, "google-chrome" on Linux) and transparently redirects
to a dedicated `PlaywrightProfile` subdirectory instead — created
automatically, never something the operator has to set up by hand.

**Exactly one `sync_playwright()` session alive at a time.** The browser
is meant to be launched once per provider instance and reused across
every query and retry (see "Why the browser is launched lazily," above).
`_default_browser_factory()`'s `factory()` wraps
`launch_persistent_context()` in try/except and stops its just-started
driver before re-raising on any failure — without that, a failed launch
(the default-profile rejection above, a bad `executable_path`, anything)
would leave its driver connection running, un-stopped, and the next
retry would start a *second* `sync_playwright()` session while the first
was still alive: exactly what Playwright's sync API raises "It looks
like you are using Playwright Sync API inside the asyncio loop" for.

## Configuration (`settings.py`)

| Setting | Purpose |
|---|---|
| `search_url_template` | Results-page URL with a literal `{query}` placeholder. No default — see above. |
| `result_container_selector` / `title_selector` / `url_selector` | CSS selectors for one result item, its title, and its link. No default. |
| `user_data_dir` | Real Chrome user-data directory, launched via `launch_persistent_context()`. No default — required, see settings.py. |
| `snippet_selector` | Optional CSS selector for snippet text; blank means "no snippet available." |
| `query_templates` | Which queries to generate — defaults to `GoogleSearchProviderSettings`'s own set. |
| `max_results` | Maximum result URLs collected per query. |
| `timeout_seconds` | Per-page-navigation timeout. |
| `max_retries` / `retry_backoff_seconds` | Retry policy for transient navigation failures (also covers a detected consent/CAPTCHA/unusual-traffic interstitial — see below). |
| `cache_ttl` | How long one query's results are reused before being considered stale. |
| `headless` | Togglable; `.env.local.example` defaults this to `false` (see why in that file). |
| `user_agent` | Sent as the browser's User-Agent, and checked against robots.txt. |
| `executable_path` | Path to the real browser executable `launch_persistent_context()` runs — for this provider's intended use, your real, already-installed Google Chrome (not Playwright's bundled Chromium). Optional; blank falls back to Playwright's own resolution. |
| `debug_dir` | Directory a query's rendered HTML + a screenshot are saved to whenever its selectors yield zero results, or a consent/CAPTCHA/unusual-traffic page is detected. Blank disables saving. Default: `"browser_search_debug"`. |

## Detecting consent/CAPTCHA/"unusual traffic" pages

Google serves these in place of real results but still returns HTTP 200
and a normal-looking page — `extract_results()` alone would just report
"zero results" with no indication why, and every subsequent query in the
same run would likely hit the exact same interstitial.
`provider.py`'s `_detect_interstitial()` checks the navigated page's URL
and content for each, right after `page.goto()` and before extraction:

| Detected as | Signal |
|---|---|
| `consent_page` | URL host is `consent.google.com`, or the page contains "before you continue to Google" |
| `unusual_traffic` | URL path contains `/sorry/` (or the page contains "captcha"/"recaptcha") *and* the page text contains "unusual traffic"; or "unusual traffic" appears in the page regardless of URL |
| `captcha` | URL path contains `/sorry/` (or the page contains a `captcha-form`/`recaptcha`), without "unusual traffic" text |

A detected interstitial is treated as a failed attempt for that query —
routed through the exact same retry/backoff/give-up logic as a navigation
timeout (see `_InterstitialPageDetected`), and its `reason` is included in
both the saved debug filenames and `SearchResponse.error_message`.

## Diagnosing "0 results" (or an interstitial) on a real page

The page loading successfully does not mean the configured selectors still
match it, or that Google served real results at all. Two things make this
diagnosable without re-running under a debugger:

1. **Logging** (`extraction.py`): every zero-result extraction logs
   *which* selector produced nothing — "the container selector matched 0
   elements" (the page didn't render results, or `result_container_selector`
   is stale) versus "the container selector matched N elements, but none
   had a usable title/URL" (`title_selector`/`url_selector` is stale).
2. **Saved artifacts** (`debug_dir`, provider.py's `_save_debug_artifacts`):
   the exact rendered HTML and a screenshot, timestamped and labeled with
   the reason (`zero_results`/`consent_page`/`captcha`/`unusual_traffic`),
   so you can open them and compare against the configured selectors
   directly — see `.env.local.example`'s `BROWSER_SEARCH_DEBUG_DIR`.

`tests/integration/test_browser_search_e2e.py`'s
`test_real_browser_collects_results_using_the_configured_google_selectors`
regression-guards the exact selectors `.env.local.example` ships
(`div.g` / `h3` / `a:has(h3)` / `.VwiC3b`) against a real browser and a
page shaped like Google's actual `www.google.com/search` markup; three
more tests in that file do the same for each interstitial type — run them
with `RUN_BROWSER_SEARCH_E2E=1` (see "Running the real end-to-end test,"
below). If a real, live Google search still returns 0 results after these
pass, the page Google served that day differs from these fixtures (a
template change, or an interstitial variant not covered above) — the
saved HTML/screenshot from `debug_dir` will show which.

## Environment variables

See `.env.example`'s `BROWSER_SEARCH_*` block. `search_url_template`, the
three required selectors, and `user_data_dir` have no default and raise
`ValueError` at construction time if blank. For running this provider on
a developer laptop specifically, `.env.local.example` (repo root)
pre-fills a working Google-based configuration — see `LOCAL_SETUP.md` for
the full walkthrough (`setup_local.py`, `run_local.py`, Development
Mode).

## Why a failed fetch's error message includes the failure reason

`fetch()`/`search()` include *why* a fetch failed (an HTTP status, or
`"connection error: ..."`/`"navigation error: ..."` for anything that
never got a response at all) in `EnrichmentResponse.error_message`/
`SearchResponse.error_message`, not just that it failed. This has one
purpose beyond better log messages: `run_pipeline.py`'s Development Mode
(`--dev-mode`) classifies a failure as a network-policy problem (a
blocked connection, DNS failure, or an HTTP 403 at the connect/robots
stage) versus a genuine content-level failure entirely from this string —
see `run_pipeline.py`'s own `_is_network_policy_failure` for the exact,
narrow set of markers it looks for. `_get()`/`_search_single_query()`
still return only `str | None`/`tuple[SearchResult, ...] | None` as
before; the reason is stashed on a private, single-read instance
attribute (`_last_fetch_failure`/`_last_query_failure`) read immediately
by the caller that already builds the response — no new return type, no
new parameter, no change to either class's public shape.

```python
from lead_intelligence.infrastructure.search.browser.provider import (
    BrowserSearchProvider,
)
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)

provider = BrowserSearchProvider(BrowserSearchProviderSettings.from_env())
try:
    ...
finally:
    provider.close()
```

## `EnrichmentStatus` (reused from the Enrichment Provider Framework)

| Status | When |
|---|---|
| `FAILURE` | No executive name was available, no queries could be built, or every query genuinely failed (after retries). |
| `PARTIAL` | At least one query succeeded and at least one query failed. |
| `SUCCESS` | Every query succeeded, including the legitimate empty case of "no results found." (robots.txt disallowing the target no longer forces this on its own — see "Why robots.txt is checked but no longer blocks execution.") |

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `BrowserSearchProvider` — the `SearchProviderPort` implementation; orchestrates query building, robots.txt, retry-guarded browser navigation, and result extraction. |
| `settings.py` | `BrowserSearchProviderSettings` — search URL template, CSS selectors, query templates, retry/timeout/cache policy, headless flag; `from_env()`. |
| `cache.py` | `SearchResultCache`, `InMemorySearchResultCache` — TTL-based per-query result reuse (same shape as `google_search/cache.py`, keyed on the canonical `SearchResult`). |
| `extraction.py` | `extract_results` — parses a rendered results page (via `PageLike`/`ElementLike` structural types, satisfied by a real Playwright `Page` or a test fake) into `SearchResult`s. |

## Testing

### Mocked unit tests (`tests/unit/browser_search/`)

Every unit test uses a fake, in-memory `Browser`/`Page`
(`fixtures.py`'s `FakeBrowser`/`FakePage`/`FakeElement`) and a mocked
`httpx` transport for the robots.txt check — **no test here launches a
real browser or touches the real network.** Covers: settings validation
and `from_env()`, cache TTL behavior, extraction (title/URL/snippet/rank,
relative-URL resolution, missing-field skipping, the `max_results`
first-N-successful-results semantics), and an end-to-end provider suite
(missing-name handling, successful multi-query search, every page opened
being closed, caching across repeated searches, retry-then-succeed and
retry-exhausted behavior, partial-success status, robots.txt allow/
disallow/missing, robots.txt fetched only once per instance, and
`close()`).

### Running the real end-to-end test

`tests/integration/test_browser_search_e2e.py` launches a **real**
Playwright/Chromium browser against a **real, local** static HTML page
(served over `127.0.0.1` by Python's own `http.server`) — never a live
third-party search engine. It's skipped by default (every other test in
this repository is fast and network-free); opt in with:

```bash
pip install -r requirements.txt   # installs the playwright package
playwright install chromium       # downloads a matching Chromium build,
                                   # if one isn't already available

RUN_BROWSER_SEARCH_E2E=1 pytest tests/integration/test_browser_search_e2e.py -v
```

If your environment already has a Chromium binary that doesn't match the
revision Playwright's own installer expects (this happens in some
sandboxed/pre-provisioned environments), point `executable_path`
explicitly instead of running `playwright install`:

```bash
RUN_BROWSER_SEARCH_E2E=1 \
BROWSER_SEARCH_EXECUTABLE_PATH=/path/to/your/chrome \
pytest tests/integration/test_browser_search_e2e.py -v
```

This exact second form is how this test was verified during development,
against this platform's own pre-provisioned Chromium build.

### Testing against a real, authorized search engine

This repository does not include a test against any live third-party
search engine, and none should be added without first confirming
authorization to automate queries against it (see "Why there is no
built-in search engine," above). To try `BrowserSearchProvider` against a
real, authorized target locally:

```bash
export BROWSER_SEARCH_URL_TEMPLATE="https://your-authorized-engine.example/search?q={query}"
export BROWSER_SEARCH_RESULT_SELECTOR="..."   # inspect the page's real DOM
export BROWSER_SEARCH_TITLE_SELECTOR="..."
export BROWSER_SEARCH_URL_SELECTOR="..."
export BROWSER_SEARCH_USER_DATA_DIR="/path/to/a/real/chrome/profile"

python3 -c "
from datetime import datetime, timezone
from lead_intelligence.application.dto.search_models import SearchRequest, SubjectType
from lead_intelligence.infrastructure.search.browser.provider import BrowserSearchProvider
from lead_intelligence.infrastructure.search.browser.settings import BrowserSearchProviderSettings

provider = BrowserSearchProvider(BrowserSearchProviderSettings.from_env())
try:
    request = SearchRequest(
        request_id='manual-1', subject_type=SubjectType.PERSON, subject_id='row:1',
        known_attributes={'first_name': 'Ada', 'last_name': 'Lovelace'},
        requested_at=datetime.now(timezone.utc),
    )
    response = provider.search(request)
    print(response.status, len(response.results))
    for result in response.results[:5]:
        print(result)
finally:
    provider.close()
"
```
