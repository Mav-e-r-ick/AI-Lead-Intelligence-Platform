"""GoogleSearchProviderSettings: every knob this one provider needs.

WHY THIS ISN'T PART OF THE FRAMEWORK'S ProviderConfiguration:
ProviderConfiguration (application/enrichment/config.py) is deliberately
generic — enabled/priority/refresh policy/a timeout the framework itself
doesn't enforce — plus a fully opaque `parameters` mapping the framework
never interprets. Real per-provider behavior (the API key, the search
engine id, retry counts, backoff, which query templates to run, how many
results per query) is exactly what "no provider-specific business logic
in the framework" pushes down into the provider itself. This dataclass is
where that lives, fully typed rather than pulled out of `parameters` at
call time.

WHY QUERY TEMPLATES ARE PART OF SETTINGS, NOT HARDCODED IN THE PROVIDER:
The task explicitly asks for "configurable search queries." Templates are
plain strings containing `{name}`, `{company}`, and/or `{title}`
placeholders — `query_builder.py` fills in whichever placeholders a
template uses and skips a template entirely if a placeholder it needs
(e.g. `{title}`) has no value for this executive. A caller can add,
remove, or reorder templates (e.g. add `'"{name}" fired'`) via a custom
GoogleSearchProviderSettings, without touching provider code.

WHY from_env() EXISTS, SEPARATE FROM THE DATACLASS ITSELF:
Mirrors NeverBounceSettings.from_env() (infrastructure/external_services/
email_verification/neverbounce/settings.py): reading `os.environ` directly
inside the dataclass would make every test either mutate real process
environment variables or monkeypatch `os.environ`. Instead, `from_env()`
takes an injectable `env` mapping (defaulting to `os.environ`), so tests
can pass a plain dict and production code can call
`GoogleSearchProviderSettings.from_env()` with no arguments — only the
real `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` environment
variables are needed once they exist.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Mapping

#: The two environment variables this provider requires: a Google Custom
#: Search JSON API key, and the Programmable Search Engine id ("cx") that
#: scopes which sites/pages the search covers.
GOOGLE_SEARCH_API_KEY_ENV_VAR = "GOOGLE_SEARCH_API_KEY"
GOOGLE_SEARCH_ENGINE_ID_ENV_VAR = "GOOGLE_SEARCH_ENGINE_ID"

#: Default query templates. `{name}` is always required; `{company}` and
#: `{title}` are optional — query_builder.py skips a template if a
#: placeholder it references has no value for this executive.
DEFAULT_QUERY_TEMPLATES: tuple[str, ...] = (
    '"{name}" "{company}"',
    '"{name}" promotion',
    '"{name}" appointed',
    '"{name}" joins',
    '"{name}" resigned',
    '"{name}" leadership',
)


@dataclass(frozen=True)
class GoogleSearchProviderSettings:
    """Immutable, typed configuration for one GoogleSearchProvider instance.

    Attributes:
        api_key: Google Custom Search JSON API key, sent as the `key`
            query parameter on every request. Read from the
            `GOOGLE_SEARCH_API_KEY` environment variable via `from_env()`.
        search_engine_id: The Programmable Search Engine id ("cx") to
            search under. Read from `GOOGLE_SEARCH_ENGINE_ID`.
        base_url: Google Custom Search API base URL. Overridable for
            testing against a mock server.
        timeout_seconds: Per-request timeout, applied to every search call.
        max_retries: How many additional attempts are made after an
            initial failed request (timeout, connection error, or 5xx
            response) before giving up on that one query. 4xx responses
            are never retried.
        retry_backoff_seconds: Base delay before a retry; multiplied by
            the attempt number for simple linear backoff.
        max_results: Maximum number of results requested per query (the
            API's own `num` parameter), capped at Google's own limit of 10
            per request.
        cache_ttl: How long a query's results are reused from cache before
            being considered stale and re-searched.
        query_templates: Which queries to generate per executive — see
            module docstring for the placeholder substitution rules.
    """

    api_key: str
    search_engine_id: str
    base_url: str = "https://www.googleapis.com/customsearch/v1"
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    max_results: int = 5
    cache_ttl: timedelta = timedelta(hours=6)
    query_templates: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_QUERY_TEMPLATES
    )

    def validate(self) -> None:
        """Raise ValueError if this settings object is self-contradictory.

        Called once, at provider construction time — a misconfigured
        provider should fail immediately, not on its first request.
        """

        if not self.api_key.strip():
            raise ValueError(
                "GoogleSearchProviderSettings.api_key must not be blank. Set "
                f"the {GOOGLE_SEARCH_API_KEY_ENV_VAR} environment variable."
            )
        if not self.search_engine_id.strip():
            raise ValueError(
                "GoogleSearchProviderSettings.search_engine_id must not be "
                f"blank. Set the {GOOGLE_SEARCH_ENGINE_ID_ENV_VAR} environment "
                "variable."
            )
        if not self.base_url.strip():
            raise ValueError("GoogleSearchProviderSettings.base_url must not be blank.")
        if self.timeout_seconds <= 0:
            raise ValueError(
                "GoogleSearchProviderSettings.timeout_seconds must be > 0, got "
                f"{self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "GoogleSearchProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "GoogleSearchProviderSettings.retry_backoff_seconds must be "
                f">= 0, got {self.retry_backoff_seconds}."
            )
        if not (1 <= self.max_results <= 10):
            raise ValueError(
                "GoogleSearchProviderSettings.max_results must be within "
                f"[1, 10] (the Google Custom Search API's own per-request "
                f"limit), got {self.max_results}."
            )
        if self.cache_ttl < timedelta(0):
            raise ValueError(
                "GoogleSearchProviderSettings.cache_ttl must not be negative, "
                f"got {self.cache_ttl}."
            )
        if not self.query_templates:
            raise ValueError(
                "GoogleSearchProviderSettings.query_templates must not be empty."
            )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **overrides: object
    ) -> GoogleSearchProviderSettings:
        """Build settings from environment variables.

        Args:
            env: Mapping to read `GOOGLE_SEARCH_API_KEY`/
                `GOOGLE_SEARCH_ENGINE_ID` from. Defaults to the real
                process environment (`os.environ`); pass a plain dict in
                tests.
            **overrides: Any other `GoogleSearchProviderSettings` field
                (e.g. `max_results=3`), for callers who want everything
                else from the environment but one field overridden.

        Returns:
            A GoogleSearchProviderSettings with `api_key`/
            `search_engine_id` read from the environment. `validate()` is
            not called here — call it once the provider is constructed,
            same as every other settings object in this codebase.
        """

        source = env if env is not None else os.environ
        api_key = source.get(GOOGLE_SEARCH_API_KEY_ENV_VAR, "")
        search_engine_id = source.get(GOOGLE_SEARCH_ENGINE_ID_ENV_VAR, "")
        return cls(
            api_key=api_key, search_engine_id=search_engine_id, **overrides  # type: ignore[arg-type]
        )
