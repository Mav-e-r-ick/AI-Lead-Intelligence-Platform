# Domain Layer

## What "domain" means here
The **domain** is the beating heart of the business itself — the concepts and
rules that would still be true even if we had no database, no API, no
website, and no AI provider. Think of it as "what is a Lead? what makes a
lead's data valid? what does 'promoted' mean?" — independent of *how* that
data is stored or displayed.

## The Golden Rule of this folder
**Nothing in `domain/` is allowed to import from `application/`,
`infrastructure/`, or `interfaces/`.** The domain must not know that
FastAPI, SQLAlchemy, or Anthropic's API even exist. This is the most
important rule in Clean Architecture: dependencies point *inward*, toward
the domain, never outward from it.

Why this matters for you as a learner: it means you could delete the entire
database, swap FastAPI for Flask, or replace Anthropic with another AI
provider, and not change a single line in this folder. The business rules
survive every technology decision.

## Sub-folders

| Folder | Purpose |
|---|---|
| `entities/` | The core business "nouns" — e.g. a `Lead`, an `Executive`, a `Company`. An entity has an identity that persists over time (the same lead is still "the same lead" even after its phone number changes). |
| `value_objects/` | Small, immutable concepts defined entirely by their value, not an identity — e.g. an `EmailAddress` or `PhoneNumber` type that knows what a *valid* email looks like. Two value objects with the same value are considered equal. |
| `repositories/` | **Implemented** (interfaces only). Contracts describing how entities are saved/loaded — e.g. "an `ObservationRepository` must be able to `add` and `find_evidence`." The actual database code that implements these contracts lives in `infrastructure/database/`, not here. This split is what lets us swap PostgreSQL for another storage technology later without touching business rules. |
| `exceptions/` | Custom error types that describe business-rule violations in plain language (e.g. `InvalidEmailFormatError`), instead of relying on generic Python errors. **Implemented:** `import_exceptions.py` (Import Engine, see `infrastructure/importers/README.md`), `cleaning_exceptions.py` (Cleaning Engine, see `application/cleaning/README.md`), `identity_resolution_exceptions.py` (Identity Resolution Engine, see `application/identity_resolution/README.md`). |

## Current status
`exceptions/import_exceptions.py`, `exceptions/cleaning_exceptions.py`, and
`exceptions/identity_resolution_exceptions.py` are implemented.
`repositories/` is now implemented as well — see below. `entities/` and
`value_objects/` remain empty on purpose — no business
entities have been written yet, so the repository interfaces are generic
over a placeholder `TypeVar` (e.g. `TObservation`) rather than a concrete
class. These folders exist so future work has an obvious, correctly-layered
place to go.

### `repositories/` — Repository & Unit of Work interfaces

Implements the interfaces defined in the approved Persistence Architecture.
Every named interface is generic over its (not-yet-implemented) entity
type, and built on one of three generic base classes in
`base_repository.py`:

| Base class | Exposes | Covers |
|---|---|---|
| `Repository[TEntity, TId]` | `get_by_id`, `exists` | Every repository (the minimal read contract). |
| `AppendOnlyRepository` | + `add` (no `update`) | `ObservationRepository`, `SnapshotRepository`, `RelationshipRepository`, `VerificationRepository`, `AIInsightRepository`, `OutreachHistoryRepository`, `AuditLogRepository` — every ledger-shaped, immutable table. |
| `MutableRepository` | + `add`, `update` | `LeadRepository` only — the one genuinely, generically mutable, CRM-style record. |

`DigitalTwinRepository` and `CompanyRepository` are built on plain
`Repository`, with an explicit, narrow `update_status()` instead of a
generic `update()` — visible at every call site that status flags
(suppressed/retired, active) are the *only* thing about them that ever
changes; their factual history lives in immutable Snapshots instead.

`unit_of_work.py` defines the abstract `UnitOfWork` — a pure
begin/commit/rollback/end lifecycle contract with no SQLAlchemy (or even
"Session") in sight, per this layer's Clean Architecture rule. The
concrete implementation, `SqlAlchemyUnitOfWork`, lives in
`infrastructure/database/unit_of_work.py`.

No concrete repository classes exist yet — only these interfaces. That is
deliberate: implementing them requires the domain entities in `entities/`,
which is a future task.
