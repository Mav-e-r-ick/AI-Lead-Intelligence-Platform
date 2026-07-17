"""GoogleSearchProviderSettings: every knob the Search Layer's
GoogleSearchProvider needs.

WHY THIS READS THE SAME GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID
ENVIRONMENT VARIABLES AS `enrichment/google_search/settings.py`:
Both providers call the exact same Google Custom Search JSON API using
the exact same underlying account/credential — there is only one Google
Custom Search API key an operator provisions, and `LinkedInSearchProvider`/
`NewsProvider` (also built on `GoogleCustomSearchClient`) share it too.
Minting a second, differently-named environment variable for the same
literal credential would be pure duplication with no configuration
benefit — an operator who has already set up Google Custom Search once
gets every Search Layer Google-backed provider working, not just one.

WHY QUERY TEMPLATES NOW EXPLICITLY TARGET EXECUTIVE INFLECTION EVENTS:
Per this redesign's objective (continuous monitoring for promotions, new
jobs, company changes, board appointments, retirements, resignations,
etc.), the default templates combine name/company/title with the
inflection-signal keywords this task specifies (promotion, joined,
appointed, named, board, CEO, VP, director) — a materially different,
broader set than the original `enrichment/google_search/settings.py`
defaults (which were general "gather any public evidence" queries, not
inflection-focused). Reusing that settings module's *defaults* here would
under-serve this provider's actual purpose.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Mapping

GOOGLE_SEARCH_API_KEY_ENV_VAR = "GOOGLE_SEARCH_API_KEY"
GOOGLE_SEARCH_ENGINE_ID_ENV_VAR = "GOOGLE_SEARCH_ENGINE_ID"

#: `{name}`/`{company}`/`{title}` placeholders, filled by
#: `query_builder.build_queries` (reused unmodified from
#: `enrichment/google_search/query_builder.py` — pure string substitution
#: with zero Google-specific logic). A template referencing a placeholder
#: with no known value for this executive is skipped, not sent blank.
DEFAULT_QUERY_TEMPLATES: tuple[str, ...] = (
    '"{name}" "{company}"',
    '"{name}" "{title}"',
    '"{name}" "{company}" promotion',
    '"{name}" "{company}" promoted',
    '"{name}" "{company}" joined',
    '"{name}" "{company}" appointed',
    '"{name}" "{company}" named',
    '"{name}" "{company}" board',
    '"{name}" CEO',
    '"{name}" VP',
    '"{name}" director',
)


@dataclass(frozen=True)
class GoogleSearchProviderSettings:
    """Immutable, typed configuration for one GoogleSearchProvider
    (Search Layer) instance.

    Attributes:
        api_key: Google Custom Search JSON API key.
        search_engine_id: The Programmable Search Engine id ("cx").
        base_url: Google Custom Search API base URL. Overridable for
            testing against a mock server.
        timeout_seconds: Per-request timeout.
        max_retries: Additional attempts after an initial failed request.
        retry_backoff_seconds: Base delay before a retry; multiplied by
            the attempt number.
        max_results: Results requested per query, capped at Google's own
            10-per-request limit.
        cache_ttl: How long one query's results are reused before being
            considered stale.
        query_templates: Which queries to generate per executive — see
            module docstring.
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
        Called once, at provider construction time."""

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
                f"[1, 10], got {self.max_results}."
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
    ) -> "GoogleSearchProviderSettings":
        """Build settings from environment variables (see module
        docstring for why this reads the same two variables as
        `enrichment/google_search/settings.py`).

        Args:
            env: Mapping to read from. Defaults to `os.environ`; pass a
                plain dict in tests.
            **overrides: Any other field (e.g. `max_results=3`).
        """

        source = env if env is not None else os.environ
        api_key = source.get(GOOGLE_SEARCH_API_KEY_ENV_VAR, "")
        search_engine_id = source.get(GOOGLE_SEARCH_ENGINE_ID_ENV_VAR, "")
        return cls(
            api_key=api_key, search_engine_id=search_engine_id, **overrides  # type: ignore[arg-type]
        )
