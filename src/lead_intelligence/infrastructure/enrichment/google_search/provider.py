"""GoogleSearchProvider: searches publicly available web information about
one executive, gathering evidence of career changes, promotions, company
moves, resignations, awards, interviews, and leadership announcements.

WHY THIS SUPPORTS ONLY SubjectType.PERSON:
This provider answers "what does the public web say about this specific
executive?" — a fact about one already-identified person, not about a
company as a whole (contrast with CompanyWebsiteProvider, which supports
only SubjectType.COMPANY). `ProviderRegistry.providers_supporting` will
never route a Company enrichment request to it.

WHY EVERY RESULT BECOMES ONE `web_mention` ObservationCandidate, NEVER A
STRUCTURED FIELD:
Unlike CompanyWebsiteProvider (which extracts specific fields — name,
title, email — from a leadership page), a search result is raw, unparsed
evidence: "this URL exists and mentions this executive in this context."
This provider deliberately does not decide what a result *means* (a
promotion? a resignation? unrelated noise?) — that interpretation is
explicitly out of scope (no AI summarization, no change detection). Every
result is reported as one `web_mention` observation, carrying the title as
its value and the snippet/source domain/publication date/originating
query as opaque `raw_context`, so a future stage has everything needed to
interpret it without this provider guessing on its behalf.

WHY known_attributes[fc.FIRST_NAME]/[fc.LAST_NAME]/[fc.COMPANY_NAME]/[fc.TITLE],
NOT A NEW VOCABULARY:
EnrichmentRequest.known_attributes is "canonical field name -> value," and
`field_contract.py` (application/cleaning/) is this platform's one
established canonical vocabulary today. Reusing these fields avoids
inventing a second, parallel vocabulary for the same concepts.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

import httpx
from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ObservationCandidate,
    SubjectType,
)
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.infrastructure.enrichment.google_search.cache import (
    InMemorySearchResultCache,
    SearchResultCache,
)
from lead_intelligence.infrastructure.enrichment.google_search.extraction import (
    SearchResult,
    parse_search_response,
)
from lead_intelligence.infrastructure.enrichment.google_search.query_builder import (
    build_queries,
)
from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    GoogleSearchProviderSettings,
)

PROVIDER_ID = "google_search"

#: The one attribute every result is reported under — see module docstring
#: for why this is deliberately not a structured, field-contract attribute.
_OBSERVED_ATTRIBUTE = "web_mention"


class GoogleSearchProvider(EnrichmentProviderPort):
    """Gathers public web evidence about one executive via the Google
    Custom Search JSON API (Version 1 — see module docstring and
    README.md)."""

    def __init__(
        self,
        settings: GoogleSearchProviderSettings,
        http_client: httpx.Client | None = None,
        cache: SearchResultCache | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            settings: This provider's own configuration (API key, search
                engine id, timeout, retry policy, max results, cache TTL,
                query templates). Typically built via
                `GoogleSearchProviderSettings.from_env()`.
            http_client: The httpx.Client used for every request. Defaults
                to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            cache: Where each query's results are reused from. Defaults to
                a fresh InMemorySearchResultCache sized from
                `settings.cache_ttl`.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps and cache
                behavior.
            sleep_fn: Called between retry attempts. Override with a no-op
                in tests to avoid real delays.
        """

        settings.validate()
        self._settings = settings
        self._http_client = http_client or httpx.Client()
        self._cache = cache or InMemorySearchResultCache(ttl=settings.cache_ttl)
        self._clock = clock
        self._sleep = sleep_fn

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Google Search"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.PERSON})

    def fetch(self, request: EnrichmentRequest) -> EnrichmentResponse:
        """Search the public web for `request`'s executive and report
        every result found as a `web_mention` ObservationCandidate.

        Never raises for ordinary failure modes (no name available, every
        query failing) — those are reported via
        `EnrichmentResponse.status`/`error_message`, per
        EnrichmentProviderPort's contract.
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
            "Google Search provider starting: executive='{}', {} quer(y/ies)",
            name,
            len(queries),
        )

        observations: list[ObservationCandidate] = []
        queries_succeeded = 0
        queries_failed = 0
        observed_at = self._clock()

        for query in queries:
            results = self._search(query)
            if results is None:
                queries_failed += 1
                continue
            queries_succeeded += 1
            observations.extend(
                self._to_observations(request.subject_id, query, results, observed_at)
            )

        if queries_succeeded == 0:
            status = EnrichmentStatus.FAILURE
        elif queries_failed > 0:
            status = EnrichmentStatus.PARTIAL
        else:
            status = EnrichmentStatus.SUCCESS

        logger.info(
            "Google Search provider finished: executive='{}', {} quer(y/ies) "
            "succeeded, {} failed, {} observation(s)",
            name,
            queries_succeeded,
            queries_failed,
            len(observations),
        )
        return self._response(request, status, tuple(observations))

    def _to_observations(
        self,
        subject_id: str,
        query: str,
        results: tuple[SearchResult, ...],
        observed_at: datetime,
    ) -> list[ObservationCandidate]:
        observations = []
        for result in results:
            raw_context: dict[str, str] = {
                "query": query,
                "snippet": result.snippet,
                "source_domain": result.source_domain,
            }
            if result.published_at:
                raw_context["published_at"] = result.published_at

            observations.append(
                ObservationCandidate(
                    subject_id=subject_id,
                    attribute=_OBSERVED_ATTRIBUTE,
                    value=result.title,
                    provider_id=self.provider_id,
                    observed_at=observed_at,
                    source_url=result.url,
                    raw_context=raw_context,
                )
            )
        return observations

    def _response(
        self,
        request: EnrichmentRequest,
        status: EnrichmentStatus,
        observations: tuple[ObservationCandidate, ...],
        error_message: str | None = None,
    ) -> EnrichmentResponse:
        return EnrichmentResponse(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=status,
            observations=observations,
            error_message=error_message,
            started_at=request.requested_at,
            completed_at=self._clock(),
        )

    def _search(self, query: str) -> tuple[SearchResult, ...] | None:
        """Fetch `query`'s results, via cache first, then retrying
        transient failures (timeouts, connection errors, 5xx responses,
        HTTP 429) up to `settings.max_retries` additional times. 4xx
        responses are never retried. Returns None if results could not be
        obtained.
        """

        cached = self._cache.get(query, self._clock())
        if cached is not None:
            logger.debug("Cache hit for query '{}'", query)
            return cached

        params: dict[str, str | int] = {
            "key": self._settings.api_key,
            "cx": self._settings.search_engine_id,
            "q": query,
            "num": self._settings.max_results,
        }
        attempts = self._settings.max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                response = self._http_client.get(
                    self._settings.base_url,
                    params=params,
                    timeout=self._settings.timeout_seconds,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Request error searching '{}' (attempt {}/{}): {}",
                    query,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code == 429:
                logger.warning(
                    "Rate limited searching '{}' (attempt {}/{})",
                    query,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 500:
                logger.warning(
                    "Server error {} searching '{}' (attempt {}/{})",
                    response.status_code,
                    query,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 400:
                logger.info(
                    "Client error {} searching '{}'; not retrying.",
                    response.status_code,
                    query,
                )
                return None

            try:
                payload = response.json()
            except ValueError:
                logger.error("Non-JSON response searching '{}'", query)
                return None

            results = parse_search_response(payload)
            self._cache.set(query, results, self._clock())
            return results

        return None


def _executive_name(request: EnrichmentRequest) -> str:
    first_name = (request.known_attributes.get(fc.FIRST_NAME) or "").strip()
    last_name = (request.known_attributes.get(fc.LAST_NAME) or "").strip()
    return " ".join(part for part in (first_name, last_name) if part)
