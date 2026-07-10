# Infrastructure Layer

## What "infrastructure" means here
This is where we talk to the **outside world**: databases, third-party
APIs, file formats, email servers. Anything that involves a network call, a
file on disk, or a specific vendor's SDK belongs here.

## The rule for this folder
Infrastructure code **implements** the `ports/` (interfaces) defined in
`application/ports/`. For example, `application/ports/` might one day
declare `class EmailVerifierPort(Protocol): def verify(self, email: str) ->
bool: ...`, and a file in
`infrastructure/external_services/email_verification/` would provide a
concrete class like `ZeroBounceEmailVerifier` that fulfills that contract
using ZeroBounce's real API.

**Why bother with this split?** Vendors change. Today's email-verification
company might raise prices or shut down tomorrow. Because every use case in
`application/` only ever talks to the abstract port — never to
`ZeroBounceEmailVerifier` directly — swapping vendors means writing one new
class here and changing one line of configuration. No use case, and
nothing in `domain/`, ever needs to change.

## Sub-folders

| Folder | Purpose |
|---|---|
| `database/` | **Implemented (infrastructure only).** SQLAlchemy engine/session factories (`session.py`), the declarative `Base` (`base.py`, no tables yet), the concrete `SqlAlchemyUnitOfWork` (`unit_of_work.py`), and a `check_database_connectivity` health check (`health.py`). Concrete repository classes that implement the `domain/repositories/` interfaces are a future task. |
| `importers/` | Adapters that bring external tabular data **in** — one sub-folder per source technology, each implementing `application/ports/source_reader_port.py`. See `importers/README.md` for the full Import Engine design. |
| `importers/excel/` | **Implemented.** Reads `.xlsx` files (`ExcelSourceReader`, `ExcelFileValidator`, `ExcelSheetSelector`) — the technical detail of *how* a spreadsheet becomes plain, unmodified records. |
| `importers/csv/`, `importers/google_sheets/`, `importers/sql/` | Future sibling adapters for other tabular sources, implementing the same port — not built yet. |
| `enrichment/` | Adapters that implement `application/ports/enrichment_provider_port.py` — one sub-folder per external source, the same one-adapter-per-technology convention `importers/` uses. See `enrichment/company_website/README.md`. |
| `enrichment/company_website/` | **Implemented.** `CompanyWebsiteProvider` — fetches a company's website, respects `robots.txt`, finds its leadership/about/team page(s), and extracts publicly listed executives via DOM heuristics (no AI). |
| `enrichment/google_search/` | **Implemented.** `GoogleSearchProvider` — searches the public web for an executive via the Google Custom Search JSON API, generating configurable queries and converting every result into a `web_mention` `ObservationCandidate` (evidence only — no AI summarization, no change detection). |
| `enrichment/leadership_page/`, `enrichment/news/`, `enrichment/crm/`, `enrichment/dnb/`, `enrichment/linkedin/` | Future sibling providers, implementing the same port — not built yet. |
| `search/` | Adapters that implement `application/ports/search_provider_port.py` — the Search Layer's provider family (sibling to, and deliberately separate from, `enrichment/`). See `application/search/README.md` for why. |
| `search/company_crawler/` | **Implemented.** `CompanyCrawlerProvider` — the Search Layer's primary provider as of Version 1: crawls each executive's own company website (leadership/press/news pages, no third-party search engine) and returns `SearchResult`s only. See `search/company_crawler/README.md`. |
| `search/browser/` | **Implemented.** `BrowserSearchProvider` — drives a real, headless browser (Playwright) against a configured search-results page and returns `SearchResult`s only (no observation extraction). Wired into `run_pipeline.py` as an optional `fallback_only` provider, used only when the company crawl yields nothing. See `search/browser/README.md`. |
| `search/extraction/` | **Implemented.** `SearchExtractionEngine` — the RFC's Page Fetcher + Content Extractor + Observation Extraction stages: turns `SearchResult` URLs into `ObservationCandidate`s via deterministic HTML parsing and named rule-based fact patterns (no AI, no PDFs in V1). See `search/extraction/README.md`. |
| `search/bing/`, `search/brave/`, `search/serpapi/`, `search/tavily/`, `search/searchapi/`, `search/exa/` | Future sibling search providers, implementing the same port — not built yet. |
| `external_services/email_verification/` | Adapters that implement `application/ports/verification_provider_port.py`'s `EmailVerificationPort` — one sub-folder per vendor, same convention as `enrichment/`. See `email_verification/neverbounce/README.md`. |
| `external_services/email_verification/neverbounce/` | **Implemented.** `NeverBounceEmailProvider` — verifies email addresses via NeverBounce's v4 single-check API, with retry/timeout handling and full result mapping (valid/invalid/disposable/catch-all/unknown/rate-limited/timeout/API error). |
| `external_services/email_verification/zerobounce/`, `.../kickbox/`, `.../bouncer/` | Future sibling providers, implementing the same port — not built yet. |
| `external_services/phone_verification/` | Talks to whichever phone-verification vendor is chosen (e.g. Twilio Lookup, Numverify). |
| `external_services/linkedin/` | Talks to whichever LinkedIn/profile-data provider is chosen (e.g. Proxycurl). |
| `external_services/company_data/` | Talks to whichever company-info/funding-data provider is chosen (e.g. Clearbit, Crunchbase). |
| `external_services/ai_providers/` | Wraps the Anthropic (Claude) SDK calls used for generating personalized outreach messages. |
| `external_services/email_sending/` | Wraps SMTP / a transactional-email provider for actually sending the reviewed outreach emails. |

## Current status
The Excel Import Engine (`importers/excel/`), the `database/` package
(engine/session, Unit of Work, health check — see the table above), the
Company Website and Google Search enrichment providers
(`enrichment/company_website/`, `enrichment/google_search/`), the
Browser Search provider (`search/browser/`), the Search Extraction
Engine (`search/extraction/`), and the NeverBounce email
verification provider
(`external_services/email_verification/neverbounce/`) are implemented.
Every other `enrichment/`, `search/`, and `external_services/` folder
here is still empty on purpose; no other vendor integrations exist yet.
These folders exist so each future integration has one obvious, isolated
home, and so that no external SDK ever needs to be imported from
`domain/` or `application/`.

### `database/` — configuration

Local PostgreSQL for development is provided by the root `docker-compose.yml`
(`docker-compose up -d postgres`), with credentials matching
`.env.example`'s `DATABASE_URL`. Without it, `DATABASE_URL` falls back to a
zero-setup local SQLite file. Connection pool sizing
(`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_PRE_PING` in
`.env.example`) only takes effect against PostgreSQL — SQLite has no
comparable connection pool. Schema migrations are managed by Alembic (root
`alembic.ini` / `alembic/`), configured to read `DATABASE_URL` from
`core.config.get_settings()` rather than a hardcoded value, and pointed at
`Base.metadata` for future `--autogenerate` support once ORM models exist.
