# Tests

## Why tests live outside `src/`
Keeping `tests/` separate from `src/lead_intelligence/` means test code is
never accidentally packaged/shipped with the application, while still
sitting right next to the code it tests for easy navigation.

## Sub-folders

| Folder | Purpose |
|---|---|
| `unit/` | Fast tests that check one function/class in isolation, with all external dependencies (database, APIs) replaced by fakes. Should run in milliseconds and require no network access. |
| `integration/` | Slower tests that check multiple pieces working together (e.g. "does the FastAPI app actually start and respond?"). May talk to a real (test) database or a locally running server. |
| `fixtures/` | Shared, reusable test data and setup helpers. **Implemented:** `excel_builder.py` — builds small, disposable `.xlsx` files in a temp directory so Import Engine tests never depend on the real (gitignored) sample dataset. |

## What's here right now
- `conftest.py` sets `DATABASE_URL` to an in-memory SQLite database before
  any test module is imported, so importing the FastAPI app (which
  constructs a real database Engine at import time) never leaves a stray
  `local_dev.db` file in the repo root.
- `integration/test_health.py` calls `/health` and `/health/database` from
  `interfaces/api/main.py` — proving the core -> interfaces import chain
  works, and that the readiness check correctly reports both a reachable
  database and (via a dependency override pointed at an unreachable port)
  an unreachable one as HTTP 503.
- `unit/importer/` covers the Import Engine: `test_file_validator.py`,
  `test_sheet_selector.py`, `test_excel_reader.py`,
  `test_import_dataset_use_case.py`, and `test_models.py`. All of them use
  synthetic in-memory workbooks (via `fixtures/excel_builder.py`), so they
  run fast and don't require any external file — including one test that
  directly proves leading zeros survive a round trip through a text-typed
  identifier column.
- `unit/cleaning/` covers the Cleaning Engine: `test_registry_consistency.py`
  (every one of the 68 rules checked against its CLEANING_RULES.md
  invariants), `test_common_rules.py` (the generic, reusable rule base
  classes), `test_pipeline.py` (stage ordering, the business master switch,
  fail-safe error handling, audit trail assembly, using small fake rules to
  isolate orchestration from any individual rule), `test_config.py`
  (`CleaningProfile`), `test_clean_dataset_use_case.py`, and
  `test_rules_behavior.py` (targeted tests for the bespoke, non-generic
  rules — name casing, phone E.164 formatting, the Pre-Tax-Profit exclusion
  in CLN-048, the CLN-016/CLN-067 mutual-exclusivity check, and a regression
  test for the `www.`-prefix bug found during end-to-end verification).
- `unit/persistence/` covers the Persistence Infrastructure:
  `test_base_repository.py` (the generic `Repository` /
  `AppendOnlyRepository` / `MutableRepository` hierarchy — including that
  `AppendOnlyRepository` structurally has no `update()`),
  `test_repository_interfaces.py` (every one of the 10 named repository
  interfaces is built on the correct base class, per the approved
  Persistence Architecture),
  `test_session.py` (the SQLite-vs-PostgreSQL branching in
  `create_engine_from_settings`), `test_unit_of_work.py`
  (`SqlAlchemyUnitOfWork`'s commit/rollback lifecycle, using a temp-file
  SQLite database so separate Unit of Work instances share real persisted
  state, the same as separate requests would against PostgreSQL), and
  `test_health.py` (`check_database_connectivity` against both a reachable
  and an unreachable database).
- `unit/identity_resolution/` covers the Identity Resolution Engine:
  `test_config.py` (`IdentityResolutionProfile` validation), `fixtures.py`
  (`FakeIdentityCandidatePort`, an in-memory stand-in for the not-yet-built
  infrastructure adapter), `test_signal_extraction.py` (Person/Company
  signal extraction, missing-field handling, fallback fields, the `www.`
  domain-stripping behavior), `test_candidate_generation.py` (blocking
  eligibility — title can never surface a candidate alone — dedup,
  deterministic capping/ordering), `test_scoring.py` (every confidence
  band, the "single weak signal is never sufficient" rule, contradiction
  handling, determinism, `recompute_confidence` equivalence to
  `score_candidate`), `test_decision.py` (auto-merge precedence, tie-
  breaking, review-candidate ordering), `test_engine.py` (end-to-end
  auto-merge/candidate-review/new-identity paths and dataset-level metrics,
  using injected deterministic id/clock dependencies), `test_recomputation.py`
  (confidence band transitions as new evidence arrives), and
  `test_use_case.py` (`ResolveIdentityUseCase`).
