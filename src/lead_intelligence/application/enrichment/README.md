# Enrichment Provider Framework

Implements Version 1 of the Enrichment Layer: a provider-agnostic
framework for collecting executive information from multiple external
sources without coupling the rest of the platform to any specific one.

## Scope: what Version 1 does and does not do

**Does:** define the one contract every provider must implement
(`EnrichmentProviderPort`), the request/response shapes providers exchange
with the coordinator, a registry for wiring in providers via dependency
injection, per-provider configuration (enabled/priority/refresh policy),
health tracking (a lightweight circuit breaker), and an
`EnrichmentCoordinator` that determines which providers apply, executes
them in priority order, and combines their results.

**Does not:** implement any real provider. No web scraping, no external
API calls, no LinkedIn integration, no AI. Every concrete source — Company
Website, Leadership Page, News, Public Web Search, CRM, D&B, LinkedIn,
other commercial APIs — is a future task: one new class implementing
`EnrichmentProviderPort`, registered with `ProviderRegistry`. Nothing in
this framework needs to change when that happens.

## How the pieces communicate

```
EnrichSubjectUseCase                    (application/use_cases/enrich_subject.py)
        |
        v
EnrichmentCoordinator                   (coordinator.py)
        |
        |-- reads --> EnrichmentProfile       (config.py)            "enabled? priority? refresh policy?"
        |-- reads --> ProviderRegistry        (provider_registry.py)  "which providers exist, and support this subject_type?"
        |-- reads --> ProviderHealthTracker   (provider_health.py)    "is this provider currently healthy?"
        |
        |-- for each applicable, enabled, healthy, stale provider,
        |   in ascending ProviderPriority order:
        |       EnrichmentRequest  -> provider.fetch() -> EnrichmentResponse
        |
        v
EnrichmentCoordinationResult            (application/dto/enrichment_models.py)
  = provider_responses: tuple[EnrichmentResponse, ...]
  + observations: tuple[ObservationCandidate, ...]   (flattened across all executed providers)
  + skipped_providers: tuple[ProviderSkip, ...]
  + metrics: EnrichmentCoordinationMetrics
```

**Execution, per subject (`EnrichmentCoordinator.enrich`):**
1. **Filter to applicable providers**: `ProviderRegistry.providers_supporting(subject_type)`
   excludes any provider that doesn't declare support for this Subject
   type at all (e.g. a Leadership Page provider is never even considered
   for a Company). These providers are structurally inapplicable, not
   "skipped" — they never appear in `skipped_providers`.
2. **Order by priority**: remaining providers are sorted by their
   `ProviderConfiguration.priority` (ascending — `CRITICAL` first), with
   `provider_id` as a stable tiebreaker.
3. For each, in order, gate on three independent, generic checks — any one
   failing produces a `ProviderSkip` with its specific `SkipReason` and the
   provider is never called:
   - **Enabled**: `EnrichmentProfile.is_enabled(provider_id)`.
   - **Healthy**: `ProviderHealthTracker.is_available(provider_id)` — false
     once a provider has accumulated enough consecutive failures.
   - **Stale**: `RefreshPolicy.should_refresh(last_fetched_at, now)` — a
     provider whose data isn't old enough yet is skipped, not re-called.
4. Otherwise, build one `EnrichmentRequest` and call `provider.fetch()`,
   guarded so an unexpected exception is caught, logged, recorded as a
   `FAILURE` response, and used to update that provider's health — one
   misbehaving provider never stops the others.
5. Every executed provider's `ObservationCandidate`s are flattened into one
   run-wide `observations` sequence on the returned result.

## Why `ObservationCandidate`, not the future `Observation` entity

`domain/entities/` doesn't exist yet — the real, provenance-and-confidence
bearing `Observation` entity described in the Executive Intelligence
Architecture is a separate, not-yet-reached task. `ObservationCandidate`
is deliberately scoped to only what a provider can honestly assert today
(which attribute, what value, from where, when) — the same "engine-scoped,
not the future entity" pattern already used for `IdentityRecord` in the
Identity Resolution Engine. A future Observation Pipeline is responsible
for turning candidates into real Observations (conflict resolution,
resolved fact-confidence, etc.); this framework only *collects*
candidates, it never resolves them.

## Why health tracking is a circuit breaker, not just a log

