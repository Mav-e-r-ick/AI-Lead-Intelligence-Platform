# AI Lead Intelligence Platform

A production-grade platform that will eventually import executive data from
Excel, clean and verify it, detect professional inflection points (job
changes, promotions, funding events), generate AI-personalized outreach
messages, and send them after human review.

> **Status: Foundation + Import Engine + Cleaning Engine + Persistence
> Infrastructure + Identity Resolution Engine (V1) + Enrichment Provider
> Framework (V1) + Executive Comparison Engine (V1) + Inflection Detection
> Engine (V1) + Contact Verification Framework (V1) + NeverBounce Email
> Provider (V1) + Google Search Provider (V1) + Executive Processing
> Pipeline (V1) + Evaluation & Validation Module (V1) + Search Layer (V1)
> + Browser Search Provider (V1) + Search Extraction Engine (V1).** The project structure, configuration, and wiring are in
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
> A second concrete provider, the **Google Search Provider (Version 1)** —
> given an executive's name (plus company/title if known), generates a
> configurable set of search queries (`"<name>" "<company>"`, `"<name>"
> promotion`, `appointed`, `joins`, `resigned`, `leadership`), searches each
> via the Google Custom Search JSON API, and converts every result into a
> `web_mention` `ObservationCandidate` (title, URL, snippet, publication
> date, source domain) — pure evidence gathering, no AI summarization, no
> change detection — is also implemented (see
> [`infrastructure/enrichment/google_search/README.md`](src/lead_intelligence/infrastructure/enrichment/google_search/README.md)).
> Every other real source (Leadership Page, News, CRM, D&B, LinkedIn,
> other commercial APIs) is future work behind the same
> `EnrichmentProviderPort`. The **Executive Comparison Engine (Version 1)**
> — compares an existing (cleaned) executive record against newly
> collected `ObservationCandidate`s field by field (name, title, company,
> email, phone), using configurable exact or fuzzy strategies, and reports
> one of six verdicts (`MATCH`/`CHANGED`/`MISSING`/`NEW`/`CONFLICT`/
> `UNKNOWN`) plus a summary with a deterministic confidence score — is also
> implemented (see
> [`application/comparison/README.md`](src/lead_intelligence/application/comparison/README.md)).
> It only identifies differences; it never classifies what a difference
> means (no promotion/resignation/inflection detection) — that
> interpretation is the **Inflection Detection Engine (Version 1)**'s job:
> it converts a `ComparisonResult` into deterministic, explainable business
> events (Promotion, Demotion, Company Change, Possible Resignation,
> Contact Information Changed, Executive Newly Appeared, Executive No
> Longer Found), each with a confidence score, supporting evidence, and a
> human-readable explanation, via seven fixed detection rules plus a
> keyword-based title seniority ranking — no AI, no search, no
> verification (see
> [`application/inflection/README.md`](src/lead_intelligence/application/inflection/README.md)).
> The **Contact Verification Framework (Version 1)** — before an executive
> is contacted, their email address and phone number should still be
> confirmed valid: this framework defines `VerificationProviderPort` (and
> its `EmailVerificationPort`/`PhoneVerificationPort` specializations),
> the request/result/report shapes, per-provider priority/enabled
> configuration, and a `VerificationCoordinator` that runs every
> applicable provider and reports every result unresolved (it never picks
> a "winning" verdict when providers disagree) — is also implemented (see
> [`application/verification/README.md`](src/lead_intelligence/application/verification/README.md)).
> Its first concrete provider, the **NeverBounce Email Provider (Version
> 1)** — verifies one email address via NeverBounce's v4 single-check API,
> mapping every documented outcome (valid, invalid, disposable, catch-all,
> unknown, rate-limited, timeout, API error) onto the framework's
> `VerificationStatus`, with retries, timeouts, and logging — is also
> implemented (see
> [`infrastructure/external_services/email_verification/neverbounce/README.md`](src/lead_intelligence/infrastructure/external_services/email_verification/neverbounce/README.md)).
> Every other real provider (ZeroBounce, Kickbox, Bouncer, Twilio Lookup,
> Numverify, Abstract API) is future work behind the same ports. The
> **Executive Processing Pipeline (Version 1)** — an
> `ExecutiveProcessingOrchestrator` (`application/executive_pipeline/`)
> that processes one executive record end to end using every module
> above: enrichment (Company Website + Google Search, queried once per
> applicable subject type), the Executive Comparison Engine, the
> Inflection Detection Engine, and (only if configured) email
> verification — with per-stage error handling so one stage's failure
> never discards another's results, and one combined
> `ExecutiveProcessingReport` (executive name, providers executed,
> observations collected, comparison summary, detected inflections,
> verification results, processing duration, processing status) — is also
> implemented (see
> [`application/executive_pipeline/README.md`](src/lead_intelligence/application/executive_pipeline/README.md)).
> No new provider and no change to any existing engine or framework — pure
> orchestration. The **Evaluation & Validation Module (Version 1)** — a
> `PipelineRunner` (`application/evaluation/`) that runs every executive in
> a real Excel file through the Executive Processing Pipeline unchanged,
> and produces a CSV report (one row per executive: name, company, website
> searched, providers executed, results found per provider, comparison
> summary, detected inflections, verification status, processing duration,
> errors) plus a JSON summary of platform-wide metrics (success rate,
> failed searches, company websites found, Google searches completed,
> promotions/company-changes/missing-executives detected, verification
> success rate) — is also implemented (see
> [`application/evaluation/README.md`](src/lead_intelligence/application/evaluation/README.md)).
> No new provider, no AI, no automation, no redesign of any existing
> module — pure measurement of the platform as it exists today. The
> **Search Layer (Version 1)**, per the approved Search Layer RFC —
> `SearchProviderPort`, `SearchResult`/`SearchRequest`/`SearchResponse`
> (`application/dto/search_models.py`), and a `SearchCoordinator` +
> `SearchProviderRegistry` (`application/search/`) mirroring the
> Enrichment Provider Framework's own registry/priority/health-tracking
> pattern — separates *searching* (returning only title/url/snippet/
> source/rank) from *extracting* (turning a page into evidence), so a
> search provider can never return an observation. Its first concrete
> provider, **Browser Search (Version 1)** — `BrowserSearchProvider`
> (`infrastructure/search/browser/`), which drives a real, headless
> browser (Playwright) against an operator-configured search-results page,
> collects the first N result URLs per query, respects that search
> engine's own `robots.txt`, and retries/caches/logs — is also implemented
> (see [`application/search/README.md`](src/lead_intelligence/application/search/README.md)
> and [`infrastructure/search/browser/README.md`](src/lead_intelligence/infrastructure/search/browser/README.md)).
> No AI, no new business logic, no built-in default search engine (the
> operator must supply and be authorized to use their own target).
> **`BrowserSearchProvider` has since been superseded as the Search Layer's
> primary provider by `CompanyCrawlerProvider` (Version 1) — see roadmap
> item 14 below — and is now wired in only as an optional, lower-priority
> `fallback_only` provider.** The
> **Search Extraction Engine (Version 1)** (`infrastructure/search/extraction/`)
> completes the RFC's pipeline: it turns `SearchResult` URLs into
> structured `ObservationCandidate`s — downloading each destination page
> (respecting that domain's own robots.txt; PDFs skipped in V1),
> extracting the page title, visible text, and declared publication date
> via deterministic HTML parsing, and extracting executive
> name/title/company via a small, named set of rule-based announcement
> patterns (each extracted fact traceable to the exact rule that produced
> it) — no AI, no LLM, no guessing: unmatched pages yield only their
> `web_page` evidence candidate (see
> [`infrastructure/search/extraction/README.md`](src/lead_intelligence/infrastructure/search/extraction/README.md)).
> The **Executive Processing Pipeline (Version 2)**
> (`application/executive_pipeline/`) now wires all of the above
> together: `ExecutiveProcessingOrchestrator.process()` adds an Identity
> Resolution stage (records the engine's full decision on the report; the
> caller-supplied `subject_id` is kept for every other stage, since no
> identity persistence exists yet to resolve into), runs the Search Layer
> (Browser Search) alongside enrichment (Company Website), feeds every
> found `SearchResult` through the Search Extraction Engine, and combines
> both evidence paths' `ObservationCandidate`s before Comparison runs — as
> before, every stage has its own error handling, so one stage's failure
> never discards another's results. A new `process_batch()` runs many
> executives, continues past any one executive's failure (including a
> genuinely unexpected exception, not just an ordinary one), and returns
> one final `ExecutiveIntelligenceReport` — the "Final Executive
> Intelligence Report" — bundling every per-executive
> `ExecutiveProcessingReport` plus batch statistics (counts by status,
> error totals, execution time). No new provider, no AI, no messaging, no
> automation, and no change to any existing engine or framework — pure
> orchestration, connecting modules that were each already built and
> tested standalone (see
> [`application/executive_pipeline/README.md`](src/lead_intelligence/application/executive_pipeline/README.md)).
> No ORM models, concrete repositories, or tables exist yet, and Identity
> Resolution's lineage redirects, rollback windows, and full reviewer
> workflow are explicitly Version 2 — both deliberately deferred to future
> tasks. Every other business feature (domain entities, phone
> verification, AI generation, sending) is still an empty, clearly-labeled
> placeholder waiting for future work.

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

