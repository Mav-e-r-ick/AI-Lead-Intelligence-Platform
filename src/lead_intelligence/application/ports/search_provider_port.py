"""SearchProviderPort: the one contract every search provider must
implement, whatever it actually is (a search API client, a headless
browser driving a search engine's own results page, or — in tests — an
in-memory fake).

WHY THIS INTERFACE MIRRORS EnrichmentProviderPort EXACTLY:
Per the approved Search Layer RFC, search providers are a sibling
provider family to enrichment providers — same shape (an id, a display
name, which subject types it applies to, one method that turns a request
into a response), different responsibility (results, never observations).
Keeping the two ports structurally identical is what let the existing
Enrichment Provider Framework's registry/coordinator/health-tracking
pattern be reused for Search almost verbatim, rather than inventing a
second, different coordination style.

WHY THIS INTERFACE HAS NO DEFAULT METHODS OR HELPER LOGIC:
Same reasoning as EnrichmentProviderPort: any shared behavior a real
provider might want (HTTP retries, browser automation, caching) belongs in
that concrete provider's own infrastructure code, never here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lead_intelligence.application.dto.search_models import (
    SearchRequest,
    SearchResponse,
    SubjectType,
)


class SearchProviderPort(ABC):
    """One external (or future-external) source of search results."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """A short, stable, unique identifier (e.g. "google_search",
        "browser_search", "bing"). Used as the key everywhere a provider
        is referenced: SearchProviderRegistry, SearchProfile's per-provider
        configuration, and ProviderHealthTracker."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """A human-readable name, for logs and future admin UIs."""

    @property
    @abstractmethod
    def supported_subject_types(self) -> frozenset[SubjectType]:
        """Which Subject type(s) this provider can be asked about.
        SearchProviderRegistry uses this to exclude a provider from
        consideration entirely for the wrong subject_type, before
        enabled/health checks ever run."""

    @abstractmethod
    def search(self, request: SearchRequest) -> SearchResponse:
        """Attempt to fulfill `request` and return every result found.

        Implementations should not raise for ordinary "found nothing" or
        "source unavailable" cases — report those via
        `SearchResponse.status`/`error_message` instead, so the
        coordinator's per-provider metrics and health tracking stay
        accurate. An actual raised exception is still handled safely (the
        coordinator treats it as a failure and keeps going), but it should
        be reserved for genuinely unexpected programming errors, not
        expected real-world outcomes like "no results found."

        Must never extract observations, interpret a result's meaning, or
        fetch a result's destination page — a search provider's job ends
        at reporting title/url/snippet/source/rank for whatever it found.
        """
