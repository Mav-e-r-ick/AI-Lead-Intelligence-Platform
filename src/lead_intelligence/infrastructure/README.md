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
| `enrichment/leadership_page/`, `enrichment/news/`, `enrichment/web_search/`, `enrichment/crm/`, `enrichment/dnb/`, `enrichment/linkedin/` | Future sibling providers, implementing the same port — not built yet. |
| `external_services/email_verification/` | Talks to whichever email-verification vendor is chosen (e.g. ZeroBounce, NeverBounce, Hunter.io). |
| `external_services/phone_verification/` | Talks to whichever phone-verification vendor is chosen (e.g. Twilio Lookup, Numverify). |
| `external_services/linkedin/` | Talks to whichever LinkedIn/profile-data provider is chosen (e.g. Proxycurl). |
| `external_services/company_data/` | Talks to whichever company-info/funding-data provider is chosen (e.g. Clearbit, Crunchbase). |
| `external_services/ai_providers/` | Wraps the Anthropic (Claude) SDK calls used for generating personalized outreach messages. |
| `external_services/email_sending/` | Wraps SMTP / a transactional-email provider for actually sending the reviewed outreach emails. |

## Current status
The Excel Import Engine (`importers/excel/`), the `database/` package
(engine/session, Unit of Work, health check — see the table above), and
the Company Website enrichment provider (`enrichment/company_website/`)
are implemented. Every other `enrichment/` and `external_services/` folder
here is still empty on purpose; no other vendor integrations exist yet.
These folders exist so each future integration has one obvious, isolated
home, and so that no external SDK ever needs to be imported from `domain/`
or `application/`.

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
