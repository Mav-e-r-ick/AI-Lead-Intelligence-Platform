# Interfaces Layer (a.k.a. Presentation / Adapters)

## What "interfaces" means here
This is how the **outside world talks to our application** — a REST API, a
command-line tool, or (later) a web dashboard. In Clean Architecture terms
this is the outermost ring: the "Interface Adapters" layer.

## The rule for this folder
Code here translates between the outside world's format (HTTP JSON
requests, CLI arguments) and the application layer's use cases. It is
allowed to depend on `application/` (to call use cases) and `core/` (for
settings/logging), but it must contain **no business rules** itself — an
API route's job is only "receive a request, call a use case, return a
response," never "decide whether an email is valid."

## Sub-folders

| Folder | Purpose |
|---|---|
| `api/` | The FastAPI web application: `main.py` creates the app object; `routes/` will hold one file per group of endpoints (e.g. `leads.py`, `outreach.py`) once real endpoints are built. |
| `cli/` | Command-line entry points for scripts/automation (e.g. "run the Excel import from the terminal"), for later use. |
| `schemas/` | Pydantic models describing the exact shape of API request/response bodies. These are intentionally separate from `application/dto/` and `domain/entities/` — the outside-facing JSON shape is allowed to change (e.g. renaming a public field) without forcing a change to internal business objects. |

## Current status
Only one real thing exists right now: a `/health` endpoint in `api/main.py`,
included purely to prove the layers wire together and the app can actually
start. It contains no business logic. Everything else is an empty,
correctly-placed folder waiting for future work. See `../README.md` (project
root) and `docs/ARCHITECTURE.md` for the full picture.