- `unit/enrichment/` covers the Enrichment Provider Framework:
  `fixtures.py` (`FakeEnrichmentProvider`, a fully scripted in-memory
  stand-in for the real providers this task deliberately does not
  implement), `test_config.py` (`RefreshPolicy` staleness math,
  `ProviderConfiguration`/`EnrichmentProfile` validation and fallback-to-
  default behavior), `test_provider_health.py` (the pure health
  transition functions and `ProviderHealthTracker`'s circuit-breaker
  behavior — degraded vs. unhealthy thresholds, recovery on success),
  `test_provider_registry.py` (duplicate-id rejection, subject-type
  filtering), `test_coordinator.py` (priority ordering and tie-breaking,
  disabled/unhealthy/not-yet-stale skipping with the correct
  `SkipReason`, unsupported-subject-type providers never even being
  considered, fail-safe handling of a raising provider, observation
  aggregation across providers, metrics accuracy, and determinism), and
  `test_use_case.py` (`EnrichSubjectUseCase`).
- `unit/company_website/` covers the Company Website Provider:
  `fixtures.py` (shared HTML snippets and an `httpx.MockTransport`-backed
  client builder — no test here ever touches the real network),
  `test_settings.py` (`CompanyWebsiteProviderSettings` validation),
  `test_cache.py` (`InMemoryPageCache` TTL expiry), `test_page_discovery.py`
  (leadership/about/team link detection, same-domain filtering, relative-
  link resolution, keyword-strength ranking, deduplication), `test_extraction.py`
  (name/title/biography/email/phone extraction, multiple people per page,
  missing-field handling, mailto:/tel: vs. regex-fallback contact info,
  innermost-container selection, deduplication), `test_provider.py`
  (end-to-end `fetch()` behavior: missing-URL handling, robots.txt
  allow/disallow at both the homepage and per-page level, all three
  `EnrichmentStatus` outcomes, retry-then-succeed and retry-exhausted
  behavior for 5xx/timeouts, no-retry on 4xx, cache reuse across repeated
  fetches, bare-domain URL normalization, and the `max_leadership_pages`
  cap), and `test_coordinator_integration.py` (proving this provider runs
  correctly through the real `EnrichmentCoordinator`/`ProviderRegistry`,
  not just in isolation).
- `unit/comparison/` covers the Executive Comparison Engine: `fixtures.py`
  (`make_existing_record`, `make_observation` builders), `test_comparators.py`
  (text normalization, `difflib`-based similarity, email/phone
  normalizers), `test_resolvers.py` (existing-value extraction fallback
  chains per field), `test_config.py` (`ComparisonProfile` validation —
  duplicate fields, missing resolvers, out-of-range fuzzy thresholds), and
  `test_engine.py` (all six verdicts — `MATCH`/`CHANGED`/`MISSING`/`NEW`/
  `CONFLICT`/`UNKNOWN` — for both EXACT and FUZZY fields, conflict
  deduplication distinguishing trivial formatting differences from
  genuinely distinct values, summary/confidence arithmetic, field
  ordering, and determinism), and `test_use_case.py`
  (`CompareExecutiveUseCase`).
- `unit/inflection/` covers the Inflection Detection Engine:
  `fixtures.py` (`FieldComparison`/`ComparisonResult` builders),
  `test_seniority.py` (keyword-based title seniority ranking, including
  the longest-match-wins tie-break), `test_rule_base.py`
  (`get_field_comparison` helper), `test_registry.py`
  (`InflectionRuleRegistry` duplicate-`rule_id` guarding), `test_config.py`
  (`InflectionProfile` enable/disable and confidence overrides, validation
  of out-of-range overrides), `test_rules.py` (fire/no-fire coverage for
  all seven rules, including the Possible-Resignation/
  Executive-No-Longer-Found mutual exclusivity), `test_engine.py`
  (end-to-end confidence arithmetic and clamping, disabled rules, multiple
  simultaneous inflections, determinism), and `test_use_case.py`
  (`DetectInflectionsUseCase`).
- `unit/verification/` covers the Contact Verification Framework:
  `fixtures.py` (`FakeVerificationProvider`, an in-memory stand-in for the
  real providers this task deliberately does not implement),
  `test_config.py` (`VerificationProfile`/`VerificationProviderConfiguration`
  validation and enabled/default-fallback lookup), `test_ports.py`
  (`EmailVerificationPort`/`PhoneVerificationPort`'s fixed contact-type
  support), `test_coordinator.py` (end-to-end: priority ordering and
  tie-breaking, disabled-provider skipping, unsupported-contact-type
  providers never even being considered, fail-safe handling of a raising
  provider, technical-failure vs. successful-call metrics classification,
  duplicate-provider-id guarding, never picking a winning verdict when
  providers disagree, and determinism), and `test_use_case.py`
  (`VerifyContactUseCase`).