# 2b. Install this project itself in editable mode. The app code lives
#     under src/lead_intelligence/ (a "src layout") — this is what makes
#     "import lead_intelligence" resolve from any working directory, with
#     no PYTHONPATH to set by hand. One time per environment.
pip install -e .

# 3. Copy the example environment file and fill in real values later.
cp .env.example .env

# 4. (Optional) Start a local PostgreSQL matching .env.example. Without
#    this, DATABASE_URL still works against the zero-setup SQLite default.
docker-compose up -d postgres

# 5. Run the test suite (health-check smoke test + Import/Cleaning/
#    Persistence/Identity Resolution/Enrichment/Comparison/Inflection/
#    Verification/NeverBounce/GoogleSearch/ExecutiveProcessingPipeline/
#    Evaluation/Search/BrowserSearch unit + integration tests). The real
#    Playwright end-to-end test is opt-in and skipped by default (see
#    infrastructure/search/browser/README.md).
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

## Running the pipeline on a real Excel file, locally

```bash
cp .env.local.example .env.local   # DuckDuckGo-based BrowserSearchProvider fallback config
                                    # (CompanyCrawlerProvider, the primary search
                                    # provider, needs no configuration)
playwright install chromium        # once per machine
python setup_local.py              # verifies Python/Playwright/browser/network/config
python run_local.py path/to/your.xlsx --limit 10
```

