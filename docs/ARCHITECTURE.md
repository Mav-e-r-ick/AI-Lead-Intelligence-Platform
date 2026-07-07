# Architecture Deep Dive

This document explains **why** the project is organized the way it is. The
root `README.md` tells you *where* everything is; this file explains the
reasoning, for readers who want to understand the design, not just use it.

## 1. Why "Clean Architecture" at all?

Clean Architecture (a term popularized by Robert C. Martin, aka "Uncle
Bob") organizes code into concentric layers, with one strict rule:

> **Dependencies only point inward.** Outer layers may depend on inner
> layers. Inner layers must never depend on outer layers.

```
 ┌─────────────────────────────────────────────────────────┐
 │  interfaces/   (API, CLI — how the outside world talks   │
 │                 to us)                                   │
 │   ┌───────────────────────────────────────────────────┐  │
 │   │  infrastructure/  (databases, third-party APIs —   │  │
 │   │                    how WE talk to the outside world)│ │
 │   │   ┌───────────────────────────────────────────┐    │  │
 │   │   │  application/  (use cases — the things the │    │  │
 │   │   │                 app can DO)                 │    │  │
 │   │   │   ┌───────────────────────────────────┐     │    │  │
 │   │   │   │  domain/  (business concepts and   │     │    │  │
 │   │   │   │            rules — the "nouns")     │     │    │  │
 │   │   │   └───────────────────────────────────┘     │    │  │
 │   │   └───────────────────────────────────────────┘    │  │
 │   └───────────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────┘
        arrows of dependency point INWARD, toward domain/
```

### The beginner-friendly version
Imagine `domain/` is a recipe for a cake — flour, sugar, eggs, steps. It
doesn't care if you bake it in a gas oven or an electric one. `infrastructure/`
is the actual oven brand. `interfaces/` is the restaurant menu customers
order from. If you switch oven brands (say, from PostgreSQL to MongoDB, or
from ZeroBounce to NeverBounce for email verification), the recipe (business
rules) doesn't change at all — only the oven-specific code does.

### Why this matters for THIS project specifically
Every feature listed in the project brief involves at least one
third-party vendor that could change:
- Excel parsing library
- Email verification vendor
- Phone verification vendor
- LinkedIn/company-data vendor
- AI provider (Anthropic today, maybe something else tomorrow)
- Email-sending provider

By keeping vendor-specific code confined to `infrastructure/`, behind
interfaces (`ports`) owned by `application/`, we can swap any one of these
later by writing one new adapter class — never by rewriting business logic.

## 2. Why 4 layers, and why these particular names?

| Layer | Uncle Bob's name | Question it answers |
|---|---|---|
| `domain/` | Entities | "What IS a lead? What makes contact info valid?" |
| `application/` | Use Cases | "What can the SYSTEM DO? (import, verify, generate, send)" |
| `infrastructure/` | Interface Adapters (data side) | "HOW do we talk to a real database/API?" |
| `interfaces/` | Interface Adapters (delivery side) | "HOW does a human/HTTP client talk to US?" |

Two folders both map to Uncle Bob's "Interface Adapters" ring because that
ring has two directions of communication: infrastructure/ handles
*outgoing* calls (to databases, vendor APIs), while interfaces/ handles
*incoming* calls (from an API client or CLI user). Splitting them makes the
direction of each dependency immediately obvious from the folder name.

## 3. Why is there also a `core/` folder outside all 4 layers?

`core/` holds things that are genuinely cross-cutting and have no business
meaning at all: reading configuration (`config.py`) and setting up logging
(`logging.py`). Every layer is allowed to use `core/`, because "what log
level is configured" isn't a business rule, an outside-world detail, or a
delivery mechanism — it's just shared plumbing.

## 4. Why `src/` layout instead of putting `lead_intelligence/` at the repo root?

Putting the package inside `src/` (rather than directly in the repo root)
is a well-established Python convention that prevents a subtle but common
bug: without it, running `pytest` or `python` from the repo root can
accidentally import your local, uninstalled source files instead of the
properly-installed package, hiding packaging mistakes until it's too late
(e.g. a deploy). It costs one extra folder level and buys real safety.

## 5. Why separate `application/dto/` from `domain/entities/` and `interfaces/schemas/`?

These three all describe "shapes of data," but for different audiences:
- `domain/entities/` — the internal, true business representation.
- `application/dto/` — the shape a use case needs as input/output.
- `interfaces/schemas/` — the shape exposed over the public API/CLI.

Keeping them distinct means the public API's JSON shape (which outside
clients depend on and is hard to change) is never accidentally the same
object as the internal database model (which needs to change freely as the
business evolves). This is a few extra small classes in exchange for
being able to change internals without breaking a public API contract.

## 6. Why is `ports/` inside `application/` rather than inside `domain/`?

Ports describe things the *use cases* need from the outside world (e.g.
"send an email", "call the AI provider") — they belong to the layer that
needs them. The `domain/` layer stays even purer: it doesn't need
verification vendors or AI providers to define what a "Lead" is.

## 7. What exists right now vs. what's still a placeholder?

Working code, as of the Import Engine task:
- `core/config.py` and `core/logging.py` — configuration/logging plumbing.
- `infrastructure/database/base.py` and `session.py` — DB connection
  plumbing, no tables defined yet.
- `interfaces/api/main.py` — a FastAPI app with a single `/health` endpoint.
- **The Import Engine** — `application/ports/source_reader_port.py`,
  `application/dto/models.py`, `application/use_cases/import_dataset.py`,
  `domain/exceptions/import_exceptions.py`, and
  `infrastructure/importers/excel/*` — reads `.xlsx` files into plain,
  unmodified `RawRecord`s. See
  `infrastructure/importers/README.md` for the full design. This is the
  first *complete, working* vertical slice through all four layers.
- `tests/integration/test_health.py` and `tests/unit/importer/*` — tests
  proving the above actually runs.

Specified but not yet implemented:
- **The Cleaning Engine** — its architecture (pipeline stages, ports,
  configuration strategy) has been designed and approved, and every
  individual cleaning rule has a permanent, versioned specification in
  [`docs/CLEANING_RULES.md`](CLEANING_RULES.md) (Rule IDs `CLN-001`–`CLN-068`).
  No code exists for it yet — implementation is a distinct future task, and
  each rule's entry is authoritative over whatever code eventually
  implements it, not the other way around.

Everything else (`domain/entities`, `infrastructure/external_services/*`,
cleaning/verification/AI-generation use cases, etc.) is still an empty,
correctly-placed folder with a docstring explaining its future purpose —
the Import Engine only reads and structures data; it does not interpret,
clean, or act on it.
