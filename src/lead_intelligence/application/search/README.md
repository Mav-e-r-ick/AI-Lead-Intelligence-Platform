# Search Layer

Implements Version 1 of the Search Layer, per the approved Search Layer
RFC: a provider-agnostic framework for collecting **search results**
(URLs, never observations) from multiple external sources, sibling to —
and deliberately not merged into — the Enrichment Provider Framework.

## Scope: what Version 1 does and does not do

**Does:** define the one contract every search provider must implement
(`SearchProviderPort`), the request/response shapes providers exchange
with the coordinator (`application/dto/search_models.py`), a registry for
wiring in providers via dependency injection, per-provider configuration
(enabled/priority/`fallback_only`), health tracking (reusing
`application/enrichment/provider_health.py`'s `ProviderHealthTracker`
unmodified), and a `SearchCoordinator` that determines which providers
apply, executes them in priority order, skips a `fallback_only` provider
once a higher-priority provider already contributed results, and combines
the rest.

**Does not:** implement any concrete provider itself (that's
`infrastructure/search/company_crawler/`, this layer's primary provider as
of Version 1 — crawls each executive's own company website, no third-party
search engine involved — plus `infrastructure/search/browser/`, wired in
as an optional `fallback_only` provider for when the company site yields
nothing, plus any future one — Bing, Brave, SerpAPI, Tavily, SearchAPI,
Exa — each a new class implementing `SearchProviderPort`). Does not extract
observations, interpret a result's meaning, or fetch a result's
destination page — a search provider's job ends at
title/url/snippet/source/rank; turning results into evidence is
`infrastructure/search/extraction/`'s job, called separately by
`ExecutiveProcessingOrchestrator` — see "How this is wired into the
Executive Processing Pipeline" below.

## Why this is a separate package from `application/enrichment/`

Per the approved RFC: search and extraction are different responsibilities
with different failure modes and different future providers. Folding
`SearchCoordinator` into `EnrichmentCoordinator` would re-couple exactly
what the RFC exists to separate — a search provider structurally cannot
return an `ObservationCandidate` (`SearchProviderPort.search()` returns
`SearchResponse`, which only carries `SearchResult`s), so the separation
is enforced by the type system, not just convention.

## Why there is no `RefreshPolicy`/staleness skip, unlike `EnrichmentProfile`

`RefreshPolicy` answers "how long is previously collected data still
fresh" — a question that only makes sense once results are persisted
somewhere with a last-fetched timestamp. Nothing in this platform
persists search results yet (the same is true of enrichment observations
today), so carrying a refresh policy here would be unexercised
scaffolding. If/when search results are persisted, `SearchProfile` can
grow a `refresh_policy` field the same way `ProviderConfiguration`
already has one.

## How the pieces communicate

```
ExecutiveProcessingOrchestrator         (application/executive_pipeline/orchestrator.py)
        |
        v
SearchCoordinator                       (coordinator.py)
        |
        |-- reads --> SearchProfile             (config.py)            "enabled? priority?"
        |-- reads --> SearchProviderRegistry    (provider_registry.py)  "which providers exist, and support this subject_type?"
        |-- reads --> ProviderHealthTracker     (application/enrichment/provider_health.py, reused)
        |
        |-- for each applicable, enabled, healthy provider,
        |   in ascending priority order:
        |       SearchRequest  -> provider.search() -> SearchResponse
        |
        v
SearchCoordinationResult                (application/dto/search_models.py)
  = provider_responses: tuple[SearchResponse, ...]
  + results: tuple[SearchResult, ...]   (flattened across all executed providers)
  + skipped_providers: tuple[ProviderSkip, ...]   (reused from enrichment_models.py)
  + metrics: SearchCoordinationMetrics
```

**Execution, per subject (`SearchCoordinator.search`):**
1. **Filter to applicable providers**: `SearchProviderRegistry.providers_supporting(subject_type)`.
2. **Order by priority**: ascending `SearchProviderConfiguration.priority`
   (`CRITICAL` first), `provider_id` as a stable tiebreaker.
3. For each, in order: gate on **enabled** and **healthy** (any one
   failing produces a `ProviderSkip`, provider never called), then call
   `provider.search()`. A provider that raises is treated exactly like one
   that reports `FAILURE` — one misbehaving provider never sinks the run.
4. Collect every `SearchResult` from every executed provider into one
   flattened `results` tuple, plus per-provider responses, skips, and
   metrics.

## How this is wired into the Executive Processing Pipeline

`ExecutiveProcessingOrchestrator.process()` (application/executive_pipeline/)
calls `SearchCoordinator.search()` alongside — not instead of —
`EnrichmentCoordinator.enrich()`; the two evidence paths run
independently and their observations are combined before Comparison runs
(see `executive_pipeline/README.md`). Every `SearchResult` the
coordinator returns is then handed to a `SearchExtractionPort`
(`application/ports/search_extraction_port.py`, satisfied in production
by the real `SearchExtractionEngine`) — the orchestrator's own
responsibility, not this package's, keeping "search finds URLs" and
"extraction reads them" as separate calls the orchestrator sequences,
exactly per the approved RFC. `scripts/run_evaluation.py` does not yet
build a `SearchCoordinator` (`CompanyCrawlerProvider`/`BrowserSearchProvider`)
for its own evaluation runs — that CLI wiring is a separate, still-pending
follow-up from this orchestrator change. `run_pipeline.py` does build one
(see `infrastructure/search/company_crawler/README.md`'s "Fallback
semantics" section for the exact priority/`fallback_only` wiring).

## Files

| File | Responsibility |
|---|---|
| `config.py` | `SearchProviderConfiguration`, `SearchProfile`, `default_profile()`. |
| `provider_registry.py` | `SearchProviderRegistry` — dependency-injected lookup of every registered provider. |
| `coordinator.py` | `SearchCoordinator` — sequences applicable/enabled/healthy providers in priority order and combines results. |
| `application/ports/search_provider_port.py` | `SearchProviderPort` — the one contract every search provider implements. |
| `application/dto/search_models.py` | `SearchResult`, `SearchRequest`, `SearchResponse`, `SearchCoordinationMetrics`, `SearchCoordinationResult`. |

Tests: `tests/unit/search/` — `fixtures.py` (`FakeSearchProvider`),
`test_config.py`, `test_provider_registry.py`, `test_coordinator.py`
(priority ordering and tie-breaking, disabled/unhealthy skipping with the
correct `SkipReason`, unsupported-subject-type providers never even being
considered, fail-safe handling of a raising provider, result aggregation
across providers, metrics accuracy, and determinism) — the same coverage
shape as `tests/unit/enrichment/`, minus the refresh-policy cases that
don't apply here.
