# Browser Search Provider

`BrowserSearchProvider` — the Search Layer's first concrete provider
(Version 1). Drives a real, headless browser (via Playwright) against a
search engine's own results page and collects result URLs, for engines
that have no published API. Implements
`application/ports/search_provider_port.py`'s `SearchProviderPort` —
returns `SearchResult`s only, never extracts observations or fetches a
result's destination page.

## Scope: what Version 1 does and does not do

**Does:** accept an executive's name/company/title, build a configurable
set of search queries (reusing `google_search`'s query-template engine
directly), launch a headless Chromium instance, navigate to a configured
search-results URL per query, extract up to `max_results` results per
query via configured CSS selectors, retry transient navigation failures,
cache each query's results, log every stage, and check the search
engine's own `robots.txt` before ever navigating there.

**Does not:** interpret a result's meaning, extract observations, or
fetch/crawl a result's *destination* page — that boundary is deliberate
(see "Why this provider never fetches a result's destination page"
below). Does not ship with a working default search target — see
"Why there is no built-in search engine" below. Not yet wired into
`ExecutiveProcessingOrchestrator` (see `application/search/README.md`).

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

## Why robots.txt is checked against the search engine's own domain

Following directly from the above: the one page this provider crawls is
the search results page itself, so that's the one place "respect
robots.txt for pages you crawl" applies to this class. Checked once per
provider instance (the domain never changes for a given instance), via a
plain HTTP request — never the browser — using the same
`RobotFileParser.can_fetch(user_agent, url)` pattern
`CompanyWebsiteProvider` already uses. A robots.txt that disallows the
configured URL results in `EnrichmentStatus.SUCCESS` with zero results
(compliance is not a failure) and the browser is never launched at all
for that `search()` call. A missing/unreachable robots.txt is treated as
"no restrictions" — the standard crawler convention.

## Why query building reuses `google_search.query_builder.build_queries`

That function is pure `{name}`/`{company}`/`{title}` placeholder
substitution with zero Google-specific logic — reusing it directly (no
second implementation) is exactly what "reuse the existing Search/
Enrichment architecture" means in practice. `query_templates` defaults to
the exact same set `GoogleSearchProviderSettings` ships with.

## Why the browser is launched lazily and stays alive across `search()` calls

Launching a fresh Chromium process per query would be far slower than
reusing one already-running browser across many executives in the same
run — the same reasoning `httpx.Client()` reuse already follows
elsewhere. Call `provider.close()` once done with a provider instance;
there is no `__del__`-based cleanup.

## Configuration (`settings.py`)

| Setting | Purpose |
|---|---|
| `search_url_template` | Results-page URL with a literal `{query}` placeholder. No default — see above. |
| `result_container_selector` / `title_selector` / `url_selector` | CSS selectors for one result item, its title, and its link. No default. |
| `snippet_selector` | Optional CSS selector for snippet text; blank means "no snippet available." |
| `query_templates` | Which queries to generate — defaults to `GoogleSearchProviderSettings`'s own set. |
| `max_results` | Maximum result URLs collected per query. |
| `timeout_seconds` | Per-page-navigation timeout. |
| `max_retries` / `retry_backoff_seconds` | Retry policy for transient navigation failures. |
| `cache_ttl` | How long one query's results are reused before being considered stale. |
| `headless` | Always `True` in production; togglable for local debugging. |
| `user_agent` | Sent as the browser's User-Agent, and checked against robots.txt. |
| `executable_path` | Optional explicit Chromium binary path, overriding Playwright's own resolution (see "Running the real end-to-end test," below, for when you need this). |

## Environment variables

See `.env.example`'s `BROWSER_SEARCH_*` block. `search_url_template` and
the three required selectors have no default and raise `ValueError` at
construction time if blank.

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
| `SUCCESS` | Every query succeeded — including robots.txt disallowing the search engine, and the legitimate empty case of "no results found." |

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
