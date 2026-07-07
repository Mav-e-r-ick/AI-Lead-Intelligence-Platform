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
| `repositories/` | **Interfaces (contracts)** describing how entities are saved/loaded — e.g. "a `LeadRepository` must be able to `get_by_id` and `save`." The actual database code that implements this contract lives in `infrastructure/`, not here. This split is what lets us swap PostgreSQL for MongoDB later without touching business rules. |
| `exceptions/` | Custom error types that describe business-rule violations in plain language (e.g. `InvalidEmailFormatError`), instead of relying on generic Python errors. |

## Current status
Empty on purpose. No entities, rules, or exceptions have been written yet —
this task is foundation only. These folders exist so future work has an
obvious, correctly-layered place to go.