`run_local.py` loads `.env.local`, runs `setup_local.py`'s pre-flight
checks, then delegates entirely to `run_pipeline.py`
(`ExecutiveProcessingOrchestrator.process_batch()`) — see
[`LOCAL_SETUP.md`](LOCAL_SETUP.md) for the full walkthrough, Playwright
installation troubleshooting, and what `--dev-mode`/`PIPELINE_DEV_MODE`
(Development Mode: don't let a network-policy failure trip
`ProviderHealthTracker`'s circuit breaker; real website failures are
unaffected) actually changes.

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
│   ├── README.md                # Explains the purpose of this folder
│   └── run_evaluation.py        # CLI: runs the Evaluation & Validation module's PipelineRunner on a real Excel file
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
│       │   └── exceptions/        # import_exceptions.py, cleaning_exceptions.py, identity_resolution_exceptions.py, enrichment_exceptions.py, comparison_exceptions.py, inflection_exceptions.py, verification_exceptions.py
│       ├── application/          # Use cases (what the system can DO)
│       │   ├── README.md
│       │   ├── use_cases/         # import_dataset.py, clean_dataset.py, resolve_identity.py, enrich_subject.py, compare_executive.py, detect_inflections.py, verify_contact.py, process_executive.py
│       │   ├── services/          # Logic shared across use cases (none yet)
│       │   ├── ports/             # source_reader_port.py, cleaning_rule_port.py, identity_candidate_port.py, enrichment_provider_port.py, verification_provider_port.py
│       │   ├── dto/               # models.py, cleaning_models.py, identity_resolution_models.py, enrichment_models.py, comparison_models.py, inflection_models.py, verification_models.py, executive_pipeline_models.py, evaluation_models.py
│       │   ├── cleaning/          # Cleaning Engine — see cleaning/README.md (68 rules, CLN-001..068)
│       │   │   └── rules/          # One module per CLEANING_RULES.md category
│       │   ├── identity_resolution/ # Identity Resolution Engine (V1) — see identity_resolution/README.md
│       │   ├── enrichment/        # Enrichment Provider Framework (V1) — see enrichment/README.md
│       │   ├── comparison/        # Executive Comparison Engine (V1) — see comparison/README.md
│       │   ├── inflection/        # Inflection Detection Engine (V1) — see inflection/README.md
│       │   ├── verification/      # Contact Verification Framework (V1) — see verification/README.md
│       │   ├── executive_pipeline/ # Executive Processing Pipeline (V2) — see executive_pipeline/README.md
│       │   ├── evaluation/        # Evaluation & Validation Module (V1) — see evaluation/README.md
│       │   └── search/            # Search Layer (V1) — see search/README.md
│       ├── infrastructure/       # Talks to databases & third-party vendors
│       │   ├── README.md
│       │   ├── database/          # SQLAlchemy engine/session/base, SqlAlchemyUnitOfWork, health check (no tables yet)
│       │   ├── importers/         # Import Engine — see importers/README.md
│       │   │   └── excel/          # ExcelSourceReader, ExcelFileValidator, ExcelSheetSelector
│       │   ├── enrichment/        # Enrichment providers — see enrichment/company_website/README.md
│       │   │   ├── company_website/ # CompanyWebsiteProvider (V1) — robots.txt, discovery, extraction, retry/timeout/cache
│       │   │   └── google_search/   # GoogleSearchProvider (V1) — configurable queries, retry/timeout/cache, web_mention observations
│       │   ├── search/            # Search providers + extraction — see search/company_crawler/README.md
│       │   │   ├── company_crawler/ # CompanyCrawlerProvider (V1) — primary provider; Playwright + BeautifulSoup/lxml, crawls the company's own site, no AI
│       │   │   ├── browser/         # BrowserSearchProvider (V1) — optional fallback_only provider; Playwright, configurable engine/selectors, robots.txt, retry/timeout/cache
│       │   │   └── extraction/      # SearchExtractionEngine (V1) — SearchResult URLs -> ObservationCandidates, rule-based, no AI
│       │   └── external_services/ # One sub-folder per vendor category:
│       │       ├── email_verification/
│       │       │   └── neverbounce/  # NeverBounceEmailProvider (V1) — retry/timeout, full result mapping
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
    │   ├── company_website/        # Company Website Provider unit tests
    │   ├── comparison/             # Executive Comparison Engine unit tests
    │   ├── inflection/             # Inflection Detection Engine unit tests
    │   ├── verification/           # Contact Verification Framework unit tests
    │   ├── neverbounce/            # NeverBounce email provider unit tests
    │   ├── google_search/          # Google Search provider unit tests
    │   ├── executive_pipeline/     # Executive Processing Pipeline unit tests
    │   ├── evaluation/             # Evaluation & Validation Module unit tests
    │   ├── search/                 # Search Layer framework unit tests
    │   ├── company_crawler/        # CompanyCrawlerProvider unit tests (mocked Playwright)
    │   ├── browser_search/         # BrowserSearchProvider unit tests (mocked Playwright)
    │   └── search_extraction/      # Search Extraction Engine unit tests (mocked HTTP)
    ├── integration/               # Tests spanning multiple pieces
    │   ├── test_health.py          # Proves the foundation runs and the database is reachable
    │   ├── test_executive_pipeline.py # Full pipeline (V1 stages) through real (HTTP-mocked) providers
    │   ├── test_executive_intelligence_pipeline.py # Full V2 pipeline (+ identity resolution, search, extraction) end to end
    │   └── test_browser_search_e2e.py # Real Playwright + local HTTP server (opt-in, RUN_BROWSER_SEARCH_E2E=1)
    └── fixtures/                  # excel_builder.py — synthetic .xlsx fixtures for tests
