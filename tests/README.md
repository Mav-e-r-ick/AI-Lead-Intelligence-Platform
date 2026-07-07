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

## Running the tests
```bash
pip install -r requirements-dev.txt
pytest
```
