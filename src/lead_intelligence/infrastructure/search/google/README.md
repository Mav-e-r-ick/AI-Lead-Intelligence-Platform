# Google Search Provider (Search Layer)

`GoogleSearchProvider` — one of the five federated Search Layer providers
introduced by the Federated Search redesign (see
`application/search/README.md`'s "Federated Search" section and
`docs/architecture/search_layer_federation.md`). Discovers executive
changes across the general web via the Google Custom Search JSON API.
Implements `SearchProviderPort` — returns `SearchResult`s only, never
extracts observations.

## Scope

**Does:** build a set of inflection-focused search queries (name + company
+ title, combined with "promotion"/"joined"/"appointed"/"named"/"board"/
"CEO"/"VP"/"director" — see `settings.py`'s `DEFAULT_QUERY_TEMPLATES`),
run each through the shared `GoogleCustomSearchClient`
(`infrastructure/search/google_custom_search/`), and report every result
with a confidence score assigned via `application/search/confidence.py`.

**Does not:** fetch a result's destination page, interpret what a result
means, or decide whether it represents a real inflection event — that is
`SearchExtractionEngine`'s and (eventually) the Inflection Engine's job,
both unmodified by this redesign.

## Why `provider_id = "google_web_search"`, not `"google_search"`

`infrastructure/enrichment/google_search/` already registers
`provider_id = "google_search"` with `EnrichmentCoordinator` — a separate
registry/health-tracker from this provider's `SearchCoordinator`, so there
is no mechanical collision, but reusing the same id here would make every
downstream trace (`ExecutiveIntelligenceReport.providers_executed`, logs)
ambiguous about which of the two actually ran. See `provider.py`'s module
docstring for the full reasoning.

## Why query building reuses `enrichment.google_search.query_builder.build_queries`

Pure `{name}`/`{company}`/`{title}` placeholder substitution with zero
Google-specific logic — `BrowserSearchProvider` already reused it for the
same reason. One implementation, not a second copy.

## Why this shares `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` with `enrichment/google_search/`

Both hit the exact same Google Custom Search API account/credential —
`LinkedInSearchProvider` and `NewsProvider` (also built on the shared
`GoogleCustomSearchClient`) reuse it too. See `settings.py`'s module
docstring.

## Configuration (`settings.py`)

| Setting | Default | Purpose |
|---|---|---|
| `api_key` / `search_engine_id` | — (required) | Google Custom Search credentials, read via `from_env()`. |
| `query_templates` | See `DEFAULT_QUERY_TEMPLATES` | Inflection-focused queries — see module docstring. |
| `max_results` | `5` | Results requested per query (capped at 10 by Google). |
| `timeout_seconds` / `max_retries` / `retry_backoff_seconds` | `10.0` / `2` / `0.5` | Per-request policy, delegated to `GoogleCustomSearchClient`. |
| `cache_ttl` | 6 hours | How long one query's results are reused. |

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `GoogleSearchProvider` — the `SearchProviderPort` implementation. |
| `settings.py` | `GoogleSearchProviderSettings` — query templates, retry/timeout/cache policy, `from_env()`. |

## Testing

`tests/unit/google_web_search/` — mocked `httpx` transport only, no real
network call. Covers settings validation/`from_env()`, missing-name
handling, successful multi-query search, confidence assignment (generic
domain vs. a trusted-news domain incidentally found via a general search),
every-query-failing status, and result ranking across queries.
