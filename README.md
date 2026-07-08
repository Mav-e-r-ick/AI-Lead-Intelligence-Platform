# AI Lead Intelligence Platform

A production-grade platform that will eventually import executive data from
Excel, clean and verify it, detect professional inflection points (job
changes, promotions, funding events), generate AI-personalized outreach
messages, and send them after human review.

> **Status: Foundation + Import Engine + Cleaning Engine + Persistence
> Infrastructure + Identity Resolution Engine (V1) + Enrichment Provider
> Framework (V1).** The project structure, configuration, and wiring are in
> place. The **Import Engine** (reading Excel files into plain, unmodified
> records — see
> [`infrastructure/importers/README.md`](src/lead_intelligence/infrastructure/importers/README.md))
> and the **Cleaning Engine** (68 rules, normalizing and flagging that data —
> see [`docs/CLEANING_RULES.md`](docs/CLEANING_RULES.md) and
> [`application/cleaning/README.md`](src/lead_intelligence/application/cleaning/README.md))
> are both implemented, tested, and verified end-to-end against the reference
> dataset. The **Persistence Infrastructure** — PostgreSQL/SQLAlchemy
> engine and session management, a Unit of Work abstraction, the repository
> *interfaces* for every object identified in the Persistence Architecture,
> dependency injection, Alembic migrations, and a `/health/database`
> readiness check — is also in place (see `domain/repositories/`,
> `infrastructure/database/`). The **Identity Resolution Engine (Version 1)**
> — signal extraction, Strong/Moderate/Weak identifier scoring, candidate
> generation, auto-merge/candidate-review/new-identity decisions, and
> confidence recomputation, per the approved Identity Resolution RFC — is
> implemented as pure, deterministic application logic (see
> [`application/identity_resolution/README.md`](src/lead_intelligence/application/identity_resolution/README.md)).
> The **Enrichment Provider Framework (Version 1)** — the provider
> interface, request/response shapes, a provider registry, priority
> ordering, refresh policy, health tracking (a lightweight circuit
> breaker), and a coordinator that runs every applicable provider and
> combines their results — is also implemented (see
> [`application/enrichment/README.md`](src/lead_intelligence/application/enrichment/README.md)),
> along with its first concrete provider, the **Company Website Provider
> (Version 1)** — fetches a company's homepage, respects `robots.txt`,
> discovers leadership/about/team pages, and extracts executive name,
> title, biography, and contact info via DOM heuristics (no AI), with
> retries, timeouts, and caching (see
> [`infrastructure/enrichment/company_website/README.md`](src/lead_intelligence/infrastructure/enrichment/company_website/README.md)).
> Every other real source (Leadership Page, News, Public Web Search, CRM,
> D&B, LinkedIn, other commercial APIs) is future work behind the same
> `EnrichmentProviderPort`. No ORM models, concrete repositories, or
> tables exist yet, and Identity Resolution's lineage redirects, rollback
> windows, and full reviewer workflow are explicitly Version 2 — both
> deliberately deferred to future tasks. Every other business feature
> (domain entities, verification, inflection-point detection, AI
> generation, sending) is still an empty, clearly-labeled placeholder
> waiting for future work.

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

# 4. (Optional) Start a local PostgreSQL matching .env.example. Without
#    this, DATABASE_URL still works against the zero-setup SQLite default.
docker-compose up -d postgres

# 5. Run the test suite (health-check smoke test + Import/Cleaning/
#    Persistence/Identity Resolution/Enrichment unit tests).
pytest