- `unit/neverbounce/` covers the NeverBounce email verification provider:
  `fixtures.py` (`httpx.MockTransport`-backed client builder and
  NeverBounce response-body builders — no test here ever touches the real
  network), `test_settings.py` (`NeverBounceSettings` validation and
  `from_env()`, including real `os.environ` via `monkeypatch`),
  `test_provider.py` (every documented NeverBounce `result` value's status
  mapping — valid/invalid/disposable/catchall/unknown — every API-level
  error status — auth_failure/general_failure/bad_referrer/
  throttle_triggered/temp_unavail — HTTP-level failures — 429/5xx/4xx/
  timeout/connection error — and their retry behavior), and
  `test_coordinator_integration.py` (proving this provider runs correctly
  through the real `VerificationCoordinator`, not just in isolation).
- `unit/google_search/` covers the Google Search enrichment provider:
  `fixtures.py` (`httpx.MockTransport`-backed client builder and Google
  Custom Search response-body builders — no test here ever touches the
  real network), `test_settings.py` (`GoogleSearchProviderSettings`
  validation and `from_env()`, including real `os.environ` via
  `monkeypatch`), `test_query_builder.py` (placeholder substitution,
  skipping templates whose value is missing, deduplication, and order
  preservation), `test_extraction.py` (title/URL/snippet/publication-date/
  domain extraction, missing-field handling, multiple items),
  `test_cache.py` (`InMemorySearchResultCache` TTL expiry),
  `test_provider.py` (end-to-end: missing-name handling, query generation
  with/without a known company, `web_mention` observation mapping, all
  three `EnrichmentStatus` outcomes, retry/timeout/rate-limit/client-error
  behavior, and cache reuse across repeated queries), and
  `test_coordinator_integration.py` (proving this provider runs correctly
  through the real `EnrichmentCoordinator`/`ProviderRegistry`, not just in
  isolation).
