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
| `fixtures/` | Shared, reusable test data and setup helpers (e.g. a sample "fake lead" dictionary) used by multiple test files, so tests don't duplicate setup code. |

## What's here right now
`test_health.py` is the only real test in this foundation task. It calls
the `/health` endpoint from `interfaces/api/main.py` and checks it responds
successfully — this proves the whole import chain (core -> interfaces)
actually works, without testing any business feature (there are none yet).

## Running the tests
```bash
pip install -r requirements-dev.txt
pytest
```
