# Google Search Provider

An Enrichment Provider Framework provider: given an executive's name
(plus company and title, if known), search the public web via the Google
Custom Search JSON API for evidence of career changes — promotions,
appointments, company moves, resignations, awards, interviews, leadership
announcements — ready to be interpreted by a future stage.

Implements `application/ports/enrichment_provider_port.py`'s
`EnrichmentProviderPort`, exactly like `CompanyWebsiteProvider` does.
Nothing in `application/enrichment/` (the framework) knows this class
exists — it's wired in by whatever future orchestration layer constructs a
`ProviderRegistry`.

## Scope: what Version 1 does and does not do

**Does:** accept an executive's name/company/title, generate a
configurable set of search queries, call the Google Custom Search JSON
API for each, extract title/URL/snippet/publication date/source domain
from every result, convert every result into an `ObservationCandidate`,
retry transient failures, time out slow requests, cache repeated queries,
and log every step.

**Does not:** call an AI/LLM to summarize or interpret results, detect
changes between runs (no "this is new since last time" logic), generate
outreach messages, integrate with LinkedIn, or duplicate a future News
provider. This provider only gathers evidence — it never decides what a
result *means*.

## How the pieces communicate

```
GoogleSearchProvider.fetch(EnrichmentRequest)     (provider.py)
        |
        |-- known_attributes[fc.FIRST_NAME]/[fc.LAST_NAME]  ->  executive name
        |-- known_attributes[fc.COMPANY_NAME]  (optional)
        |-- known_attributes[fc.TITLE]          (optional)
        |
        v
  build_queries(name, company, title, settings.query_templates)  (query_builder.py)
        |                                    -> configurable query strings,
        |                                       skipping any template whose
        |                                       placeholder has no value
        v
  for each query:
        _search(query)                       (retry + timeout + cache)
        |       GET {base_url}?key=...&cx=...&q=...&num=...
        v
        parse_search_response(json)          (extraction.py)
        |                                     -> SearchResult per item:
        |                                        title, url, snippet,
        |                                        published_at, source_domain
        v
  one ObservationCandidate (attribute="web_mention") per SearchResult
        |
        v
EnrichmentResponse                            (application/dto/enrichment_models.py)
```

## Why this provider supports only `SubjectType.PERSON`

This provider answers "what does the public web say about this specific
executive?" — a fact about one already-identified person, not about a
company as a whole (contrast with `CompanyWebsiteProvider`, which supports
only `SubjectType.COMPANY`). `ProviderRegistry.providers_supporting` will
never route a Company enrichment request to it.

## Why every result becomes one `web_mention` observation, never a
structured field

Unlike `CompanyWebsiteProvider` (which extracts specific fields — name,
title, email — from a leadership page), a search result is raw, unparsed
evidence: "this URL exists and mentions this executive in this context."
This provider deliberately does not decide what a result means (a
promotion? a resignation? unrelated noise?) — every result is reported as
one `web_mention` `ObservationCandidate`, carrying the result's title as
its `value` and the snippet/source domain/publication date/originating
query as opaque `raw_context`, so a future interpretation stage has
everything it needs without this provider guessing on its behalf.

## Why `known_attributes[fc.FIRST_NAME]`/`[fc.LAST_NAME]`/`[fc.COMPANY_NAME]`/`[fc.TITLE]`, not a new vocabulary

`EnrichmentRequest.known_attributes` is "canonical field name -> value,"
and `field_contract.py` (`application/cleaning/`) is this platform's one
established canonical vocabulary today. This provider reads the
executive's name from `fc.FIRST_NAME`/`fc.LAST_NAME` (falling back to
nothing if both are blank — reported as `EnrichmentStatus.FAILURE`, not a
raised exception) and optionally `fc.COMPANY_NAME`/`fc.TITLE`, rather than
inventing a second, parallel vocabulary for the same concepts.

## Configurable search queries (`query_builder.py`, `settings.py`)

`GoogleSearchProviderSettings.query_templates` defaults to:

```python
DEFAULT_QUERY_TEMPLATES = (
    '"{name}" "{company}"',
    '"{name}" promotion',
    '"{name}" appointed',
    '"{name}" joins',
    '"{name}" resigned',
    '"{name}" leadership',
)
```

