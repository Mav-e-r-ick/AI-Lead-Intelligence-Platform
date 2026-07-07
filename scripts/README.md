# Scripts

## Purpose
A home for small, standalone operational scripts that support development
but aren't part of the application itself — e.g. a future `seed_db.py` to
populate a local database with sample data, or a `check_env.py` that
verifies all required `.env` variables are set.

## Why this is separate from `src/`
Application code in `src/lead_intelligence/` is organized by Clean
Architecture layer and is meant to be imported as a package. Scripts here
are meant to be *run directly* (`python scripts/some_script.py`) and are
one-off tools, not part of the importable application.

## Current status
Empty on purpose — no scripts have been needed yet. This is foundation
only.
