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

## Running the tests
```bash
pip install -r requirements-dev.txt
pytest
```
