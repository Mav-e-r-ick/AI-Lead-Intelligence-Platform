"""VerificationCoordinator: the Contact Verification Framework's single
orchestration point.

Given one contact detail (an email address or a phone number, tied to a
subject), the coordinator:
1. Determines which registered providers even support this contact_type.
2. Filters to providers that are enabled under the active VerificationProfile.
3. Executes the remaining providers in priority order.
4. Collects every VerificationResult from every executed provider.
5. Returns one combined VerificationReport.

WHY THIS CLASS CONTAINS NO PROVIDER-SPECIFIC LOGIC:
Every decision this coordinator makes (enabled? what order?) is answered
generically, via VerificationProfile and each provider's own declared
`supported_contact_types` — never by branching on a specific provider_id.
Concrete providers (NeverBounce, ZeroBounce, Kickbox, Bouncer, Twilio
Lookup, Numverify, Abstract API, ...) are a future task; this class must
work unmodified once they exist.

WHY THIS COORDINATOR NEVER PICKS A "WINNING" VerificationResult:
When two enabled providers disagree (one says VALID, another RISKY), this
framework reports both, unresolved — the same restraint the Executive
Comparison Engine exercises around its own differences. Deciding which
provider to trust, or how to combine multiple verdicts into one decision,
is explicitly future work, not part of "the verification framework."

WHY EXECUTION IS SEQUENTIAL, NOT CONCURRENT:
Version 1 is framework-only — no real I/O (no commercial API calls)
happens here yet, so there is nothing to gain from concurrency and much to
lose in determinism and testability. A future infrastructure task can
parallelize real provider calls without changing this class's public
contract.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Sequence

from loguru import logger

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationCoordinationMetrics,
    VerificationProviderSkip,
    VerificationReport,
    VerificationRequest,
    VerificationResult,
    VerificationSkipReason,
    VerificationStatus,
)
from lead_intelligence.application.ports.verification_provider_port import (
    VerificationProviderPort,
)
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.domain.exceptions import DuplicateVerificationProviderError

#: Statuses that represent the *provider call itself* failing, as opposed
#: to a successfully-obtained verdict (even an uncertain one like RISKY or
#: UNKNOWN is still a successful provider call) — mirrors EnrichmentStatus's
#: SUCCESS/PARTIAL vs. FAILURE/TIMEOUT/RATE_LIMITED split in the Enrichment
#: Provider Framework's coordinator.
_TECHNICAL_FAILURE_STATUSES = frozenset(
    {
        VerificationStatus.ERROR,
        VerificationStatus.TIMEOUT,
        VerificationStatus.RATE_LIMITED,
    }
)


class VerificationCoordinator:
    """Runs every applicable, enabled provider for one contact detail, in
    priority order, and combines their results.

    WHY THERE IS NO SEPARATE PUBLIC REGISTRY CLASS (UNLIKE ProviderRegistry
    IN THE ENRICHMENT PROVIDER FRAMEWORK):
    This task's explicit component list does not include one; folding
    provider lookup and its duplicate-id guard directly into this
    coordinator's constructor keeps the framework to exactly what was
    asked for, without inventing an extra public surface.
    """

    def __init__(
        self,
        providers: Sequence[VerificationProviderPort],
        profile: VerificationProfile,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure a coordinator bound to one set of providers and one profile.

        Args:
            providers: Every provider this coordinator may call (dependency
                injection — not a hardcoded list).
            profile: The active VerificationProfile.
            id_factory: Generates each VerificationRequest's id. Override
                with a deterministic sequence in tests.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.

        Raises:
            DuplicateVerificationProviderError: If two providers report the
                same `provider_id`.
        """

        by_id: dict[str, VerificationProviderPort] = {}
        for provider in providers:
            if provider.provider_id in by_id:
                raise DuplicateVerificationProviderError(
                    f"Provider id '{provider.provider_id}' is registered more "
                    "than once; provider ids must be unique."
                )
            by_id[provider.provider_id] = provider
        self._providers = by_id
        self._profile = profile
        self._id_factory = id_factory
        self._clock = clock

    def verify(
        self, contact_type: ContactType, subject_id: str, value: str
    ) -> VerificationReport:
        """Verify one contact detail and return the combined report.

        Args:
            contact_type: EMAIL or PHONE — determines which registered
                providers even apply.
            subject_id: The Digital Twin id (or provisional identity id)
                this contact detail belongs to. Opaque to this framework.
            value: The contact detail to verify (e.g. "ada@example.com").

        Raises:
            InvalidVerificationConfigurationError: If the profile itself is
                invalid — raised before any provider is executed.
        """

        self._profile.validate()

        started_at = self._clock()
        logger.info(
            "Verification coordination starting: profile='{}', contact_type={}, "
            "subject_id={}",
            self._profile.name,
            contact_type.value,
            subject_id,
        )

        applicable = self._providers_supporting(contact_type)
        ordered = self._order_by_priority(applicable)

        request = VerificationRequest(
            request_id=self._id_factory(),
            contact_type=contact_type,
            value=value,
            subject_id=subject_id,
            requested_at=started_at,
        )

        results: list[VerificationResult] = []
        skipped: list[VerificationProviderSkip] = []
        succeeded = 0
        failed = 0

        start_perf = time.perf_counter()

        for provider in ordered:
            configuration = self._profile.configuration_for(provider.provider_id)

            if not configuration.enabled:
                skipped.append(
                    VerificationProviderSkip(
                        provider_id=provider.provider_id,
                        reason=VerificationSkipReason.DISABLED,
                        detail="Disabled by the active VerificationProfile.",
                    )
                )
                continue

            result = self._execute_provider(provider, request)
            results.append(result)
            if result.status in _TECHNICAL_FAILURE_STATUSES:
                failed += 1
            else:
                succeeded += 1

        execution_time_total_ms = (time.perf_counter() - start_perf) * 1000
        completed_at = self._clock()

        metrics = VerificationCoordinationMetrics(
            providers_considered=len(applicable),
            providers_executed=len(results),
            providers_succeeded=succeeded,
            providers_failed=failed,
            providers_skipped=len(skipped),
            execution_time_total_ms=execution_time_total_ms,
        )

        logger.info(
            "Verification coordination complete: subject_id={}, {} executed, "
            "{} succeeded, {} failed, {} skipped",
            subject_id,
            metrics.providers_executed,
            metrics.providers_succeeded,
            metrics.providers_failed,
            metrics.providers_skipped,
        )

        return VerificationReport(
            request_id=request.request_id,
            subject_id=subject_id,
            contact_type=contact_type,
            value=value,
            provider_results=tuple(results),
            skipped_providers=tuple(skipped),
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
        )

    def _execute_provider(
        self, provider: VerificationProviderPort, request: VerificationRequest
    ) -> VerificationResult:
        """Call `provider.verify(request)`, guarding against it raising. A
        provider that raises is treated exactly like one that reports
        ERROR — one misbehaving provider must never sink the whole
        coordination run.
        """

        try:
            result = provider.verify(request)
        except Exception as exc:  # noqa: BLE001 - fail-safe: see docstring above
            at = self._clock()
            logger.warning(
                "Provider {} raised an unexpected exception and was treated as "
                "an ERROR result: {}",
                provider.provider_id,
                exc,
            )
            return VerificationResult(
                provider_id=provider.provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                contact_type=request.contact_type,
                value=request.value,
                status=VerificationStatus.ERROR,
                confidence=None,
                reason=None,
                error_message=str(exc),
                started_at=request.requested_at,
                completed_at=at,
            )

        logger.debug(
            "Provider {} returned {}",
            provider.provider_id,
            result.status.value,
        )
        return result

    def _providers_supporting(
        self, contact_type: ContactType
    ) -> tuple[VerificationProviderPort, ...]:
        """Every registered provider that declares support for
        `contact_type`, in registration order. A phone-only provider, for
        example, is excluded entirely from an email verification request —
        never even considered, let alone skipped-with-a-reason (mirrors
        ProviderRegistry.providers_supporting in the Enrichment Provider
        Framework)."""

        return tuple(
            provider
            for provider in self._providers.values()
            if contact_type in provider.supported_contact_types
        )

    def _order_by_priority(
        self, providers: tuple[VerificationProviderPort, ...]
    ) -> tuple[VerificationProviderPort, ...]:
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
