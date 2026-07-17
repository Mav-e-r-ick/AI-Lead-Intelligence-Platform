# Search Layer

Implements the Search Layer, per the approved Search Layer RFC and the
**Federated Search redesign**: a provider-agnostic framework for
collecting **search results** (URLs, never observations) from multiple
independent external sources, sibling to — and deliberately not merged
into — the Enrichment Provider Framework.

## Federated Search (current architecture)

As of this redesign, the Search Layer no longer has a single primary
provider with an optional fallback. **Every applicable, enabled, healthy
provider runs on every request**, and `SearchCoordinator` merges their
results, deduplicates same-URL results, and ranks the survivors by
confidence — see "How the pieces communicate," below, and
[`docs/architecture/search_layer_federation.md`](../../../../docs/architecture/search_layer_federation.md)
for the full rationale, sequence diagram, and comparison against the
previous single-provider architecture.

The five federated providers (`infrastructure/search/`):

| Provider | `provider_id` | Target | Base confidence |
|---|---|---|---|
| `CompanyCrawlerProvider` | `company_crawler` | The executive's own company website — leadership/management/board/about/team/people/press/news pages. | `1.00` |
| `PressReleaseProvider` | `press_release` | The same company website, scoped to press/newsroom/media/investor-relations/announcements. | `0.95` |
| `LinkedInSearchProvider` | `linkedin_search` | Google's index of LinkedIn's public profile pages, restricted to `linkedin.com`. | `0.98` |
| `NewsProvider` | `news_search` | Google Custom Search restricted to trusted business-news domains (Reuters/Bloomberg/Yahoo Finance/BusinessWire/PRNewswire/GlobeNewswire). | `0.94` (Reuters/Bloomberg) / `0.92` (the rest) |
| `GoogleSearchProvider` | `google_web_search` | The general web, via Google Custom Search. | `0.80` |

Confidence is assigned per-result by `application/search/confidence.py`
— a domain match (LinkedIn, a trusted news outlet) overrides a provider's
own base score, so the same trustworthy source is scored consistently
regardless of which provider happened to surface it. See that module's
own docstring for the full table and reasoning, and "Unknown Website"
(`DEFAULT_CONFIDENCE = 0.50`) for anything unrecognized.

`BrowserSearchProvider` (`infrastructure/search/browser/`) is **not**
one of the five federated providers — it predates this redesign, still
exists and is still tested/documented for standalone use, but
`run_pipeline.py`'s `SearchCoordinator` no longer registers it.

## Scope: what this layer does and does not do