`{name}` is always required (a template without a name value can never
apply). `{company}` and `{title}` are optional: a template referencing one
of them is skipped entirely — not filled in blank — when that value isn't
known for this executive, so a company-less executive still gets the five
name-only queries instead of a malformed `'"Ada Lovelace" ""'`. Duplicate
queries (after filling) are deduplicated, first occurrence wins. A caller
can add, remove, or reorder templates via a custom
`GoogleSearchProviderSettings` (e.g. add `'"{name}" fired'`) without
touching provider code.

## Retry, timeout, and caching (`provider.py`, `cache.py`, `settings.py`)

- Every query goes through one `_search()` that checks the cache first,
  then attempts the request with a per-request timeout
  (`settings.timeout_seconds`).
- A timeout, connection error, HTTP 429, or `5xx` response is retried up
  to `settings.max_retries` additional times, with linear backoff
  (`settings.retry_backoff_seconds * attempt`). A `4xx` response
  (other than 429) is never retried.
- A successfully searched query's results are cached
  (`InMemorySearchResultCache`, keyed by the exact query string) for
  `settings.cache_ttl`, so re-enriching the same executive shortly after a
  previous run doesn't re-issue (and re-pay for) identical searches.

## `EnrichmentStatus` outcomes

| Status | When |
|---|---|
| `FAILURE` | No executive name was available, no queries could be built, or every query failed. |
| `PARTIAL` | At least one query succeeded and at least one query genuinely failed (after retries). |
| `SUCCESS` | Every query succeeded — including the legitimate empty case of "no results found" for any of them. |

## Configuration (`settings.py`)

| Setting | Purpose |
|---|---|
| `api_key` / `search_engine_id` | Google Custom Search JSON API credentials (see Environment variables, below). |
| `max_results` | Maximum results requested per query (the API's own `num` parameter), validated within `[1, 10]` — Google's own per-request limit. |
| `timeout_seconds` | Per-request timeout. |
| `cache_ttl` | How long one query's results are reused before being considered stale. |
| `max_retries` / `retry_backoff_seconds` | Retry policy for transient failures. |
| `query_templates` | Which queries to generate — see above. |

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_SEARCH_API_KEY` | Yes | A Google API key with the Custom Search API enabled. Get one at https://console.cloud.google.com/apis/credentials. |
| `GOOGLE_SEARCH_ENGINE_ID` | Yes | A Programmable Search Engine id ("cx"). Create one at https://programmablesearchengine.google.com/. |

```python
from lead_intelligence.infrastructure.enrichment.google_search.provider import (
    GoogleSearchProvider,
)
from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    GoogleSearchProviderSettings,
)

provider = GoogleSearchProvider(settings=GoogleSearchProviderSettings.from_env())
```

`GoogleSearchProviderSettings.validate()` runs at construction time — a
blank or missing API key/search engine id raises `ValueError`
immediately, rather than silently sending an unauthenticated request on
the first `fetch()` call.

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `GoogleSearchProvider` — the `EnrichmentProviderPort` implementation; orchestrates query building, retry-guarded search calls, result extraction, and `ObservationCandidate` assembly. |
| `settings.py` | `GoogleSearchProviderSettings` — API key, search engine id, timeout, retries, backoff, max results, cache TTL, query templates; `from_env()` reads `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID`. |
| `query_builder.py` | `build_queries` — fills query templates from an executive's name/company/title, skipping templates whose placeholders aren't available. |
| `cache.py` | `SearchResultCache`, `InMemorySearchResultCache` — TTL-based per-query result reuse. |
| `extraction.py` | `SearchResult`, `parse_search_response` — Google Custom Search JSON response -> plain result records. |

Tests: `tests/unit/google_search/` — settings validation and `from_env()`,
query-builder placeholder/skip/dedup/ordering behavior, response
extraction (title/URL/snippet/publication-date/domain, missing fields,
multiple items), cache TTL behavior, and an end-to-end provider suite
against `httpx.MockTransport` (never a real network call) covering missing
inputs, successful multi-query searches, `web_mention` observation
mapping, retry/timeout/rate-limit/client-error handling, caching, and one
integration test proving this provider runs correctly through the real
`EnrichmentCoordinator`/`ProviderRegistry`.
