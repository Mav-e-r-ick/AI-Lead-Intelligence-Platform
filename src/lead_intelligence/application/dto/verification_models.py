"""Plain data shapes produced by the Contact Verification Framework.

WHY THIS FILE EXISTS (SEPARATE FROM enrichment_models.py / comparison_models.py):
Same reasoning as every other stage's own DTO file's docstring: each
pipeline stage gets one cohesive vocabulary file, so none of them grows
into an unrelated grab-bag as more stages are added.

Every dataclass here is immutable (frozen, tuple/mapping-proxy fields) for
the same reason as every other stage's DTOs: once a provider or the
coordinator hands back a result, no downstream code should be able to
silently mutate the evidence behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

__all__ = [
    "ContactType",
    "VerificationStatus",
    "VerificationSkipReason",
    "VerificationRequest",
    "VerificationResult",
    "VerificationProviderSkip",
    "VerificationCoordinationMetrics",
    "VerificationReport",
]


class ContactType(str, Enum):
    """Which kind of contact detail a VerificationRequest is about. Used to
    route a request to the providers that can actually answer it
    (EmailVerificationPort vs. PhoneVerificationPort)."""

    EMAIL = "email"
    PHONE = "phone"


class VerificationStatus(str, Enum):
    """The outcome of one provider's attempt to verify one contact detail.

    VALID: the provider confirmed the contact is deliverable/reachable.
    INVALID: the provider confirmed the contact is NOT deliverable/
        reachable (e.g. mailbox does not exist, number disconnected).
    RISKY: the provider found the contact deliverable/reachable but flagged
        it as uncertain (e.g. a catch-all domain, a role-based mailbox, a
        VOIP number) — neither a clean pass nor a clean fail.
    UNKNOWN: the provider could not determine an answer (e.g. greylisting,
        no response from the mail server) — not the same as an error; the
        provider ran and genuinely could not tell.
    ERROR: the provider call itself failed (network error, invalid
        credentials, malformed request) — this framework's own failure
        mode, independent of anything about the contact detail itself.
    TIMEOUT: the provider did not respond within its configured budget.
    RATE_LIMITED: the provider rejected the request due to rate limiting.
    """

    VALID = "valid"
    INVALID = "invalid"
    RISKY = "risky"
    UNKNOWN = "unknown"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class VerificationSkipReason(str, Enum):
    """Why the coordinator did not execute an otherwise-applicable provider."""

    DISABLED = "disabled"
    UNSUPPORTED_CONTACT_TYPE = "unsupported_contact_type"


@dataclass(frozen=True)
class VerificationRequest:
    """What the coordinator asks every applicable provider to fulfill.

    One VerificationRequest is built per coordination run and passed
    identically to every executed provider — providers differ in *how*
    they answer it, never in what's being asked.

    Attributes:
        request_id: Opaque, traceable id for this request (carried onto
            every resulting VerificationResult).
        contact_type: EMAIL or PHONE — determines which registered
            providers even apply.
        value: The contact detail to verify, exactly as it should be
            checked (e.g. "ada@example.com", "+1-555-0100"). This framework
            does not normalize or validate its shape — that is the
            Cleaning Engine's job, applied before this request is built.
        subject_id: The Digital Twin id (or provisional identity id) this
            contact detail belongs to, for traceability. Opaque to this
            framework.
        requested_at: When this request was built.
    """

    request_id: str
    contact_type: ContactType
    value: str
    subject_id: str
    requested_at: datetime


@dataclass(frozen=True)
class VerificationResult:
    """One provider's answer to one VerificationRequest.

    Attributes:
        provider_id: Which provider produced this result.
        request_id: The originating VerificationRequest's id.
        subject_id: The originating request's subject_id, carried through
            for convenience.
        contact_type: The originating request's contact_type.
        value: The originating request's value, carried through for
            convenience (so a result is self-describing without needing
            the original request alongside it).
        status: One of the seven VerificationStatus outcomes.
        confidence: In [0.0, 1.0] if the provider reports one, else None —
            not every provider gives a confidence score.
        reason: A short, human-readable explanation from the provider
            (e.g. "mailbox does not exist"), if it gives one.
        error_message: Populated only for ERROR/TIMEOUT/RATE_LIMITED —
            what went wrong with the provider call itself.
        started_at: When this provider's verify() call began.
        completed_at: When this provider's verify() call finished.
        raw_response: Provider-specific extra detail, kept opaque here for
            traceability without this framework needing to understand it.
    """

    provider_id: str
    request_id: str
    subject_id: str
    contact_type: ContactType
    value: str
    status: VerificationStatus
    confidence: float | None
    reason: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime
    raw_response: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "raw_response", MappingProxyType(dict(self.raw_response))
        )

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of this provider's verify() call, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass(frozen=True)
class VerificationProviderSkip:
    """Why the coordinator did not execute one otherwise-applicable provider."""

    provider_id: str
    reason: VerificationSkipReason
    detail: str


@dataclass(frozen=True)
class VerificationCoordinationMetrics:
    """Aggregate metrics for one VerificationCoordinator.verify() run."""

    providers_considered: int
    providers_executed: int
    providers_succeeded: int
    providers_failed: int
    providers_skipped: int

    execution_time_total_ms: float


@dataclass(frozen=True)
class VerificationReport:
    """The Contact Verification Framework's single combined output type for
    one VerificationRequest.

    Attributes:
        request_id: The originating VerificationRequest's id.
        subject_id: The originating request's subject_id.
        contact_type: The originating request's contact_type.
        value: The originating request's value.
        provider_results: Every executed provider's individual
            VerificationResult, in execution order. This framework
            deliberately does not pick a single "winning" verdict when
            multiple providers disagree — that interpretation, like the
            Executive Comparison Engine's differences, is future work.
        skipped_providers: Every applicable-but-not-executed provider,
            with why (disabled, or unsupported for this contact_type).
        started_at: When coordination began.
        completed_at: When coordination finished.
        metrics: The raw numbers this report's shape is built from.
    """

    request_id: str
    subject_id: str
    contact_type: ContactType
    value: str
    provider_results: tuple[VerificationResult, ...]
    skipped_providers: tuple[VerificationProviderSkip, ...]
    started_at: datetime
    completed_at: datetime
    metrics: VerificationCoordinationMetrics

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the whole coordination run, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000
