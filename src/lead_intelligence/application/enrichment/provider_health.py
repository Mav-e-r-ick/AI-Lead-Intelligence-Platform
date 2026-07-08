"""Provider health tracking: whether a provider has been failing enough
recently that the coordinator should stop calling it for a while (a
lightweight circuit breaker), and the pure state-transition functions that
`ProviderHealthTracker` is built from.

WHY THE TRANSITIONS ARE PURE FUNCTIONS, AND THE TRACKER IS A THIN SHELL
AROUND THEM:
`record_success`/`record_failure` take a ProviderHealth and return a new
one — the same "make illegal states unrepresentable" + immutability style
used throughout this platform (see scoring.py's docstring in the Identity
Resolution Engine for the same reasoning applied to scores). This keeps
the actual state-transition logic trivially unit-testable in isolation,
independent of the tracker's bookkeeping (which providers exist, mutating
a dict) around it.
"""

from __future__ import annotations

from datetime import datetime

from lead_intelligence.application.dto.enrichment_models import (
    ProviderHealth,
    ProviderHealthStatus,
)

#: Consecutive failures at or beyond which a provider is considered
#: UNHEALTHY (and the coordinator will skip it) rather than merely DEGRADED.
DEFAULT_UNHEALTHY_THRESHOLD = 3


def initial_health(provider_id: str) -> ProviderHealth:
    """The starting health for a provider that has never been run."""

    return ProviderHealth(
        provider_id=provider_id,
        status=ProviderHealthStatus.UNKNOWN,
        consecutive_failures=0,
        last_success_at=None,
        last_failure_at=None,
        last_error=None,
    )


def record_success(health: ProviderHealth, at: datetime) -> ProviderHealth:
    """A successful (or partially successful) fetch resets the failure streak."""

    return ProviderHealth(
        provider_id=health.provider_id,
        status=ProviderHealthStatus.HEALTHY,
        consecutive_failures=0,
        last_success_at=at,
        last_failure_at=health.last_failure_at,
        last_error=None,
    )


def record_failure(
    health: ProviderHealth,
    at: datetime,
    error: str,
    unhealthy_threshold: int = DEFAULT_UNHEALTHY_THRESHOLD,
) -> ProviderHealth:
    """A failed fetch extends the failure streak, and crosses into
    UNHEALTHY once `unhealthy_threshold` consecutive failures accumulate."""

    consecutive_failures = health.consecutive_failures + 1
    status = (
        ProviderHealthStatus.UNHEALTHY
        if consecutive_failures >= unhealthy_threshold
        else ProviderHealthStatus.DEGRADED
    )
    return ProviderHealth(
        provider_id=health.provider_id,
        status=status,
        consecutive_failures=consecutive_failures,
        last_success_at=health.last_success_at,
        last_failure_at=at,
        last_error=error,
    )


class ProviderHealthTracker:
    """An in-memory, mutable record of every provider's current health,
    built from the pure transition functions above.

    Deliberately in-memory only — persisting health across process
    restarts (or sharing it across coordinator instances) is
    infrastructure work explicitly out of this task's framework-only scope.
    """

    def __init__(self, unhealthy_threshold: int = DEFAULT_UNHEALTHY_THRESHOLD) -> None:
        self._health: dict[str, ProviderHealth] = {}
        self._unhealthy_threshold = unhealthy_threshold

    def get(self, provider_id: str) -> ProviderHealth:
        """This provider's current health, defaulting to UNKNOWN (never
        run) if it has no recorded history yet."""

        return self._health.get(provider_id, initial_health(provider_id))

    def is_available(self, provider_id: str) -> bool:
        """Whether the coordinator should attempt to run this provider —
        false only once it has crossed into UNHEALTHY."""

        return self.get(provider_id).status is not ProviderHealthStatus.UNHEALTHY

    def record_success(self, provider_id: str, at: datetime) -> ProviderHealth:
        updated = record_success(self.get(provider_id), at)
        self._health[provider_id] = updated
        return updated

    def record_failure(
        self, provider_id: str, at: datetime, error: str
    ) -> ProviderHealth:
        updated = record_failure(
            self.get(provider_id), at, error, self._unhealthy_threshold
        )
        self._health[provider_id] = updated
        return updated
