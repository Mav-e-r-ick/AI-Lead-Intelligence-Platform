"""FastAPI application entry point.

WHY THIS FILE EXISTS (AND WHY IT HAS A /health ENDPOINT):
This is the only "runnable" piece of code in the whole foundation. It
exists to prove that the project's layers are wired together correctly —
that `core.config`, `core.logging`, and the package structure all import
cleanly — *before* any real feature is built on top of them.

The single `/health` endpoint below is standard practice in production
systems (used by load balancers and uptime monitors to check "is the app
alive?") and contains no business logic — it does not touch leads,
emails, or AI providers. Every other route file (e.g. for leads or
outreach) will be added under `routes/` in a future task, and included
here with `app.include_router(...)`.

Run it locally with:
    uvicorn lead_intelligence.interfaces.api.main:app --reload
"""

from fastapi import FastAPI

from lead_intelligence.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="AI Lead Intelligence Platform",
    version="0.1.0",
    description=(
        "Foundation build. No business features are implemented yet — "
        "see the project README for the roadmap."
    ),
)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the API process is up and able to respond to requests."""

    return {"status": "ok"}