# 6. Run the API and confirm the foundation actually boots.
uvicorn lead_intelligence.interfaces.api.main:app --reload
# then visit http://127.0.0.1:8000/health -> {"status": "ok"}
# and http://127.0.0.1:8000/health/database -> {"status": "ok", "error": null}
```

Alembic (schema migrations) is configured but has no migrations to run yet
— no ORM models exist, so there is nothing to generate a migration for.
Once models exist, the usual commands apply: `alembic revision --autogenerate
-m "..."` then `alembic upgrade head`.

## Project layout

```
.
├── .env.example              # Template listing every config value the app needs (fake values)
├── .gitignore                 # Tells git which files to never track (secrets, caches, PII data)
├── docker-compose.yml           # Local PostgreSQL, matching .env.example's DATABASE_URL
├── alembic.ini                  # Alembic (migrations) configuration
├── alembic/                     # Alembic environment + versions/ (no migrations yet — no ORM models yet)
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
│       │   ├── repositories/      # Repository + Unit of Work *interfaces* (10 named + base classes)
│       │   └── exceptions/        # import_exceptions.py, cleaning_exceptions.py, identity_resolution_exceptions.py, enrichment_exceptions.py
│       ├── application/          # Use cases (what the system can DO)
│       │   ├── README.md
│       │   ├── use_cases/         # import_dataset.py, clean_dataset.py, resolve_identity.py, enrich_subject.py
│       │   ├── services/          # Logic shared across use cases (none yet)
│       │   ├── ports/             # source_reader_port.py, cleaning_rule_port.py, identity_candidate_port.py, enrichment_provider_port.py
│       │   ├── dto/               # models.py, cleaning_models.py, identity_resolution_models.py, enrichment_models.py
│       │   ├── cleaning/          # Cleaning Engine — see cleaning/README.md (68 rules, CLN-001..068)
│       │   │   └── rules/          # One module per CLEANING_RULES.md category
│       │   ├── identity_resolution/ # Identity Resolution Engine (V1) — see identity_resolution/README.md
│       │   └── enrichment/        # Enrichment Provider Framework (V1) — see enrichment/README.md
│       ├── infrastructure/       # Talks to databases & third-party vendors
│       │   ├── README.md
│       │   ├── database/          # SQLAlchemy engine/session/base, SqlAlchemyUnitOfWork, health check (no tables yet)
│       │   ├── importers/         # Import Engine — see importers/README.md
│       │   │   └── excel/          # ExcelSourceReader, ExcelFileValidator, ExcelSheetSelector
│       │   ├── enrichment/        # Enrichment providers — see enrichment/company_website/README.md
│       │   │   └── company_website/ # CompanyWebsiteProvider (V1) — robots.txt, discovery, extraction, retry/timeout/cache
│       │   └── external_services/ # One sub-folder per vendor category:
│       │       ├── email_verification/
│       │       ├── phone_verification/
│       │       ├── linkedin/
│       │       ├── company_data/
│       │       ├── ai_providers/     # Anthropic (Claude) SDK wrapper
│       │       └── email_sending/
│       └── interfaces/           # How the outside world talks to us
│           ├── README.md
│           ├── api/                # FastAPI app (main.py: /health, /health/database; dependencies.py: DI providers)
│           ├── cli/                # Future command-line entry points
│           └── schemas/            # Pydantic request/response models for the API
└── tests/
    ├── README.md
    ├── conftest.py                # Forces an in-memory DATABASE_URL for tests (no stray local_dev.db)
    ├── unit/
    │   ├── importer/               # Import Engine unit tests
    │   ├── cleaning/               # Cleaning Engine unit tests
    │   ├── persistence/            # Repository interfaces, Unit of Work, session factory, health check
    │   ├── identity_resolution/    # Identity Resolution Engine unit tests
    │   ├── enrichment/             # Enrichment Provider Framework unit tests
    │   └── company_website/        # Company Website Provider unit tests
    ├── integration/               # Tests spanning multiple pieces
    │   └── test_health.py          # Proves the foundation runs and the database is reachable
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
| `docker-compose.yml` | Runs a local PostgreSQL container with credentials matching `.env.example`, so `DATABASE_URL` works out of the box with `docker-compose up -d postgres`. |
| `alembic.ini` / `alembic/` | Migration tooling configuration. `alembic/env.py` reads `DATABASE_URL` from `core.config.get_settings()` (never hardcoded), and points at `Base.metadata` for future autogenerate support. No migrations exist yet — no ORM models exist yet. |
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
2. ✅ Clean and standardize the data — the **Cleaning Engine**
   (`application/cleaning/`), implementing all 68 rules specified in
   [`docs/CLEANING_RULES.md`](docs/CLEANING_RULES.md) (`CLN-001`–`CLN-068`).
3. ✅ Persistence foundation — PostgreSQL/SQLAlchemy engine + session
   management, Unit of Work, repository *interfaces* for every object in
   the Persistence Architecture, DI, Alembic, and a `/health/database`
   check (`domain/repositories/`, `infrastructure/database/`). Domain
   entities, ORM models, and concrete repositories are not yet
   implemented — deliberately deferred to a future task.
4. ✅ Resolve identities — the **Identity Resolution Engine (Version 1)**
   (`application/identity_resolution/`): extract Strong/Moderate/Weak
   identity signals, generate candidate matches, compute explainable
   confidence scores, and decide auto-merge / candidate-review / new-
   identity, per the approved Identity Resolution RFC. Not yet
   implemented (Version 2): identity lineage redirects, merge rollback
   windows, and the full reviewer workflow.
5. ✅ Collect executive information from multiple sources without coupling
   the platform to any one of them — the **Enrichment Provider Framework
   (Version 1)** (`application/enrichment/`): `EnrichmentProviderPort`, a
   provider registry, priority ordering, refresh policy, health tracking,
   and a coordinator that runs every applicable provider and combines
   their results — plus its first concrete provider, the **Company
   Website Provider (Version 1)**
   (`infrastructure/enrichment/company_website/`): fetches a company's
   homepage, respects `robots.txt`, discovers leadership/about/team
   pages, and extracts executive name/title/biography/contact info via
   DOM heuristics (no AI), with retries, timeouts, and caching. Not yet
   implemented: every other concrete provider (Leadership Page, News,
   Public Web Search, CRM, D&B, LinkedIn, other commercial APIs) — each is
   a future task behind the same port.
6. Verify emails, phone numbers, LinkedIn profiles, and company information.
7. Detect professional inflection points (promotion, job change, resignation,
   company funding, etc.).
8. Generate AI-personalized outreach messages.
9. Send emails after a human review step.

## Handling sensitive data

This platform will process real people's personal and professional
information (names, emails, phone numbers, employers). `data/raw/` and
`data/processed/` are gitignored specifically so that this data never ends
up in git history — see [`data/README.md`](data/README.md) for details.
