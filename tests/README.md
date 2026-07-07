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
- `integration/test_health.py` calls the `/health` endpoint from
  `interfaces/api/main.py` and checks it responds successfully — proving
  the core -> interfaces import chain works.
- `unit/importer/` covers the Import Engine: `test_file_validator.py`,
  `test_sheet_selector.py`, `test_excel_reader.py`,
  `test_import_dataset_use_case.py`, and `test_models.py`. All of them use
  synthetic in-memory workbooks (via `fixtures/excel_builder.py`), so they
  run fast and don't require any external file — including one test that
  directly proves leading zeros survive a round trip through a text-typed
  identifier column.

## Running the tests
```bash
pip install -r requirements-dev.txt
pytest
```