```

Every folder that isn't self-explanatory has its own `README.md` right
inside it — read those for the full reasoning on that specific layer. This
top-level table is the map; the per-folder READMEs are the terrain.

## What each root file is for

| File | Purpose |
|---|---|
| `requirements.txt` | Every third-party package the *running app* needs, grouped by which future feature it supports, with comments explaining each choice. Install with `pip install -r requirements.txt`. |
| `pyproject.toml` | Packaging metadata that makes `lead_intelligence` (under `src/`) an installable package — `pip install -e .` is what lets `import lead_intelligence` resolve from any working directory, with no `PYTHONPATH` needed. |
| `requirements-dev.txt` | Additional packages needed only for development (pytest, black, ruff, mypy, pre-commit) — never installed on a production server. |
| `.gitignore` | Prevents secrets (`.env`), generated files (`__pycache__`, caches), local databases, and — importantly — real lead data (`data/raw`, `data/processed`) from ever being committed to git. |
| `.env.example` | A checked-in template listing every environment variable the app will use, with placeholder (fake) values. Copy it to `.env` and fill in real secrets locally; `.env` itself is gitignored. |
| `docker-compose.yml` | Runs a local PostgreSQL container with credentials matching `.env.example`, so `DATABASE_URL` works out of the box with `docker-compose up -d postgres`. |
| `alembic.ini` / `alembic/` | Migration tooling configuration. `alembic/env.py` reads `DATABASE_URL` from `core.config.get_settings()` (never hardcoded), and points at `Base.metadata` for future autogenerate support. No migrations exist yet — no ORM models exist yet. |
| `.env.local.example` | Checked-in sample `BrowserSearchProvider` (DuckDuckGo) + Development Mode configuration for `run_local.py`/`run_pipeline.py`. Copy to `.env.local` (gitignored) to use — see [`LOCAL_SETUP.md`](LOCAL_SETUP.md). |
| `setup_local.py` | Verifies a developer laptop is ready to run the pipeline against real data (Python version, Playwright, browser, network, config, output directory) — checks only, no business logic. |
| `run_local.py` | Loads `.env.local`, runs `setup_local.py`'s checks, then delegates to `run_pipeline.py` — see [`LOCAL_SETUP.md`](LOCAL_SETUP.md). |
| `run_pipeline.py` | Runs `ExecutiveProcessingOrchestrator.process_batch()` over a real Excel file and writes `results.xlsx` / `processing_report.json` / `logs/`. |
| `LOCAL_SETUP.md` | Full walkthrough for running the pipeline locally with real internet access: Playwright installation, `.env.local`, `setup_local.py`, `run_local.py`, and Development Mode. |
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
   their results — plus two concrete providers: the **Company Website
   Provider (Version 1)** (`infrastructure/enrichment/company_website/`):
   fetches a company's homepage, respects `robots.txt`, discovers
   leadership/about/team pages, and extracts executive name/title/
   biography/contact info via DOM heuristics (no AI), with retries,
   timeouts, and caching; and the **Google Search Provider (Version 1)**
   (`infrastructure/enrichment/google_search/`): generates configurable
   search queries for an executive (name+company, promotion, appointed,
   joins, resigned, leadership), searches each via the Google Custom
   Search JSON API, and converts every result into a `web_mention`
   `ObservationCandidate` (title, URL, snippet, publication date, source
   domain) — pure evidence gathering, with retries, timeouts, and caching,
   no AI summarization or change detection. Not yet implemented: every
   other concrete provider (Leadership Page, News, CRM, D&B, LinkedIn,
   other commercial APIs) — each is a future task behind the same port.
6. ✅ Identify differences between existing records and newly collected
   information — the **Executive Comparison Engine (Version 1)**
   (`application/comparison/`): compares name, title, company, email, and
   phone between an existing (cleaned) record and new
   `ObservationCandidate`s, using configurable exact (email, phone) or
   fuzzy (name, title, company) strategies, and reports
   `MATCH`/`CHANGED`/`MISSING`/`NEW`/`CONFLICT`/`UNKNOWN` per field plus a
   summary with a deterministic confidence score. Deliberately does not
   classify what a difference means — no promotion/resignation/inflection
   detection, no AI, no verification.
7. ✅ Convert technical differences into business events — the
   **Inflection Detection Engine (Version 1)** (`application/inflection/`):
   seven fixed, deterministic rules over a `ComparisonResult` detect
   Promotion, Demotion, Company Change, Possible Resignation, Contact
   Information Changed, Executive Newly Appeared, and Executive No Longer
   Found, each with a confidence score (the rule's own reliability
   discounted by the comparison's own confidence), supporting evidence,
   and a human-readable explanation. Title-change direction (promotion vs.
   demotion) uses a keyword-based seniority ranking, not AI. No AI, no
   search, no verification, no outreach messaging.
8. ✅ Verify contact details before outreach — the **Contact Verification
   Framework (Version 1)** (`application/verification/`):
   `VerificationProviderPort` (with `EmailVerificationPort`/
   `PhoneVerificationPort` specializations), request/result/report shapes,
   per-provider priority/enabled configuration, and a
   `VerificationCoordinator` that runs every applicable provider and
   reports every result unresolved rather than picking a winner. Its first
   concrete provider, the **NeverBounce Email Provider (Version 1)**
   (`infrastructure/external_services/email_verification/neverbounce/`) —
   verifies one email address via NeverBounce's v4 single-check API,
   mapping valid/invalid/disposable/catch-all/unknown/rate-limited/
   timeout/API-error outcomes onto `VerificationStatus`, with retries,
   timeouts, and logging — is also implemented. Every other provider
   (ZeroBounce, Kickbox, Bouncer, Twilio Lookup, Numverify, Abstract API)
   is future work behind the same ports. No phone verification, no
   LinkedIn profile or company-information verification, no message
   sending, no AI.
9. ✅ Process one executive end to end using every module already built —
   the **Executive Processing Pipeline (Version 1)**
   (`application/executive_pipeline/`): an `ExecutiveProcessingOrchestrator`
   that runs enrichment (Company Website + Google Search, queried once per
   applicable subject type — Person for Google Search, Company for
   Company Website), aggregates the collected `ObservationCandidate`s,
   runs the Executive Comparison Engine, runs the Inflection Detection
   Engine, and — only if a `VerificationCoordinator` was configured —
   verifies the executive's already-known email address, producing one
   `ExecutiveProcessingReport` (executive name, providers executed,
   observations collected, comparison summary, detected inflections,
   verification results, processing duration, processing status). Each
   stage has its own error handling, so one stage's failure never
   discards another's results. No new provider, no AI, no messaging, no
   automation, and no change to any existing engine or framework.
10. ✅ Measure how well the platform performs on real data — the
    **Evaluation & Validation Module (Version 1)** (`application/evaluation/`):
    a `PipelineRunner` that imports, cleans, and runs every executive in a
    real Excel file through the unmodified Executive Processing Pipeline,
    producing a CSV report (one row per executive, including providers
    executed, results found per provider, comparison summary, detected
    inflections, verification status, processing duration, and errors)
    and a JSON summary of platform-wide metrics (success rate, failed
    searches, company websites found, Google searches completed,
    promotions/company-changes/missing-executives detected, verification
    success rate). No new provider, no AI, no automation, no redesign of
    any existing module — pure measurement.
11. ✅ Separate searching from extracting, and add a second, credential-free
    way to gather public web evidence — the **Search Layer (Version 1)**,
    per the approved Search Layer RFC (`application/search/`,
    `application/ports/search_provider_port.py`,
    `application/dto/search_models.py`): a `SearchProviderPort` that
    returns only `SearchResult`s (title/url/snippet/source/rank), and a
    `SearchCoordinator`/`SearchProviderRegistry` mirroring the Enrichment
    Provider Framework's own registry/priority/health-tracking pattern —
    structurally incapable of returning an observation. Its first
    concrete provider, **Browser Search (Version 1)**
    (`infrastructure/search/browser/`): `BrowserSearchProvider` drives a
    real, headless browser (Playwright) against an operator-configured
    search-results page, builds configurable queries (reusing Google
    Search's own query-template engine), collects the first N result URLs
    per query, respects that search engine's own `robots.txt`, and
    retries/caches/logs. No built-in default search engine — the operator
    supplies and must be authorized to use their own target. No AI, no
    new business logic, no observation extraction, no page-fetching
    beyond the search engine's own results page.
12. ✅ Turn found URLs into structured evidence — the **Search Extraction
    Engine (Version 1)** (`infrastructure/search/extraction/`):
    `SearchExtractionEngine` converts `SearchResult`s into
    `ObservationCandidate`s by downloading each destination page
    (per-domain robots.txt, retry/timeout/caching; PDFs skipped in V1),
    extracting the page title, visible text, and declared publication
    date via deterministic HTML parsing (BeautifulSoup), and extracting
    executive name/title/company via named, rule-based announcement
    patterns — every fetched page yields a `web_page` evidence candidate
    (raw search snippet preserved verbatim), every extracted fact is
    traceable to the exact pattern that produced it, and nothing is ever
    guessed. No AI, no LLM.
13. ✅ Wire Identity Resolution, the Search Layer, and the Search
    Extraction Engine into the Executive Processing Pipeline — the
    **Executive Processing Pipeline (Version 2)**
    (`application/executive_pipeline/`): `ExecutiveProcessingOrchestrator`
    adds an Identity Resolution stage, runs the Search Layer (Browser
    Search) alongside enrichment (Company Website), feeds every found
    `SearchResult` through the Search Extraction Engine, and combines both
    evidence paths' observations before Comparison runs. A new
    `process_batch()` processes many executives, continues past any one
    executive's failure, and returns one final `ExecutiveIntelligenceReport`
    bundling every per-executive report plus batch statistics. No new
    provider, no AI, no messaging, no automation, no redesign of any
    existing module — pure orchestration (see
    [`application/executive_pipeline/README.md`](src/lead_intelligence/application/executive_pipeline/README.md)).
14. ✅ Replace search-engine querying with crawling each executive's own
    company website — the **Company Crawler Provider (Version 1)**
    (`infrastructure/search/company_crawler/`): `CompanyCrawlerProvider`
    is now the Search Layer's primary `SearchProviderPort`, opening the
    company website already on file, prioritizing internal links whose
    path/text suggest leadership/management/executive/board/about/team/
    people/press/news content (deterministic keyword scoring, no AI),
    ignoring login/privacy/product pages and paginated careers listings,
    and crawling breadth-first up to a bounded depth/page count via
    Playwright + BeautifulSoup/lxml. It still returns only `SearchResult`s
    — the unmodified `SearchExtractionEngine` (widened to also recognize
    `email`/`phone`/`linkedin_url`/`published_at` facts, a common shape on
    leadership/bio pages) is still what turns those into
    `ObservationCandidate`s, and Identity Resolution/Comparison/Inflection/
    Verification are untouched. `BrowserSearchProvider` is now wired in as
    an optional, lower-priority `fallback_only` provider — `run_pipeline.py`
    only runs it when the company crawl itself contributed zero
    `SearchResult`s for that executive (see
    [`infrastructure/search/company_crawler/README.md`](src/lead_intelligence/infrastructure/search/company_crawler/README.md)
    for the exact fallback semantics and its known Version 1 limitations).
    No AI, no LLM, no paid APIs, no change to
    `ExecutiveProcessingOrchestrator`.
15. Generate AI-personalized outreach messages.
16. Send emails after a human review step.

## Handling sensitive data

This platform will process real people's personal and professional
information (names, emails, phone numbers, employers). `data/raw/` and
`data/processed/` are gitignored specifically so that this data never ends
up in git history — see [`data/README.md`](data/README.md) for details.
