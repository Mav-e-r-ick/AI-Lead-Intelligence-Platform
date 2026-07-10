# Company Crawler Provider

`CompanyCrawlerProvider` — the Search Layer's primary provider (Version 1),
replacing `BrowserSearchProvider` in that role. Instead of querying a
third-party search engine, it opens the executive's own company website
(the URL already on file for that row) and crawls its internal links,
prioritizing pages whose path or link text suggest leadership, management,
executive, board, about, team, people, press, or news content. Implements
`application/ports/search_provider_port.py`'s `SearchProviderPort` — like
`BrowserSearchProvider` before it, it returns `SearchResult`s only (one per
crawled priority page); the existing, unmodified `SearchExtractionEngine`
is still what fetches each of those URLs and turns them into
`ObservationCandidate`s (see `run_pipeline.py`'s wiring, below). No AI, no
LLM, no paid API — link prioritization and fact extraction are both plain,
deterministic regex/DOM logic, same floor as every other provider in this
platform.

## Scope: what Version 1 does and does not do

**Does:** read the company URL from `SearchRequest.known_attributes[fc.URL]`
(the same `known_attributes` key `CompanyWebsiteProvider` already reads),
check the site's `robots.txt`, open the homepage, extract and score its
internal links (`link_prioritization.py`), breadth-first crawl up to
`max_depth` hops and `max_pages` pages, and return up to `max_results`
`SearchResult`s — one per successfully crawled priority page — for
`SearchExtractionEngine` to fetch and extract facts from downstream.

**Does not:** call an LLM, call a paid API, or do its own fact extraction
— see "Division of labor with SearchExtractionEngine," below. Does not
follow off-domain links, paginated careers listings, or login/privacy/
product pages (`link_prioritization.py`'s exclusion list). Does not treat
the homepage itself as a result (see `crawler.py`'s module docstring). Does
not persist or cache crawled pages between provider instances (see "Why
there is no page cache," below).

## Why `SubjectType.PERSON`, not `SubjectType.COMPANY` (unlike `CompanyWebsiteProvider`)

`CompanyWebsiteProvider` is an `EnrichmentProviderPort` registered with
`EnrichmentCoordinator`, invoked at company granularity. This provider is a
`SearchProviderPort` registered with `SearchCoordinator`, invoked once per
*executive* — the exact same PERSON-scoped call `BrowserSearchProvider`
always answered. The company's URL is simply one of that executive's
`known_attributes`, not a separate subject in its own right here.

## Division of labor with `SearchExtractionEngine` (unchanged, widened)

Per the approved Search Layer RFC, URL discovery and fact extraction are
two separate stages, and this task's instruction — "convert extracted data
into ObservationCandidates using the existing SearchExtractionEngine" —
means this provider must stay a discovery-only `SearchProviderPort`, not
grow its own parallel extraction path. `SearchExtractionEngine` itself was
*not* redesigned; its fact vocabulary was widened (`engine.py`'s
`_FACT_ATTRIBUTES`, `fact_extraction.py`'s `extract_facts`) to also produce
`email`, `phone`, `linkedin_url`, and `published_at` — fields a leadership/
team page routinely has that the search-result announcement pages
`BrowserSearchProvider` targeted usually didn't need. This was verified
safe without touching the protected Comparison Engine: any attribute name
Comparison has no explicit field mapping for resolves to
`ComparisonStatus.UNKNOWN` rather than erroring, and `email`/`phone` are
already proven-compatible attribute names since `CompanyWebsiteProvider`
emits them today.

**Known, accepted Version 1 limitation:** `fact_extraction.py` reports at
most one name/title/company fact set and one email/phone/LinkedIn URL per
page (the first found) — a team page listing many people yields only one
contact set, not one per person. `CompanyWebsiteProvider`'s own
per-container extraction is the richer tool for that case; widening this
provider's extraction to match was out of scope for "keep
SearchExtractionEngine" (see `fact_extraction.py`'s own docstring for the
full limitation list).

## Link prioritization (`link_prioritization.py`)

A link's path and visible text are scored by how many `PRIORITY_KEYWORDS`
they contain (`leadership`, `management`, `executive`, `executives`,
`board`, `about`, `team`, `people`, `press`, `news` — one point each, no
weighting); a score of 0 means "not a candidate," not "excluded." Links
matching `login`/`log-in`/`signin`/`sign-in`/`privacy`/`product`, or a
*paginated* careers listing (`career` + a `/page/2`-shaped path — a bare
`/careers` page is left alone, just unlikely to score), are excluded
outright regardless of score. Only same-domain links are followed. This is
a deliberate **sibling** to `company_website/page_discovery.py`, not a
reuse of it — see `link_prioritization.py`'s own docstring for why
changing that module's keyword list instead would have silently altered
`CompanyWebsiteProvider`'s own unrelated behavior.

## Why breadth-first, bounded by `max_depth` and `max_pages`

A "Team" or "Press" link often lives one hop deeper than the homepage
(only linked from an "About" page) — homepage-only discovery would miss
it. Crawling breadth-first (not depth-first) means the highest-scoring,
shallowest candidates are always exhausted before spending budget on
deeper, lower-confidence ones. Both bounds exist for the same reason
`CompanyWebsiteProvider`'s own `max_leadership_pages` does: keep one
crawl's cost and duration bounded and deterministic, never open-ended.
`max_results` is enforced independently of `max_pages` — a crawl may visit
more pages than it ultimately reports, if some visited pages scored zero
after being fetched.

## Why the homepage itself is never returned as a result

The homepage is the crawl's starting point, used only to discover links —
matching `CompanyWebsiteProvider`'s own precedent of fetching the homepage
purely to find leadership-page candidates, never treating it as executive-
information evidence in itself. A `SearchResult` here means "this specific
page plausibly has executive information on it," which the undifferentiated
homepage usually doesn't.

## Why robots.txt is respected here (unlike `BrowserSearchProvider`'s Google target)

`BrowserSearchProvider` automates the *operator's own* real, signed-in
browser against a search engine they've chosen to use — a human-using-
their-own-tools case (see that provider's own README for why its
robots.txt check no longer blocks execution). This provider instead crawls
arbitrary *third-party companies'* own websites, at dataset scale — the
textbook case robots.txt exists for, and exactly what `CompanyWebsiteProvider`
already does today. A robots.txt disallow is policy-compliant behavior,
not a failure: reported as `EnrichmentStatus.SUCCESS` with zero results,
browser never launched for that request.

## Why `launch()`, not `launch_persistent_context()`

Crawling a company's own public site is not adversarial the way querying
Google is — there is no bot-detection/profile-realism problem to solve, so
none of `BrowserSearchProvider`'s persistent-profile machinery (real
Chrome profile, default-profile redirection, human-like typing/scrolling)
applies or is needed here. A fresh, throwaway Chromium instance per
provider lifetime is simpler and exactly sufficient. The browser is still
launched lazily and reused across every `search()` call on one provider
instance (same reasoning as `BrowserSearchProvider`'s own README) —
`close()` must be called once the caller is done with this provider. The
same driver-leak-safe launch pattern applies: `_default_browser_factory()`
wraps `driver.chromium.launch(...)` in try/except and stops the just-started
driver before re-raising on any failure, so a failed launch never leaves an
orphaned `sync_playwright()` session running for the next retry to collide
with.

## Why there is no page cache

Unlike `BrowserSearchProvider`'s per-query result cache, this provider
fetches each page at most once per crawl already (`seen`/`already_seen`
dedupe pages within a single `crawl_company_site()` call), and there is no
cross-request reuse scenario analogous to "the same search query asked
twice" — each `search()` call targets a different executive's (usually
different) company URL. Adding a cache layer with nothing to exercise it
would be scaffolding, not a real capability.

## Configuration (`settings.py`)

Unlike `BrowserSearchProviderSettings` (which requires every value
explicitly — automating a browser against a third-party search engine's
UI is an authorization decision only the operator can make),
`CompanyCrawlerProviderSettings` ships sensible built-in defaults and has
no `from_env()`: crawling a dataset row's own company website is the same
"no authorization decision to make" case `CompanyWebsiteProviderSettings`
already is.

| Setting | Default | Purpose |
|---|---|---|
| `user_agent` | `AILeadIntelligenceBot/1.0 (...)` | Sent as the browser's User-Agent, and checked against the target company's robots.txt. |
| `timeout_seconds` | `15.0` | Per-page-navigation timeout. |
| `max_retries` | `2` | Additional attempts after an initial failed page navigation. |
| `retry_backoff_seconds` | `0.5` | Base delay before a retry; multiplied by the attempt number. |
| `max_pages` | `8` | Upper bound on pages visited per crawl (excludes the homepage). |
| `max_depth` | `2` | Link-hops beyond the homepage followed when looking for priority pages. |
| `max_results` | `10` | Maximum `SearchResult`s returned per crawl, independent of `max_pages`. |
| `headless` | `True` | Whether the browser runs without a visible window. |
| `executable_path` | `None` | Optional explicit Chromium/Chrome path, overriding Playwright's own resolution. |

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `CompanyCrawlerProvider` — the `SearchProviderPort` implementation; reads the company URL, checks robots.txt, drives the crawl, reports `SearchResponse`. |
| `settings.py` | `CompanyCrawlerProviderSettings` — crawl budget, timeout/retry policy, headless flag; typed defaults, `validate()`. |
| `link_prioritization.py` | `score_link`/`is_excluded`/`normalize_url`/`extract_priority_links` — keyword-based, no-AI link scoring and exclusion. |
| `crawler.py` | `crawl_company_site` — the breadth-first crawl loop itself, plus retry-guarded page fetch (`_fetch`) and a lightweight title/snippet summary (`_summarize`). |

## `EnrichmentStatus`

| Status | When |
|---|---|
| `FAILURE` | No company URL was available, the homepage itself could not be loaded after retries (`HomepageUnreachable`), or the crawl raised an unexpected error. |
| `SUCCESS` | The crawl completed, including the legitimate empty case of "homepage loaded but zero priority pages found," and the policy-compliant case of a robots.txt disallow. |

`SUCCESS` with zero results is not distinguished from `SUCCESS` with
results at this layer — see "Fallback semantics," below, for how
`run_pipeline.py` uses the *presence* of results (not this status alone)
to decide whether `BrowserSearchProvider` should run as a fallback.

## Fallback semantics: search engines only when the company site yields nothing

Per this task's instruction — "search engines should become a fallback
only when the company website yields no executive information" —
`run_pipeline.py`'s `_build_search_collaborators()` registers
`CompanyCrawlerProvider` as the always-on, `ProviderPriority.HIGH` primary
provider, and `BrowserSearchProvider` (when its `BROWSER_SEARCH_*` env vars
are configured) as an optional, `ProviderPriority.LOW`,
`fallback_only=True` provider. `SearchCoordinator` runs providers in
priority order and, per `SearchProviderConfiguration.fallback_only`, skips
a fallback-only provider once an earlier, higher-priority provider has
already contributed at least one `SearchResult` (`SkipReason.FALLBACK_NOT_NEEDED`).

This is a pragmatic, honestly-scoped Version 1 approximation of "no
executive information": it means *zero pages crawled*, not *zero
executive facts extracted*. The more precise signal — whether
`SearchExtractionEngine` actually found a name/title/email/etc. on those
pages — is only knowable after extraction runs, one stage downstream of
`SearchCoordinator`'s own visibility; only the protected
`ExecutiveProcessingOrchestrator` sees both stages together, and this task
does not permit modifying it. In practice this means: if the company
crawl finds and reports even one priority page (leadership, about, etc.)
but that page's extraction comes up empty, `BrowserSearchProvider` will
*not* run as a fallback for that executive in Version 1.

```python
from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.application.search.config import (
    SearchProfile,
    SearchProviderConfiguration,
)
from lead_intelligence.application.search.coordinator import SearchCoordinator
from lead_intelligence.application.search.provider_registry import SearchProviderRegistry
from lead_intelligence.infrastructure.search.company_crawler.provider import (
    CompanyCrawlerProvider,
)

coordinator = SearchCoordinator(
    SearchProviderRegistry([CompanyCrawlerProvider()]),
    SearchProfile(
        name="example",
        provider_configurations={
            "company_crawler": SearchProviderConfiguration(priority=ProviderPriority.HIGH),
        },
    ),
)
```

## Testing (`tests/unit/company_crawler/`)

Every test uses a fake, in-memory `Browser`/`Page`
(`fixtures.py`'s `FakeBrowser`/`FakePage`, keyed by a `dict[url, html_or_Exception]`,
mirroring `BrowserSearchProvider`'s own fixture style) and a mocked `httpx`
transport for robots.txt checks — **no test here launches a real browser or
touches the real network.**

| File | Covers |
|---|---|
| `test_link_prioritization.py` | `score_link`, `is_excluded` (incl. the paginated-vs-plain-careers distinction), `normalize_url`, `extract_priority_links` (off-domain exclusion, dedup, javascript/fragment-only links, relative-link resolution). |
| `test_crawler.py` | Priority-page visiting, homepage never a result, title/snippet extraction, `HomepageUnreachable` raised on an unreachable homepage (vs. an empty tuple for "loaded but nothing scored"), `max_pages`/`max_results` budgets, the `robots_allow` callback per candidate, multi-hop discovery via `max_depth`. |
| `test_settings.py` | Default validation and every `validate()` failure mode. |
| `test_provider.py` | provider_id/display_name, PERSON-only subject types, missing-URL failure without a browser launch, successful crawl, bare-domain-to-https normalization, robots disallow/missing handling, unreachable-homepage failure, every opened page closed, robots.txt fetched once per instance, `close()` behavior. |

There is no dedicated real-browser end-to-end test for this provider (unlike
`BrowserSearchProvider`'s `tests/integration/test_browser_search_e2e.py`) —
assessed as reasonable to defer for Version 1, since `crawl_company_site()`'s
navigation/retry/summarization logic is structurally identical to (and
reuses the same tested pattern as) `BrowserSearchProvider`'s own already
end-to-end-tested `_search_single_query`.