**Does:** define the one contract every search provider must implement
(`SearchProviderPort`), the request/response shapes providers exchange
with the coordinator (`application/dto/search_models.py`, including each
`SearchResult`'s `confidence`), a registry for wiring in providers via
dependency injection, per-provider configuration (enabled/priority/
`fallback_only`), health tracking (reusing `application/enrichment/
provider_health.py`'s `ProviderHealthTracker` unmodified), and a
`SearchCoordinator` that determines which providers apply, executes them,
and merges/deduplicates/ranks their results by confidence.

**Does not:** implement any concrete provider itself (that's
`infrastructure/search/`'s five federated providers above, plus
`browser/`, plus any future one — Bing, Brave, SerpAPI, Tavily, SearchAPI,
Exa — each a new class implementing `SearchProviderPort`). Does not
extract observations, interpret a result's meaning, or fetch a result's
destination page — a search provider's job ends at
title/url/snippet/source/rank/confidence; turning results into evidence
is `infrastructure/search/extraction/`'s job, called separately by
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

## Why `fallback_only` still exists, even though nothing uses it now

`SearchProviderConfiguration.fallback_only` (a provider is skipped once a
higher-priority provider already contributed a result) was this Search
Layer's *previous* architecture, before the Federated Search redesign
replaced "one primary + one fallback" with "run everything, merge by
confidence." The field itself — and `SearchCoordinator`'s skip logic for
it — was left in place rather than deleted: it is generic, already
tested, backward compatible (`default=False`), and remains a legitimate
opt-in choice for a future provider that genuinely only makes sense as a
fallback (e.g. an expensive paid API a caller wants to reserve as a last
resort). None of the five federated providers set it.

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
        |-- reads --> SearchProfile             (config.py)            "enabled? priority? fallback_only?"
        |-- reads --> SearchProviderRegistry    (provider_registry.py)  "which providers exist, and support this subject_type?"
        |-- reads --> ProviderHealthTracker     (application/enrichment/provider_health.py, reused)
        |
        |-- for each applicable, enabled, healthy provider,
        |   in ascending priority order:
        |       SearchRequest  -> provider.search() -> SearchResponse
        |
        |-- merge every SearchResult from every executed provider
        |-- deduplicate by normalized URL (highest-confidence copy wins)
        |-- rank survivors by confidence, descending
        |       (application/search/result_merging.py's dedup_and_rank)
        v
SearchCoordinationResult                (application/dto/search_models.py)
  = provider_responses: tuple[SearchResponse, ...]   (one per executed provider, unmerged)
  + results: tuple[SearchResult, ...]                (deduplicated, confidence-ranked)
  + skipped_providers: tuple[ProviderSkip, ...]       (reused from enrichment_models.py)
  + metrics: SearchCoordinationMetrics                (results_collected reflects the
                                                        post-dedup count actually in `.results`)
```

**Execution, per subject (`SearchCoordinator.search`):**
1. **Filter to applicable providers**: `SearchProviderRegistry.providers_supporting(subject_type)`.
2. **Order by priority**: ascending `SearchProviderConfiguration.priority`
   (`CRITICAL` first), `provider_id` as a stable tiebreaker. Under the
   Federated Search wiring every provider shares the same default
   priority — order here only affects `provider_responses` ordering and
   logging, never the final `.results`, since those are re-sorted by
   confidence regardless of execution order.
3. For each, in order: gate on **enabled**, **healthy**, and (if
   configured) **not `fallback_only` with results already collected**
   (any one failing produces a `ProviderSkip`, provider never called),
   then call `provider.search()`. A provider that raises is treated
   exactly like one that reports `FAILURE` — one misbehaving provider
   never sinks the run.
4. **Merge, deduplicate, and rank**: collect every `SearchResult` from
   every executed provider, drop duplicates (same normalized URL — the
   highest-confidence copy survives), and sort the rest by confidence
   descending (see `result_merging.py`).

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
build a `SearchCoordinator` for its own evaluation runs — that CLI wiring
is a separate, still-pending follow-up from this orchestrator change.
`run_pipeline.py` does build one, registering all five federated
providers (see `run_pipeline.py`'s own `_build_search_collaborators`).

## Files

| File | Responsibility |
|---|---|
| `config.py` | `SearchProviderConfiguration`, `SearchProfile`, `default_profile()`. |
| `provider_registry.py` | `SearchProviderRegistry` — dependency-injected lookup of every registered provider. |
| `coordinator.py` | `SearchCoordinator` — sequences applicable/enabled/healthy providers and merges/deduplicates/ranks their results. |
| `confidence.py` | `score_confidence()` — the shared, single-source-of-truth trust table every federated provider uses. |
| `result_merging.py` | `dedup_and_rank()` — the pure merge/deduplicate/rank transformation `SearchCoordinator` applies. |
| `application/ports/search_provider_port.py` | `SearchProviderPort` — the one contract every search provider implements. |
| `application/dto/search_models.py` | `SearchResult` (now including `confidence`), `SearchRequest`, `SearchResponse`, `SearchCoordinationMetrics`, `SearchCoordinationResult`. |

Tests: `tests/unit/search/` — `fixtures.py` (`FakeSearchProvider`),
`test_config.py`, `test_provider_registry.py`, `test_coordinator.py`
(priority ordering and tie-breaking, disabled/unhealthy skipping with the
correct `SkipReason`, unsupported-subject-type providers never even being
considered, fail-safe handling of a raising provider, result aggregation
across providers, metrics accuracy, determinism, `fallback_only` behavior,
and a dedicated `TestMergeDedupAndRank` class exercising the merge step
end-to-end through the coordinator), `test_confidence.py`, and
`test_result_merging.py`.
