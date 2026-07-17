"""NewsProviderSettings: every knob NewsProvider needs.

WHY THIS SEARCHES A `(site:a OR site:b OR ...)` CLAUSE INSTEAD OF USING
`GoogleCustomSearchClient`'s `site_restrict` PARAMETER:
Google's Custom Search API's `siteSearch` parameter only accepts one
domain per request (see `google_custom_search/client.py`'s own module
docstring) — `LinkedInSearchProvider` can use it because it only ever
targets one domain. This provider targets several trusted news domains at
once, so the restriction is instead built directly into the query text
via Google's own `site:` search operator, joined with `OR` — ordinary
query syntax Google's API already understands, not a special parameter.

WHY THESE SPECIFIC DOMAINS:
The exact outlets this task names: Reuters, Bloomberg, Yahoo Finance,
BusinessWire, PRNewswire, GlobeNewswire — see `TRUSTED_NEWS_DOMAINS`.
`application/search/confidence.py` assigns these the same domain-based
trust tiers regardless of which provider happened to find a given
article, so this list and that module's domain tables are deliberately
kept in exact correspondence (see that module's own docstring).

WHY THIS SHARES GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID:
Same Google Custom Search account/credential as every other Search Layer
provider built on `GoogleCustomSearchClient` — see
`infrastructure/search/google/settings.py`'s module docstring.
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

#: The trusted business-news domains this provider restricts every query
#: to. Kept in exact correspondence with `application/search/confidence.py`'s
#: `_TIER_1_NEWS_DOMAINS`/`_TIER_2_NEWS_DOMAINS` — see that module's own
#: docstring for the confidence each tier is assigned.
TRUSTED_NEWS_DOMAINS: tuple[str, ...] = (
    "reuters.com",
    "bloomberg.com",
    "finance.yahoo.com",
    "businesswire.com",
    "prnewswire.com",
    "globenewswire.com",
)


def site_restriction_clause(domains: tuple[str, ...]) -> str:
    """`"(site:a.com OR site:b.com OR ...)"` — Google's own `site:`
    operator, joined with `OR`, restricting a query to `domains`. Applied
    by `provider.py` at search time (from `settings.trusted_domains`), not
    baked into `DEFAULT_QUERY_TEMPLATES` — so a caller who overrides
    `trusted_domains` gets a query actually restricted to their own list,
    not the default one silently still baked into the template text."""

    return "(" + " OR ".join(f"site:{domain}" for domain in domains) + ")"


#: `{name}`/`{company}`/`{title}` placeholders, filled by
#: `query_builder.build_queries` (reused from `enrichment/google_search/`).
#: The trusted-domain restriction is prepended separately by `provider.py`
#: — see `site_restriction_clause`'s own docstring for why.
DEFAULT_QUERY_TEMPLATES: tuple[str, ...] = (
    '"{name}" "{company}"',
    '"{name}" appointed',
    '"{name}" named',
    '"{name}" promoted',
    '"{name}" resigns',
    '"{name}" steps down',
    '"{name}" board',
)


@dataclass(frozen=True)
class NewsProviderSettings:
    """Immutable, typed configuration for one NewsProvider instance.

    Attributes:
        api_key: Google Custom Search JSON API key.
        search_engine_id: The Programmable Search Engine id ("cx").
        base_url: Google Custom Search API base URL.
        timeout_seconds: Per-request timeout.
        max_retries: Additional attempts after an initial failed request.
        retry_backoff_seconds: Base delay before a retry.
        max_results: Results requested per query, capped at 10.
        cache_ttl: How long one query's results are reused.
        query_templates: Which queries to generate — see module docstring.
        trusted_domains: The domains every query is restricted to. Exposed
            so a caller can extend/narrow the list without forking this
            settings module; changing it does not automatically update
            `application/search/confidence.py`'s own domain tables, which
            are the single source of truth for *trust level*, not
            membership.
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
    trusted_domains: tuple[str, ...] = field(
        default_factory=lambda: TRUSTED_NEWS_DOMAINS
    )

    def validate(self) -> None:
        if not self.api_key.strip():
            raise ValueError(
                "NewsProviderSettings.api_key must not be blank. Set the "
                f"{GOOGLE_SEARCH_API_KEY_ENV_VAR} environment variable."
            )
        if not self.search_engine_id.strip():
            raise ValueError(
                "NewsProviderSettings.search_engine_id must not be blank. Set "
                f"the {GOOGLE_SEARCH_ENGINE_ID_ENV_VAR} environment variable."
            )
        if not self.base_url.strip():
            raise ValueError("NewsProviderSettings.base_url must not be blank.")
        if self.timeout_seconds <= 0:
            raise ValueError(
                "NewsProviderSettings.timeout_seconds must be > 0, got "
                f"{self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "NewsProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "NewsProviderSettings.retry_backoff_seconds must be >= 0, "
                f"got {self.retry_backoff_seconds}."
            )
        if not (1 <= self.max_results <= 10):
            raise ValueError(
                "NewsProviderSettings.max_results must be within [1, 10], "
                f"got {self.max_results}."
            )
        if self.cache_ttl < timedelta(0):
            raise ValueError(
                "NewsProviderSettings.cache_ttl must not be negative, got "
                f"{self.cache_ttl}."
            )
        if not self.query_templates:
            raise ValueError("NewsProviderSettings.query_templates must not be empty.")
        if not self.trusted_domains:
            raise ValueError("NewsProviderSettings.trusted_domains must not be empty.")

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **overrides: object
    ) -> "NewsProviderSettings":
        source = env if env is not None else os.environ
        api_key = source.get(GOOGLE_SEARCH_API_KEY_ENV_VAR, "")
        search_engine_id = source.get(GOOGLE_SEARCH_ENGINE_ID_ENV_VAR, "")
        return cls(
            api_key=api_key, search_engine_id=search_engine_id, **overrides  # type: ignore[arg-type]
        )
