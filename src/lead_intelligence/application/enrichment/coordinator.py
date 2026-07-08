"""EnrichmentCoordinator: the Enrichment Provider Framework's single
orchestration point.

Given a Subject (a Digital Twin id, or a provisional identity id from the
Identity Resolution Engine — the framework treats both identically as an
opaque `subject_id`), the coordinator:
1. Determines which registered providers even apply to this subject_type.
2. Filters to providers that are enabled, healthy, and due for a refresh.
3. Executes the remaining providers in priority order.
4. Collects every ObservationCandidate from every executed provider.
5. Returns one combined EnrichmentCoordinationResult.

WHY THIS CLASS CONTAINS NO PROVIDER-SPECIFIC LOGIC:
Every decision this coordinator makes (enabled? healthy? stale? what
order?) is answered generically, via EnrichmentProfile, ProviderRegistry,
and ProviderHealthTracker — never by branching on a specific provider_id.
Concrete providers (Company Website, News, D&B, ...) are a future task;
this class must work unmodified once they exist.

WHY EXECUTION IS SEQUENTIAL, NOT CONCURRENT:
Version 1 is framework-only — no real I/O (no web scraping, no external
API calls) happens here yet, so there is nothing to gain from concurrency
and much to lose in determinism and testability. A future infrastructure
task can parallelize real provider calls without changing this class's
public contract.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Mapping

from loguru import logger

from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentCoordinationMetrics,
    EnrichmentCoordinationResult,
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ObservationCandidate,
    ProviderSkip,
    SkipReason,
    SubjectType,
)
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.provider_health import (
    ProviderHealthTracker,
)
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)


class EnrichmentCoordinator:
    """Runs every applicable, enabled, healthy, due-for-refresh provider
    for one Subject, in priority order, and combines their results."""

    def __init__(
        self,
        registry: ProviderRegistry,
        profile: EnrichmentProfile,
        health_tracker: ProviderHealthTracker | None = None,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure a coordinator bound to one registry and one profile.

        Args:
            registry: Every provider this coordinator may call (dependency
                injection).
            profile: The active EnrichmentProfile.
            health_tracker: Where provider health is recorded and
                consulted. Defaults to a fresh, empty tracker; pass a
                shared one to preserve health across multiple `enrich()`
                calls (e.g. across subjects in the same run).
            id_factory: Generates each EnrichmentRequest's id. Override
                with a deterministic sequence in tests.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._registry = registry
        self._profile = profile
        self._health_tracker = health_tracker or ProviderHealthTracker()
        self._id_factory = id_factory
        self._clock = clock

    def enrich(
        self,
        subject_type: SubjectType,
        subject_id: str,
        known_attributes: Mapping[str, str],
        attributes_of_interest: tuple[str, ...] = (),
        provider_last_fetched: Mapping[str, datetime] | None = None,
    ) -> EnrichmentCoordinationResult:
        """Enrich one Subject and return the combined result.

        Args:
            subject_type: Person or Company.
            subject_id: The Digital Twin id (or provisional identity id)
                being enriched. Opaque to this framework.
            known_attributes: Canonical field name -> known value, passed
                identically to every executed provider (e.g. {"full_name":
                "Ada Lovelace", "company_name": "Acme Corp"}).
            attributes_of_interest: An optional hint of which attributes
                matter most for this run; passed through unchanged.
            provider_last_fetched: provider_id -> when that provider was
                last successfully run for this subject, if known. Absent
                or missing entries are treated as "never run" (always due
                for refresh). This framework does not persist this itself
                — a future task supplies it from real enrichment history
                once that exists.

        Raises:
            InvalidEnrichmentConfigurationError: If the profile itself is
                invalid — raised before any provider is executed.
        """

        self._profile.validate()
        provider_last_fetched = provider_last_fetched or {}

        started_at = self._clock()
        logger.info(
            "Enrichment coordination starting: profile='{}', subject_type={}, "
            "subject_id={}",
            self._profile.name,
            subject_type.value,
            subject_id,
        )

        applicable = self._registry.providers_supporting(subject_type)
        ordered = self._order_by_priority(applicable)

        provider_responses: list[EnrichmentResponse] = []
        observations: list[ObservationCandidate] = []
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
                        detail="Disabled by the active EnrichmentProfile.",
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

            last_fetched_at = provider_last_fetched.get(provider.provider_id)
            if not configuration.refresh_policy.should_refresh(
                last_fetched_at, started_at
            ):
                skipped.append(
                    ProviderSkip(
                        provider_id=provider.provider_id,
                        reason=SkipReason.NOT_STALE,
                        detail=f"Last fetched at {last_fetched_at}; not yet due for refresh.",
                    )
                )
                continue

            request = EnrichmentRequest(
                request_id=self._id_factory(),
                subject_type=subject_type,
                subject_id=subject_id,
                known_attributes=known_attributes,
                requested_at=self._clock(),
                attributes_of_interest=attributes_of_interest,
            )
            response = self._execute_provider(provider, request)
            provider_responses.append(response)
            observations.extend(response.observations)
            if response.status in (EnrichmentStatus.SUCCESS, EnrichmentStatus.PARTIAL):
                succeeded += 1
            else:
                failed += 1

        execution_time_total_ms = (time.perf_counter() - start_perf) * 1000
        completed_at = self._clock()

        metrics = EnrichmentCoordinationMetrics(
            providers_considered=len(applicable),
            providers_executed=len(provider_responses),
            providers_succeeded=succeeded,
            providers_failed=failed,
            providers_skipped=len(skipped),
            observations_collected=len(observations),
            execution_time_total_ms=execution_time_total_ms,
        )

        logger.info(
            "Enrichment coordination complete: subject_id={}, {} executed, "
            "{} succeeded, {} failed, {} skipped, {} observation(s), {:.1f}ms",
            subject_id,
            metrics.providers_executed,
            metrics.providers_succeeded,
            metrics.providers_failed,
            metrics.providers_skipped,
            metrics.observations_collected,
            metrics.execution_time_total_ms,
        )

        return EnrichmentCoordinationResult(
            subject_id=subject_id,
            subject_type=subject_type,
            provider_responses=tuple(provider_responses),
            observations=tuple(observations),
            skipped_providers=tuple(skipped),
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
        )

    def _execute_provider(
        self, provider: EnrichmentProviderPort, request: EnrichmentRequest
    ) -> EnrichmentResponse:
        """Call `provider.fetch(request)`, guarding against it raising, and
        update health tracking from the outcome either way. A provider
        that raises is treated exactly like one that reports FAILURE —
        one misbehaving provider must never sink the whole coordination run.
        """

        try:
            response = provider.fetch(request)
        except Exception as exc:  # noqa: BLE001 - fail-safe: see docstring above
            at = self._clock()
            self._health_tracker.record_failure(provider.provider_id, at, str(exc))
            logger.warning(
                "Provider {} raised an unexpected exception and was treated as "
                "a failure: {}",
                provider.provider_id,
                exc,
            )
            return EnrichmentResponse(
                provider_id=provider.provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                status=EnrichmentStatus.FAILURE,
                observations=(),
                error_message=str(exc),
                started_at=request.requested_at,
                completed_at=at,
            )

        at = self._clock()
        if response.status in (EnrichmentStatus.SUCCESS, EnrichmentStatus.PARTIAL):
            self._health_tracker.record_success(provider.provider_id, at)
            logger.debug(
                "Provider {} returned {} ({} observation(s))",
                provider.provider_id,
                response.status.value,
                len(response.observations),
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
        self, providers: tuple[EnrichmentProviderPort, ...]
    ) -> tuple[EnrichmentProviderPort, ...]:
        """Enabled providers execute in ascending ProviderPriority order
        (CRITICAL first), with `provider_id` as a stable tiebreaker — never
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
