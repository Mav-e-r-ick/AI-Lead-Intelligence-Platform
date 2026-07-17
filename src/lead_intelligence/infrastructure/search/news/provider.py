"""NewsProvider: one of the five federated Search Layer providers.
Searches trusted business-news outlets (Reuters, Bloomberg, Yahoo
Finance, BusinessWire, PRNewswire, GlobeNewswire — see `settings.py`'s
`TRUSTED_NEWS_DOMAINS`) for executive-movement news, via the shared
`GoogleCustomSearchClient` restricted to those domains through Google's
own `site:` query operator.

WHY THIS SUPPORTS ONLY SubjectType.PERSON:
Same reasoning as every other Search Layer provider — `SearchCoordinator`
invokes it once per executive.

WHY THIS RETURNS SearchResults ONLY:
Same `SearchProviderPort` contract as every other Search Layer provider —
`SearchExtractionEngine` (unmodified) is still what fetches a found
article and extracts facts from it.
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
from lead_intelligence.infrastructure.search.google_custom_search.client import (
    GoogleCustomSearchCache,
    GoogleCustomSearchClient,
)
from lead_intelligence.infrastructure.search.news.settings import (
    NewsProviderSettings,
    site_restriction_clause,
)

PROVIDER_ID = "news_search"


class NewsProvider(SearchProviderPort):
    """Searches trusted business-news outlets for executive-movement news
    (Version 1 — see module docstring)."""

    def __init__(
        self,
        settings: NewsProviderSettings,
        http_client: httpx.Client | None = None,
        cache: GoogleCustomSearchCache | None = None,
        client: GoogleCustomSearchClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
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
        return "News Search"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.PERSON})

    def search(self, request: SearchRequest) -> SearchResponse:
        """Search trusted news outlets for `request`'s executive and
        report every result found.

        Never raises for ordinary failure modes — reported via
        `SearchResponse.status`/`error_message`.
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

        site_clause = site_restriction_clause(self._settings.trusted_domains)
        logger.info(
            "News provider starting: executive='{}', {} quer(y/ies), domains={}",
            name,
            len(queries),
            self._settings.trusted_domains,
        )

        results: list[SearchResult] = []
        queries_succeeded = 0
        queries_failed = 0

        for query in queries:
            full_query = f"{site_clause} {query}"
            items = self._client.search(full_query, num=self._settings.max_results)
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
            "News provider finished: executive='{}', {} quer(y/ies) succeeded, "
            "{} failed, {} result(s)",
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