`ProviderHealthTracker` exists so a provider that starts failing
repeatedly (a real vendor outage, once real providers exist) stops being
called automatically, rather than every future enrichment run wasting time
(and, eventually, real request budget) on a source that's currently down.
It is deliberately in-memory only for Version 1 — persisting health across
process restarts, or sharing it across coordinator instances, is
infrastructure work out of this task's framework-only scope.
`record_success`/`record_failure` are pure functions
(`ProviderHealth -> ProviderHealth`); `ProviderHealthTracker` is a thin,
mutable shell that calls them and remembers the result per `provider_id`.

## Configuration (`config.py`)

- `RefreshPolicy.max_age` — how long a provider's data stays fresh before
  it's eligible to run again. The coordinator consults an optional
  `provider_last_fetched: Mapping[provider_id, datetime]` passed into
  `enrich()`; this framework does not persist that itself; a future task
  supplies it from real enrichment history once that exists.
- `ProviderConfiguration` — `enabled`, `priority`, `refresh_policy`,
  `timeout_seconds` (validated and carried for a future infrastructure
  adapter to enforce during real I/O — not enforced by this pure,
  synchronous Version 1 coordinator), and fully opaque `parameters` for
  provider-specific settings this framework never interprets.
- `EnrichmentProfile.default_configuration` — what a newly registered
  provider with no explicit profile entry runs under, so adding a new
  provider never requires updating every existing profile.
- `EnrichmentProfile.validate()` fails the whole run before any provider
  executes if the profile is self-contradictory (mirrors
  `CleaningProfile.validate()` / `IdentityResolutionProfile.validate()`).

## Adding a future concrete provider without modifying this framework

1. Write one class implementing `EnrichmentProviderPort`
   (`application/ports/enrichment_provider_port.py`) — `provider_id`,
   `display_name`, `supported_subject_types`, and `fetch()` — in a new
   `infrastructure/enrichment/<provider_name>/` module. All real I/O
   (HTTP calls, HTML parsing, rate-limit handling, vendor SDKs) lives
   there, never in this package.
2. Register an instance with `ProviderRegistry`.
3. Optionally add a `ProviderConfiguration` entry to the active
   `EnrichmentProfile` for non-default priority/refresh/enabled settings.

`EnrichmentCoordinator`, `ProviderRegistry`, `EnrichmentProfile`, and
`ProviderHealthTracker` never change — none of them name a specific
provider.

## Files

| File | Responsibility |
|---|---|
| `config.py` | `RefreshPolicy`, `ProviderConfiguration`, `EnrichmentProfile`, `default_profile`. |
| `provider_health.py` | `ProviderHealth` transition functions (`initial_health`, `record_success`, `record_failure`), `ProviderHealthTracker`. |
| `provider_registry.py` | `ProviderRegistry`. |
| `coordinator.py` | `EnrichmentCoordinator` — priority ordering, gating, fail-safe execution, aggregation. |
| `application/ports/enrichment_provider_port.py` | `EnrichmentProviderPort`. |
| `application/dto/enrichment_models.py` | Every DTO: `EnrichmentRequest`, `EnrichmentResponse`, `ObservationCandidate`, `ProviderPriority`, `ProviderHealthStatus`, `ProviderHealth`, `SkipReason`, `ProviderSkip`, `EnrichmentCoordinationResult`, `EnrichmentCoordinationMetrics`. Reuses `SubjectType` from `identity_resolution_models.py`. |
| `application/use_cases/enrich_subject.py` | `EnrichSubjectUseCase` — thin orchestration entry point. |
| `domain/exceptions/enrichment_exceptions.py` | `LeadEnrichmentError`, `InvalidEnrichmentConfigurationError`, `DuplicateProviderError`. |

Tests: `tests/unit/enrichment/` — configuration validation, refresh-policy
staleness math, health-tracker state transitions and circuit-breaker
behavior, registry deduplication and subject-type filtering, and an
end-to-end coordinator suite (priority ordering and tie-breaking,
disabled/unhealthy/not-yet-stale skipping with correct reasons,
unsupported-subject-type providers never even being considered, fail-safe
handling of a raising provider, observation aggregation, metrics accuracy,
and determinism) — all against `FakeEnrichmentProvider`, an in-memory
stand-in for the real providers this task deliberately does not implement.