- `unit/executive_pipeline/` covers the Executive Processing Pipeline:
  `fixtures.py` (`build_orchestrator` — assembles a real
  `EnrichmentCoordinator`/`ComparisonEngine`/`InflectionDetectionEngine`/
  optional `VerificationCoordinator`, plus (V2) an optional
  `IdentityResolutionEngine`/`SearchCoordinator`/`SearchExtractionPort`,
  around injectable fake providers and profile overrides),
  `test_orchestrator.py` (missing-executive-name handling, the happy path
  including an end-to-end detected Promotion, subject-type routing —
  Person- and Company-scoped providers both run, a provider supporting
  neither never runs — observation aggregation, verification scope —
  skipped when not configured, skipped when no email is known, receives
  the existing record's email — per-stage error handling for all four
  stages via genuinely invalid sub-profiles, status derivation, and
  determinism), and `test_full_pipeline_stages.py` (V2: the Identity
  Resolution stage recording its outcome on the report and surviving a
  raising port, the Search + Search Extraction stages — including
  `providers_executed` being recorded even when extraction itself fails,
  extraction being skipped with a warning when no engine is configured,
  and combined observations reaching Comparison — and `process_batch()`
  — statistics across succeeded/partial/failed executives, continuing
  past both an ordinary per-stage error and a genuinely unexpected
  exception from `process()` itself, and the returned
  `ExecutiveIntelligenceReport`'s totals/timing).
- `integration/test_executive_pipeline.py` proves the same orchestrator
  processes one executive correctly through the *real*
  `CompanyWebsiteProvider`, `GoogleSearchProvider`, and
  `NeverBounceEmailProvider` (each HTTP-mocked via `httpx.MockTransport`,
  never a real network call), with no fakes standing in for any of the
  orchestrator's own collaborators.
- `integration/test_executive_intelligence_pipeline.py` proves the V2
  pipeline end to end through every *real* collaborator at once: a real
  `IdentityResolutionEngine`, `CompanyWebsiteProvider` (HTTP-mocked), a
  real `SearchCoordinator` wrapping a `BrowserSearchProvider` (fake
  in-memory browser), a real `SearchExtractionEngine` (HTTP-mocked), and
  a real `VerificationCoordinator`/`NeverBounceEmailProvider`
  (HTTP-mocked) — `TestSingleExecutiveEndToEnd` for one record and
  `TestBatchEndToEnd` for `process_batch()` across several.
- `unit/evaluation/` covers the Evaluation & Validation module:
  `fixtures.py` (`make_report`/`make_inflection_report`/`make_verification_report`
  builders for `ExecutiveProcessingReport` and its embedded stage results),
  `test_row_builder.py` (subject_id/executive_name passthrough,
  company/website resolution, per-provider result counts,
  `providers_executed` joining, comparison-summary formatting,
  inflections-detected formatting, all four verification-status branches,
  and stage-error joining), `test_metrics.py` (success rate, the
  "technical failure" definition of failed searches, the "found" vs.
  "completed" distinction for company-website/Google metrics, every
  inflection-type count, and verification success rate excluding
  non-attempts from its denominator), `test_export.py` (CSV header/row
  round-tripping, `None`-to-blank-string conversion, parent-directory
  creation, and the JSON summary report's structure), and `test_runner.py`
  (`PipelineRunner` against a real Import Engine + Cleaning Engine over a
  tiny in-memory workbook and a fake `ProcessExecutiveUseCase` — every
  record processed, subject_id derived from the Excel row number,
  summary/source-description correctness, and per-record fail-safe
  handling of an unexpected exception).
- `unit/search/` covers the Search Layer framework: `fixtures.py`
  (`FakeSearchProvider`, an in-memory stand-in for the real providers),
  `test_config.py` (`SearchProfile`/`SearchProviderConfiguration`
  validation and fallback-to-default behavior), `test_provider_registry.py`
  (duplicate-id rejection, subject-type filtering), and
  `test_coordinator.py` (priority ordering and tie-breaking,
  disabled/unhealthy skipping with the correct `SkipReason`,
  unsupported-subject-type providers never even being considered,
  fail-safe handling of a raising provider, result aggregation across
  providers, metrics accuracy, and determinism) — the same coverage shape
  as `unit/enrichment/`, minus the refresh-policy/staleness cases that
  don't apply to Search (see `application/search/README.md` for why).
- `unit/browser_search/` covers `BrowserSearchProvider`: `fixtures.py`
  (`FakeBrowser`/`FakePage`/`FakeElement` — an in-memory stand-in for
  Playwright, and a mocked-httpx-transport builder for the robots.txt
  check — no test here ever launches a real browser or touches the real
  network), `test_settings.py` (`BrowserSearchProviderSettings`
  validation and `from_env()`), `test_cache.py` (TTL expiry),
  `test_extraction.py` (title/URL/snippet/rank extraction, relative-URL
  resolution against the page's own URL, missing-field skipping, and the
  `max_results` first-N-*successful*-results semantics), and
  `test_provider.py` (end-to-end `search()` behavior: missing-name
  handling, successful multi-query search, every opened page being
  closed, caching across repeated searches, retry-then-succeed and
  retry-exhausted behavior, partial-success status, robots.txt
  allow/disallow/missing handling, robots.txt fetched only once per
  provider instance, and `close()`).
- `integration/test_browser_search_e2e.py` is a real, non-mocked
  end-to-end test: a real headless Chromium (via Playwright) against a
  real local HTTP server (Python's own `http.server`, never a live
  third-party site). Skipped by default (every other test in this
  repository is fast and network-free); opt in with
  `RUN_BROWSER_SEARCH_E2E=1` — see
  `infrastructure/search/browser/README.md` for exact instructions,
  including the `BROWSER_SEARCH_EXECUTABLE_PATH` override some
  environments need.
- `unit/search_extraction/` covers the Search Extraction Engine:
  `fixtures.py` (an httpx mock-transport routing table, HTML page
  builders, and a flaky-then-recovering handler — no test here ever
  touches the real network), `test_settings.py`
  (`SearchExtractionSettings` validation), `test_page_fetcher.py`
  (PDF-URL skip without any request, PDF-Content-Type discard,
  robots.txt allow/disallow/missing, robots.txt fetched once per domain,
  retry-then-succeed and retry-exhausted behavior, 4xx never retried,
  page-cache reuse), `test_content_extraction.py` (title and `og:title`
  fallback, script/style/noscript/template stripping, whitespace
  collapse, `max_text_chars` truncation, publication-date meta variants
  reported verbatim and never parsed, malformed HTML tolerance),
  `test_fact_extraction.py` (every named fact pattern's fire and no-fire
  behavior, title-before-text scan order, lowercase prose never matching
  a name, and determinism), and `test_engine.py` (end-to-end: an
  announcement page yielding `web_page` + `full_name`/`title`/
  `company_name` candidates, subject_id/engine-id/source-URL stamping,
  the raw snippet preserved verbatim in `raw_context`, provenance and
  excerpt bounding, unmatched pages still yielding their `web_page`
  candidate, unreachable/PDF results yielding nothing, one bad result
  never stopping the rest, and multi-result aggregation order).

## Running the tests
```bash
pip install -r requirements-dev.txt
pytest
```
