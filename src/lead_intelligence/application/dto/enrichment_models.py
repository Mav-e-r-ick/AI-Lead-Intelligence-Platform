"""Plain data shapes produced by the Enrichment Provider Framework.

WHY THIS FILE EXISTS (SEPARATE FROM cleaning_models.py / identity_resolution_models.py):
Same reasoning as those files' own docstrings: each pipeline stage gets one
cohesive vocabulary file, so none of them grows into an unrelated grab-bag
as more stages are added.

Every dataclass here is immutable (frozen, tuple/mapping-proxy fields) for
the same reason as every other stage's DTOs: once a provider or the
coordinator hands back a result, no downstream code should be able to
silently mutate the evidence behind it.

`SubjectType` is intentionally reused from identity_resolution_models.py
rather than redefined here — a Person or a Company is the same Subject
concept regardless of which engine is looking at it (see the Digital Twin
Model's Subject abstraction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from lead_intelligence.application.dto.identity_resolution_models import SubjectType

__all__ = [
    "SubjectType",
    "EnrichmentStatus",
    "ProviderPriority",
    "ProviderHealthStatus",
    "SkipReason",
    "ObservationCandidate",
    "EnrichmentRequest",
    "EnrichmentResponse",
    "ProviderHealth",
    "ProviderSkip",
    "EnrichmentCoordinationMetrics",
    "EnrichmentCoordinationResult",
]


class EnrichmentStatus(str, Enum):
    """The outcome of one provider's attempt to fulfill one EnrichmentRequest."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class ProviderPriority(int, Enum):
    """Execution ordering, lowest value first. A plain int would work
    mechanically, but a named enum keeps every profile's intent readable
    ("CRITICAL" vs "3") and gives mypy something to check against typos.
    """

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class ProviderHealthStatus(str, Enum):
    """A provider's current operational standing, per ProviderHealthTracker."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class SkipReason(str, Enum):
    """Why the coordinator did not execute an otherwise-applicable provider."""

    DISABLED = "disabled"
    UNHEALTHY = "unhealthy"
    NOT_STALE = "not_stale"
    UNSUPPORTED_SUBJECT_TYPE = "unsupported_subject_type"


@dataclass(frozen=True)
class ObservationCandidate:
    """One candidate fact a provider observed about a Subject.

    WHY THIS IS NOT THE FUTURE OBSERVATION DOMAIN ENTITY:
    domain/entities/ does not exist yet — the immutable, provenance-and-
    confidence-bearing Observation entity described in the Executive
    Intelligence Architecture is a separate, not-yet-reached task. An
    ObservationCandidate is deliberately scoped to only what a provider can
    honestly assert today (which attribute, what value, from where, when),
    the same "engine-scoped, not the future entity" pattern already used
    for IdentityRecord in the Identity Resolution Engine. A future stage —
    the Observation Pipeline — is responsible for turning candidates into
    real Observations (with conflict resolution, resolved fact-confidence,
    etc.); this framework only collects candidates, it does not resolve them.

    Attributes:
        subject_id: The Digital Twin (or provisional identity) id this
            observation is about — the same id passed on the originating
            EnrichmentRequest.
        attribute: Canonical field name this observation is about (e.g.
            "title", "company_name") — never a provider-specific label.
        value: The observed value, as a plain string. Deliberately not
            typed per-attribute; normalizing/validating a value's shape is
            the Cleaning Engine's job, applied to future re-ingested data,
            not this framework's.
        provider_id: Which provider produced this candidate.
        observed_at: When the provider observed this fact (not necessarily
            "now" — a provider may report an as-of date from its source).
        source_url: Where this fact was found, if the provider can say.
        raw_context: Provider-specific extra detail, kept opaque here for
            traceability without this framework needing to understand it.
    """

    subject_id: str
    attribute: str
    value: str
    provider_id: str
    observed_at: datetime
    source_url: str | None = None
    raw_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "raw_context", MappingProxyType(dict(self.raw_context))
        )


@dataclass(frozen=True)
class EnrichmentRequest:
    """What the coordinator asks every applicable provider to fulfill.

    One EnrichmentRequest is built per coordination run and passed
    identically to every executed provider — providers differ in *how*
    they answer it, never in what's being asked.

    Attributes:
        request_id: Opaque, traceable id for this request (carried onto
            every resulting EnrichmentResponse and ObservationCandidate's
            audit trail).
        subject_type: Person or Company.
        subject_id: The Digital Twin id (or a provisional identity id from
            Identity Resolution) this request is about. The framework does
            not care which — it is an opaque string.
        known_attributes: Canonical field name -> known value, giving a
            provider enough to search on (e.g. {"full_name": "Ada
            Lovelace", "company_name": "Acme Corp"}).
        requested_at: When this request was built.
        attributes_of_interest: An optional hint of which attributes the
            caller cares about; empty means "anything you have."
    """

    request_id: str
    subject_type: SubjectType
    subject_id: str
    known_attributes: Mapping[str, str]
    requested_at: datetime
    attributes_of_interest: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "known_attributes", MappingProxyType(dict(self.known_attributes))
        )


@dataclass(frozen=True)
class EnrichmentResponse:
    """One provider's answer to one EnrichmentRequest."""

    provider_id: str
    request_id: str
    subject_id: str
    status: EnrichmentStatus
    observations: tuple[ObservationCandidate, ...]
    error_message: str | None
    started_at: datetime
    completed_at: datetime

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of this provider's fetch() call, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass(frozen=True)
class ProviderHealth:
    """A provider's current operational standing, as of its last-recorded
    success or failure. Immutable snapshot — ProviderHealthTracker
    (application/enrichment/provider_health.py) is what advances it over
    time via pure transition functions, the same "make illegal states
    unrepresentable" style used throughout this platform.
    """

    provider_id: str
    status: ProviderHealthStatus
    consecutive_failures: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class ProviderSkip:
    """Why the coordinator did not execute one otherwise-applicable provider."""

    provider_id: str
    reason: SkipReason
    detail: str


@dataclass(frozen=True)
class EnrichmentCoordinationMetrics:
    """Aggregate metrics for one EnrichmentCoordinator.enrich() run."""

    providers_considered: int
    providers_executed: int
    providers_succeeded: int
    providers_failed: int
    providers_skipped: int
    observations_collected: int
    execution_time_total_ms: float


@dataclass(frozen=True)
class EnrichmentCoordinationResult:
    """The Enrichment Provider Framework's single combined output type for
    one subject.

    Attributes:
        subject_id: The Digital Twin (or provisional identity) id enriched.
        subject_type: Person or Company.
        provider_responses: Every executed provider's individual response,
            in execution order.
        observations: Every ObservationCandidate from every executed
            provider, flattened into one run-wide sequence — a convenience
            view; the same candidates also live on each response.
        skipped_providers: Every applicable-but-not-executed provider, with
            why (RFC framing: disabled, unhealthy, not yet stale, or
            simply unsupported for this subject_type).
        started_at: When coordination began.
        completed_at: When coordination finished.
        metrics: The raw numbers this result's shape is built from.
    """

    subject_id: str
    subject_type: SubjectType
    provider_responses: tuple[EnrichmentResponse, ...]
    observations: tuple[ObservationCandidate, ...]
    skipped_providers: tuple[ProviderSkip, ...]
    started_at: datetime
    completed_at: datetime
    metrics: EnrichmentCoordinationMetrics

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the whole coordination run, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000
