# AI Lead Intelligence Platform

A production-grade platform that will eventually import executive data from
Excel, clean and verify it, detect professional inflection points (job
changes, promotions, funding events), generate AI-personalized outreach
messages, and send them after human review.

> **Status: Foundation + Import Engine.** The project structure, configuration,
> and wiring are in place, and the **Import Engine** (reading Excel files into
> plain, unmodified records — see
> [`infrastructure/importers/README.md`](src/lead_intelligence/infrastructure/importers/README.md))
> is implemented. Every other business feature (cleaning, verification, AI
> generation, sending) is still an empty, clearly-labeled placeholder waiting
> for future work. If you're new to software engineering: think of the
> Import Engine as the first piece of real furniture moved into one room of
> the house built in the foundation task.

## Why does an empty project need this much structure?

Because restructuring a codebase *after* it's full of business logic is
expensive and risky. Deciding the shape of the house before moving in
furniture means every future feature has one obvious, correct place to go,
and pieces (like the AI provider or the email-verification vendor) can be
swapped later without rewriting everything around them. The specific
pattern used here is called **Clean Architecture** — see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full reasoning. This
README focuses on the practical "what is every file/folder for."

## Quick start

```bash
# 1. Create an isolated Python environment (keeps this project's
#    dependencies separate from other Python projects on your machine).
python -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate

# 2. Install dependencies.
pip install -r requirements.txt -r requirements-dev.txt

# 3. Copy the example environment file and fill in real values later.
cp .env.example .env

# 4. Run the test suite (health-check smoke test + Import Engine unit tests).
pytest

# 5. Run the API and confirm the foundation actually boots.
uvicorn lead_intelligence.interfaces.api.main:app --reload
# then visit http://127.0.0.1:8000/health -> {"status": "ok"}
```

## Project layout

```
.
├── .env.example              # Template listing every config value the app needs (fake values)
├── .gitignore                 # Tells git which files to never track (secrets, caches, PII data)
├── requirements.txt            # Production Python dependencies
├── requirements-dev.txt        # Extra dependencies needed only for development (tests, linters)
├── README.md                   # You are here
├── docs/
│   └── ARCHITECTURE.md         # Deep dive: why the code is organized this way
├── data/
│   ├── README.md                # Explains why raw/processed are (almost) empty in git
│   ├── raw/                     # Excel files exactly as received (gitignored contents)
│   └── processed/               # Cleaned output (gitignored contents)
├── logs/                        # Local log file output (gitignored contents)
├── scripts/
│   └── README.md                # Explains the purpose of this folder (currently empty)
├── src/
│   └── lead_intelligence/       # The installable application package
│       ├── __init__.py
│       ├── core/                 # Shared plumbing every layer may use
│       │   ├── config.py          # Typed settings loaded from .env
│       │   └── logging.py         # Central logging setup
│       ├── domain/               # Business concepts & rules (innermost layer)
│       │   ├── README.md
│       │   ├── entities/          # e.g. future Lead, Executive, Company classes
│       │   ├── value_objects/     # e.g. future EmailAddress, PhoneNumber
│       │   ├── repositories/      # Interfaces for saving/loading entities
│       │   └── exceptions/        # import_exceptions.py (Import Engine's error types)
│       ├── application/          # Use cases (what the system can DO)
│       │   ├── README.md
│       │   ├── use_cases/         # import_dataset.py (ImportDatasetUseCase)
│       │   ├── services/          # Logic shared across use cases (none yet)
│       │   ├── ports/             # source_reader_port.py (SourceReaderPort)
│       │   └── dto/               # models.py (RawRecord, SourceMetadata, ImportedLeadDataset, ...)
│       ├── infrastructure/       # Talks to databases & third-party vendors
│       │   ├── README.md
│       │   ├── database/          # SQLAlchemy engine/session/base (no tables yet)
│       │   ├── importers/         # Import Engine — see importers/README.md
│       │   │   └── excel/          # ExcelSourceReader, ExcelFileValidator, ExcelSheetSelector
│       │   └── external_services/ # One sub-folder per vendor category:
│       │       ├── email_verification/
│       │       ├── phone_verification/
│       │       ├── linkedin/
│       │       ├── company_data/
│       │       ├── ai_providers/     # Anthropic (Claude) SDK wrapper
│       │       └── email_sending/
│       └── interfaces/           # How the outside world talks to us
│           ├── README.md
│           ├── api/                # FastAPI app (main.py has a working /health route)
│           ├── cli/                # Future command-line entry points
│           └── schemas/            # Pydantic request/response models for the API
└── tests/
    ├── README.md
    ├── unit/
    │   └── importer/              # Import Engine unit tests
    ├── integration/               # Tests spanning multiple pieces
    │   └── test_health.py          # Proves the foundation actually runs
    └── fixtures/                  # excel_builder.py — synthetic .xlsx fixtures for tests
```

Every folder that isn't self-explanatory has its own `README.md` right
inside it — read those for the full reasoning on that specific layer. This
top-level table is the map; the per-folder READMEs are the terrain.

## What each root file is for

| File | Purpose |
|---|---|
| `requirements.txt` | Every third-party package the *running app* needs, grouped by which future feature it supports, with comments explaining each choice. Install with `pip install -r requirements.txt`. |
| `requirements-dev.txt` | Additional packages needed only for development (pytest, black, ruff, mypy, pre-commit) — never installed on a production server. |
| `.gitignore` | Prevents secrets (`.env`), generated files (`__pycache__`, caches), local databases, and — importantly — real lead data (`data/raw`, `data/processed`) from ever being committed to git. |
| `.env.example` | A checked-in template listing every environment variable the app will use, with placeholder (fake) values. Copy it to `.env` and fill in real secrets locally; `.env` itself is gitignored. |
| `README.md` | This file. |

## Clean Architecture, in one sentence

Business rules (`domain/`) know nothing about use cases (`application/`);
use cases know nothing about specific databases or vendors
(`infrastructure/`); and nothing in the inner three layers knows that
FastAPI (`interfaces/`) exists — dependencies always point inward, which is
what lets any outer piece (a database, a vendor API, a web framework) be
replaced without touching the business logic. Full reasoning, diagrams, and
the "why" behind every naming decision: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Roadmap

These are the features this foundation is built to support, in the rough
order the project brief lists them:

1. ✅ Import Excel files containing executive data — the **Import Engine**
   (`infrastructure/importers/excel/`). Not yet implemented: CSV, Google
   Sheets, and SQL adapters for the same `SourceReaderPort`.
2. Clean and standardize the data.
3. Verify emails, phone numbers, LinkedIn profiles, and company information.
4. Detect professional inflection points (promotion, job change, resignation,
   company funding, etc.).
5. Generate AI-personalized outreach messages.
6. Send emails after a human review step.

## Handling sensitive data

This platform will process real people's personal and professional
information (names, emails, phone numbers, employers). `data/raw/` and
`data/processed/` are gitignored specifically so that this data never ends
up in git history — see [`data/README.md`](data/README.md) for details.
