"""SearchCoordinator: the Search Layer's single orchestration point.

Given a Subject (a Digital Twin id, or a provisional identity id from the
Identity Resolution Engine), the coordinator:
1. Determines which registered providers even apply to this subject_type.
2. Filters to providers that are enabled and healthy.
3. Executes the remaining providers in priority order — skipping any
   provider configured `fallback_only=True` once an earlier, higher-
   priority provider has already contributed a result (see
   `SearchProviderConfiguration.fallback_only`'s own docstring).
4. Collects every SearchResult from every executed provider.
5. Returns one combined SearchCoordinationResult.

WHY THIS MIRRORS application/enrichment/coordinator.py NEARLY LINE FOR
LINE:
Per the approved Search Layer RFC, Search is a sibling coordination
framework to Enrichment, not a new pattern — reusing the same, already
proven "registry + profile + health tracker" shape (down to reusing
`ProviderHealthTracker` itself, unmodified) is what "reuse the existing
Search/Enrichment architecture" means in practice. The two differences
from EnrichmentCoordinator are:
  1. No refresh-policy/staleness skip (see search/config.py's docstring —
     nothing persists search results yet, so "is this stale" has no
     answer to check against).
  2. Collects SearchResults, never ObservationCandidates — a search
     provider's contract (SearchProviderPort.search) makes it structurally
     impossible for this coordinator to receive anything else.

WHY EXECUTION IS SEQUENTIAL, NOT CONCURRENT:
Same reasoning as EnrichmentCoordinator: determinism and testability
matter more than throughput at this stage. A provider that is itself slow
(e.g. a headless browser search) should set its own timeout; this
coordinator does not add concurrency on top.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Mapping

from loguru import logger

from lead_intelligence.application.dto.enrichment_models import (
    ProviderSkip,
    SkipReason,
)
from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchCoordinationMetrics,
    SearchCoordinationResult,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SubjectType,
)
from lead_intelligence.application.enrichment.provider_health import (
    ProviderHealthTracker,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.application.search.config import SearchProfile
from lead_intelligence.application.search.provider_registry import (
    SearchProviderRegistry,
)


class SearchCoordinator:
    """Runs every applicable, enabled, healthy provider for one Subject,
    in priority order, and combines their results."""

    def __init__(
        self,
        registry: SearchProviderRegistry,
        profile: SearchProfile,
        health_tracker: ProviderHealthTracker | None = None,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure a coordinator bound to one registry and one profile.

        Args:
            registry: Every provider this coordinator may call (dependency
                injection).
            profile: The active SearchProfile.
            health_tracker: Where provider health is recorded and
                consulted. Defaults to a fresh, empty tracker; pass a
                shared one to preserve health across multiple `search()`
                calls (e.g. across subjects in the same run).
            id_factory: Generates each SearchRequest's id. Override with a
                deterministic sequence in tests.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._registry = registry
        self._profile = profile
        self._health_tracker = health_tracker or ProviderHealthTracker()
        self._id_factory = id_factory
        self._clock = clock

    def search(
        self,
        subject_type: SubjectType,
        subject_id: str,
        known_attributes: Mapping[str, str],
    ) -> SearchCoordinationResult:
        """Search for one Subject and return the combined result.

        Args:
            subject_type: Person or Company.
            subject_id: The Digital Twin id (or provisional identity id)
                being searched for. Opaque to this framework.
            known_attributes: Canonical field name -> known value, passed
                identically to every executed provider (e.g.
                {"first_name": "Ada", "last_name": "Lovelace",
                "company_name": "Acme Corp"}).

        Raises:
            InvalidSearchConfigurationError: If the profile itself is
                invalid — raised before any provider is executed.
        """

        self._profile.validate()

        started_at = self._clock()
        logger.info(
            "Search coordination starting: profile='{}', subject_type={}, "
            "subject_id={}",
            self._profile.name,
            subject_type.value,
            subject_id,
        )

        applicable = self._registry.providers_supporting(subject_type)
        ordered = self._order_by_priority(applicable)

        provider_responses: list[SearchResponse] = []
        results: list[SearchResult] = []
        skipped: list[ProviderSkip] = []
        succeeded = 0
        failed = 0

        start_perf = time.perf_counter()

        for provider in ordered:
            configuration = self._profile.configuration_for(provider.provider_id)

            if not configuration.enabled:
                skipped.append(
                    ProviderSkip(
                        provider_id=provider.provider_id,
                        reason=SkipReason.DISABLED,
                        detail="Disabled by the active SearchProfile.",
                    )
                )
                continue

            if not self._health_tracker.is_available(provider.provider_id):
                skipped.append(
                    ProviderSkip(
                        provider_id=provider.provider_id,
                        reason=SkipReason.UNHEALTHY,
                        detail="Provider has exceeded its consecutive-failure threshold.",
                    )
                )
                continue

            if configuration.fallback_only and results:
                skipped.append(
                    ProviderSkip(
                        provider_id=provider.provider_id,
                        reason=SkipReason.FALLBACK_NOT_NEEDED,
                        detail=(
                            f"{len(results)} result(s) already collected from "
                            "higher-priority provider(s); this fallback provider "
                            "was not needed."
                        ),
                    )
                )
                continue

            request = SearchRequest(
                request_id=self._id_factory(),
                subject_type=subject_type,
                subject_id=subject_id,
                known_attributes=known_attributes,
                requested_at=self._clock(),
            )
            response = self._execute_provider(provider, request)
            provider_responses.append(response)
            results.extend(response.results)
            if response.status in (EnrichmentStatus.SUCCESS, EnrichmentStatus.PARTIAL):
                succeeded += 1
            else:
                failed += 1

        execution_time_total_ms = (time.perf_counter() - start_perf) * 1000
        completed_at = self._clock()

        metrics = SearchCoordinationMetrics(
            providers_considered=len(applicable),
            providers_executed=len(provider_responses),
            providers_succeeded=succeeded,
            providers_failed=failed,
            providers_skipped=len(skipped),
            results_collected=len(results),
            execution_time_total_ms=execution_time_total_ms,
        )

        logger.info(
            "Search coordination complete: subject_id={}, {} executed, "
            "{} succeeded, {} failed, {} skipped, {} result(s), {:.1f}ms",
            subject_id,
            metrics.providers_executed,
            metrics.providers_succeeded,
            metrics.providers_failed,
            metrics.providers_skipped,
            metrics.results_collected,
            metrics.execution_time_total_ms,
        )

        return SearchCoordinationResult(
            subject_id=subject_id,
            subject_type=subject_type,
            provider_responses=tuple(provider_responses),
            results=tuple(results),
            skipped_providers=tuple(skipped),
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
        )

    def _execute_provider(
        self, provider: SearchProviderPort, request: SearchRequest
    ) -> SearchResponse:
        """Call `provider.search(request)`, guarding against it raising,
        and update health tracking from the outcome either way. A
        provider that raises is treated exactly like one that reports
        FAILURE — one misbehaving provider must never sink the whole
        coordination run.
        """

        try:
            response = provider.search(request)
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            at = self._clock()
            self._health_tracker.record_failure(provider.provider_id, at, str(exc))
            logger.warning(
                "Provider {} raised an unexpected exception and was treated as "
                "a failure: {}",
                provider.provider_id,
                exc,
            )
            return SearchResponse(
                provider_id=provider.provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                status=EnrichmentStatus.FAILURE,
                results=(),
                error_message=str(exc),
                started_at=request.requested_at,
                completed_at=at,
            )

        at = self._clock()
        if response.status in (EnrichmentStatus.SUCCESS, EnrichmentStatus.PARTIAL):
            self._health_tracker.record_success(provider.provider_id, at)
            logger.debug(
                "Provider {} returned {} ({} result(s))",
                provider.provider_id,
                response.status.value,
                len(response.results),
            )
        else:
            self._health_tracker.record_failure(
                provider.provider_id,
                at,
                response.error_message
                or f"Provider reported status={response.status.value}",
            )
            logger.debug(
                "Provider {} returned {}: {}",
                provider.provider_id,
                response.status.value,
                response.error_message,
            )
        return response

    def _order_by_priority(
        self, providers: tuple[SearchProviderPort, ...]
    ) -> tuple[SearchProviderPort, ...]:
        """Enabled providers execute in ascending priority order (CRITICAL
        first), with `provider_id` as a stable tiebreaker — never
        registry/dict order, which this framework makes no guarantee is
        reproducible."""

        return tuple(
            sorted(
                providers,
                key=lambda provider: (
                    self._profile.configuration_for(provider.provider_id).priority,
                    provider.provider_id,
                ),
            )
        )
