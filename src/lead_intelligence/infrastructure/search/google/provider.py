"""GoogleSearchProvider (Search Layer): discovers executive changes
across the general web via the Google Custom Search JSON API — one of the
five federated providers in this Search Layer redesign (see
`application/search/README.md`'s "Federated Search" section).

WHY THIS SUPPORTS ONLY SubjectType.PERSON:
Same reasoning as every other Search Layer provider: `SearchCoordinator`
invokes it once per executive, and every query it builds is about that one
person.

WHY THIS RETURNS SearchResults ONLY, NEVER ObservationCandidates:
Per `SearchProviderPort`'s contract (unchanged by this redesign): a search
provider's job ends at reporting title/url/snippet/source/rank/confidence
for what it found. The existing, unmodified `SearchExtractionEngine` is
still what fetches each result's destination page and extracts facts —
see `infrastructure/search/extraction/README.md`.

WHY QUERY BUILDING REUSES `enrichment.google_search.query_builder.build_queries`:
That function is pure `{name}`/`{company}`/`{title}` placeholder
substitution with zero Google-specific logic — `BrowserSearchProvider`
already reused it unmodified for the same reason (see that provider's own
README). Reusing it here means one query-templating implementation for
every provider in this codebase that builds Google-style queries, not a
second copy.

WHY provider_id IS "google_web_search", NOT "google_search":
`infrastructure/enrichment/google_search/provider.py` already registers
`provider_id = "google_search"` with a *different* coordinator
(EnrichmentCoordinator) — reusing the same id here would be harmless
mechanically (the two use independent registries/health-trackers, see
`run_pipeline.py`'s `_build_enrichment_providers`/`_build_search_collaborators`
building separate `ProviderHealthTracker` instances), but would make every
downstream trace (`ExecutiveIntelligenceReport.providers_executed`, logs)
genuinely ambiguous about which of the two ran. A distinct id costs
nothing and removes that ambiguity entirely.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

import httpx
from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SubjectType,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.application.search.confidence import score_confidence
from lead_intelligence.infrastructure.enrichment.google_search.query_builder import (
    build_queries,
)
from lead_intelligence.infrastructure.search.google.settings import (
    GoogleSearchProviderSettings,
)
from lead_intelligence.infrastructure.search.google_custom_search.client import (
    GoogleCustomSearchCache,
    GoogleCustomSearchClient,
)

PROVIDER_ID = "google_web_search"


class GoogleSearchProvider(SearchProviderPort):
    """Discovers executive changes across the general web (Version 1 —
    see module docstring)."""

    def __init__(
        self,
        settings: GoogleSearchProviderSettings,
        http_client: httpx.Client | None = None,
        cache: GoogleCustomSearchCache | None = None,
        client: GoogleCustomSearchClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            settings: This provider's own configuration.
            http_client: The httpx.Client used for every request. Ignored
                if `client` is supplied directly.
            cache: Where each query's results are reused from. Ignored if
                `client` is supplied directly.
            client: The GoogleCustomSearchClient to use. Defaults to one
                built from `settings`/`http_client`/`cache`; tests may
                inject a fully custom client instead.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
            sleep_fn: Called between retry attempts. Ignored if `client`
                is supplied directly.
        """

        settings.validate()
        self._settings = settings
        self._client = client or GoogleCustomSearchClient(
            api_key=settings.api_key,
            search_engine_id=settings.search_engine_id,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
            retry_backoff_seconds=settings.retry_backoff_seconds,
            max_results=settings.max_results,
            http_client=http_client,
            cache=cache,
            cache_ttl=settings.cache_ttl,
            clock=clock,
            sleep_fn=sleep_fn,
        )
        self._clock = clock

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Google Search"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.PERSON})

    def search(self, request: SearchRequest) -> SearchResponse:
        """Search the general web for `request`'s executive and report
        every result found, across every query this executive's known
        attributes let `build_queries` construct.

        Never raises for ordinary failure modes (no name available, no
        queries could be built, every query failing) — those are reported
        via `SearchResponse.status`/`error_message`.
        """

        name = _executive_name(request)
        company = request.known_attributes.get(fc.COMPANY_NAME)
        title = request.known_attributes.get(fc.TITLE)

        if not name:
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=(
                    "No executive name provided in known_attributes "
                    f"['{fc.FIRST_NAME}'/'{fc.LAST_NAME}']."
                ),
            )

        queries = build_queries(name, company, title, self._settings.query_templates)
        if not queries:
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message="No search queries could be built for this executive.",
            )

        logger.info(
            "Google Search (Search Layer) provider starting: executive='{}', "
            "{} quer(y/ies)",
            name,
            len(queries),
        )

        results: list[SearchResult] = []
        queries_succeeded = 0
        queries_failed = 0

        for query in queries:
            items = self._client.search(query, num=self._settings.max_results)
            if items is None:
                queries_failed += 1
                continue
            queries_succeeded += 1
            for item in items:
                results.append(
                    SearchResult(
                        title=item.title,
                        url=item.url,
                        snippet=item.snippet,
                        source=self.provider_id,
                        rank=len(results) + 1,
                        confidence=score_confidence(item.url, self.provider_id),
                    )
                )

        if queries_succeeded == 0:
            status = EnrichmentStatus.FAILURE
        elif queries_failed > 0:
            status = EnrichmentStatus.PARTIAL
        else:
            status = EnrichmentStatus.SUCCESS

        logger.info(
            "Google Search (Search Layer) provider finished: executive='{}', "
            "{} quer(y/ies) succeeded, {} failed, {} result(s)",
            name,
            queries_succeeded,
            queries_failed,
            len(results),
        )
        return self._response(request, status, tuple(results))

    def _response(
        self,
        request: SearchRequest,
        status: EnrichmentStatus,
        results: tuple[SearchResult, ...],
        error_message: str | None = None,
    ) -> SearchResponse:
        return SearchResponse(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=status,
            results=results,
            error_message=error_message,
            started_at=request.requested_at,
            completed_at=self._clock(),
        )


def _executive_name(request: SearchRequest) -> str:
    first_name = (request.known_attributes.get(fc.FIRST_NAME) or "").strip()
    last_name = (request.known_attributes.get(fc.LAST_NAME) or "").strip()
    return " ".join(part for part in (first_name, last_name) if part)
