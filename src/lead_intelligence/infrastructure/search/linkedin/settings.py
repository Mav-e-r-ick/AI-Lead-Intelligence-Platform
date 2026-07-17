"""LinkedInSearchProviderSettings: every knob LinkedInSearchProvider
needs.

WHY THIS PROVIDER HAS NO DIRECT LINKEDIN API INTEGRATION:
LinkedIn's own official APIs require a paid partnership tier this task's
"No paid APIs" constraint rules out, and scraping linkedin.com directly
(a headless browser hitting LinkedIn's own search UI, the way
`BrowserSearchProvider` treats a search engine) would face LinkedIn's own
aggressive bot detection and Terms of Service in a way this platform has
no authorization to navigate. Instead, this provider searches Google's
*index* of LinkedIn's public profile pages — the same technique
`GoogleSearchProvider` uses for the general web, scoped to
`linkedin.com` via `GoogleCustomSearchClient.search(..., site_restrict=
"linkedin.com")`. This finds a person's current public LinkedIn profile
page (and any other indexed linkedin.com page mentioning them) without
touching LinkedIn's own servers at all — a legitimate, deterministic, no-
AI, no-paid-API technique, not a workaround of anything LinkedIn
disallows (a public search engine indexing public web pages is exactly
what robots.txt-compliant crawling is for).

WHY THIS SHARES GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID:
Same reasoning as `infrastructure/search/google/settings.py`'s own
docstring — this is the same underlying Google Custom Search API account/
credential, reused by every Search Layer provider built on
`GoogleCustomSearchClient`.

WHY QUERY TEMPLATES TARGET PROFILE-CHANGE SIGNALS, NOT JUST "FIND THE
PROFILE":
Per this task's own specification, this provider's purpose is detecting
new company / promotion / designation change / location change / profile
updates — not merely locating a LinkedIn URL. The default templates
combine name/company/title with those specific signal words so a changed
profile (freshly re-indexed by Google) is more likely to surface than an
unrelated, stale mention.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Mapping

from lead_intelligence.infrastructure.search.google.settings import (
    GOOGLE_SEARCH_API_KEY_ENV_VAR,
    GOOGLE_SEARCH_ENGINE_ID_ENV_VAR,
)

#: linkedin.com, scoped via GoogleCustomSearchClient's `site_restrict`.
LINKEDIN_DOMAIN = "linkedin.com"

#: `{name}`/`{company}`/`{title}` placeholders, filled by
#: `query_builder.build_queries` (reused from `enrichment/google_search/`,
#: same as GoogleSearchProvider). Already scoped to linkedin.com by
#: `site_restrict` — no `site:linkedin.com` needed in the query text.
DEFAULT_QUERY_TEMPLATES: tuple[str, ...] = (
    '"{name}" "{company}"',
    '"{name}" "{title}"',
    '"{name}" new position',
    '"{name}" promoted',
    '"{name}" joined "{company}"',
    '"{name}"',
)


@dataclass(frozen=True)
class LinkedInSearchProviderSettings:
    """Immutable, typed configuration for one LinkedInSearchProvider
    instance.

    Attributes:
        api_key: Google Custom Search JSON API key (see module docstring
            for why this provider is built on Google's index of LinkedIn,
            not a direct LinkedIn integration).
        search_engine_id: The Programmable Search Engine id ("cx").
        base_url: Google Custom Search API base URL.
        timeout_seconds: Per-request timeout.
        max_retries: Additional attempts after an initial failed request.
        retry_backoff_seconds: Base delay before a retry.
        max_results: Results requested per query, capped at 10.
        cache_ttl: How long one query's results are reused.
        query_templates: Which queries to generate — see module docstring.
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
        if not self.api_key.strip():
            raise ValueError(
                "LinkedInSearchProviderSettings.api_key must not be blank. Set "
                f"the {GOOGLE_SEARCH_API_KEY_ENV_VAR} environment variable."
            )
        if not self.search_engine_id.strip():
            raise ValueError(
                "LinkedInSearchProviderSettings.search_engine_id must not be "
                f"blank. Set the {GOOGLE_SEARCH_ENGINE_ID_ENV_VAR} environment "
                "variable."
            )
        if not self.base_url.strip():
            raise ValueError(
                "LinkedInSearchProviderSettings.base_url must not be blank."
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                "LinkedInSearchProviderSettings.timeout_seconds must be > 0, "
                f"got {self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "LinkedInSearchProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "LinkedInSearchProviderSettings.retry_backoff_seconds must be "
                f">= 0, got {self.retry_backoff_seconds}."
            )
        if not (1 <= self.max_results <= 10):
            raise ValueError(
                "LinkedInSearchProviderSettings.max_results must be within "
                f"[1, 10], got {self.max_results}."
            )
        if self.cache_ttl < timedelta(0):
            raise ValueError(
                "LinkedInSearchProviderSettings.cache_ttl must not be "
                f"negative, got {self.cache_ttl}."
            )
        if not self.query_templates:
            raise ValueError(
                "LinkedInSearchProviderSettings.query_templates must not be empty."
            )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **overrides: object
    ) -> "LinkedInSearchProviderSettings":
        source = env if env is not None else os.environ
        api_key = source.get(GOOGLE_SEARCH_API_KEY_ENV_VAR, "")
        search_engine_id = source.get(GOOGLE_SEARCH_ENGINE_ID_ENV_VAR, "")
        return cls(
            api_key=api_key, search_engine_id=search_engine_id, **overrides  # type: ignore[arg-type]
        )
