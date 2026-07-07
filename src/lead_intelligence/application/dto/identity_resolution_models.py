"""Plain data shapes produced by the Identity Resolution Engine.

WHY THIS FILE EXISTS (SEPARATE FROM cleaning_models.py):
Same reasoning as cleaning_models.py's own docstring: each pipeline stage
gets one cohesive vocabulary file, so none of them grows into an unrelated
grab-bag as more stages are added. This file's vocabulary follows the
approved Identity Resolution RFC section numbers directly, referenced in
each class's docstring.

Every dataclass here is immutable (frozen, tuple fields) for the same
reason as every other stage's DTOs: once the engine hands back a decision,
no downstream code should be able to silently mutate the evidence behind
it — that would break the explainability and auditability the RFC requires.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SubjectType(str, Enum):
    """A Person or a Company — the Subject abstraction from the Digital
    Twin Model, unified because both get resolved through the same engine.
    """

    PERSON = "person"
    COMPANY = "company"


class SignalTier(str, Enum):
    """Strong / Moderate / Weak, per RFC §2. Carried on every IdentitySignal
    so scoring never has to re-look up a signal type's tier separately from
    its weight — see IdentityResolutionProfile.definition_for.
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class ConfidenceBand(str, Enum):
    """The three score outcomes defined in RFC §3."""

    AUTO_MERGE = "auto_merge"
    CANDIDATE_REVIEW = "candidate_review"
    NO_MATCH = "no_match"


class ResolutionDecision(str, Enum):
    """The engine's actual action for one record, aggregated across every
    scored candidate (RFC §4-6). Distinct from ConfidenceBand, which
    describes a single candidate's score."""

    AUTO_MERGE = "auto_merge"
    CANDIDATE_REVIEW = "candidate_review"
    NEW_IDENTITY = "new_identity"


class ReviewStatus(str, Enum):
    """Version 1 supports exactly one status: a review item is open until
    a future task adds the full reviewer workflow (RFC §6, explicitly
    Version 2 scope beyond this task)."""

    OPEN = "open"


@dataclass(frozen=True)
class IdentitySignal:
    """One piece of identity evidence extracted from a single cleaned
    record (RFC §1).

    Attributes:
        signal_type: Canonical signal type name (e.g. "duns_number",
            "email_exact", "full_name") — keys into an
            IdentityResolutionProfile's signal_definitions, never hardcoded
            or branched on during scoring (Open/Closed: a new signal type
            is one profile entry plus one extractor function, not a change
            to scoring.py).
        value: The normalized value used for comparison (lowercased,
            trimmed, and — for composite signals — joined in a fixed order).
        tier: This signal's trust tier at extraction time, sourced from the
            profile.
        source_fields: The canonical field name(s) (field_contract.py) this
            signal was derived from, for explainability and audit.
    """

    signal_type: str
    value: str
    tier: SignalTier
    source_fields: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedIdentity:
    """Every identity signal extracted from one cleaned record for one
    Subject type."""

    subject_type: SubjectType
    record_reference: str
    signals: tuple[IdentitySignal, ...]

    def signal_types(self) -> frozenset[str]:
        """The distinct signal types present, for cheap membership checks."""

        return frozenset(signal.signal_type for signal in self.signals)


@dataclass(frozen=True)
class IdentityRecord:
    """A minimal, engine-scoped view of a previously known identity to
    match new evidence against.

    WHY THIS IS NOT THE FUTURE DIGITAL TWIN ENTITY:
    domain/entities/ does not exist yet — implementing it is a deliberate,
    separate future task. IdentityRecord is scoped to exactly what identity
    matching needs (an id plus its known signals) and makes no claim to
    anticipate the eventual Digital Twin entity, which will also carry a
    Timeline, Relationships, and more. A future infrastructure adapter maps
    between the two once domain entities exist; this engine stays unaware
    of that mapping (see application/ports/identity_candidate_port.py).
    """

    identity_id: str
    subject_type: SubjectType
    signals: tuple[IdentitySignal, ...]


@dataclass(frozen=True)
class SignalMatch:
    """One signal considered while scoring a candidate — either matched
    (supporting) or actively contradicted (RFC §3's explainability
    requirement: every score must show its work)."""

    signal_type: str
    tier: SignalTier
    incoming_value: str
    candidate_value: str
    contribution: float


@dataclass(frozen=True)
class MatchExplanation:
    """Everything a human, or an audit reader, needs to understand a score
    without re-deriving it (RFC §3, §8)."""

    supporting: tuple[SignalMatch, ...]
    contradicting: tuple[SignalMatch, ...]
    reason: str


@dataclass(frozen=True)
class ConfidenceScore:
    """A match confidence score — how likely `extracted` and `candidate`
    are the same real-world Subject. Distinct from an Observation's own
    fact-confidence (source reliability); see the RFC's framing section."""

    value: float
    band: ConfidenceBand
    explanation: MatchExplanation


@dataclass(frozen=True)
class MatchCandidate:
    """One existing IdentityRecord, scored against one ExtractedIdentity."""

    candidate: IdentityRecord
    score: ConfidenceScore


@dataclass(frozen=True)
class IdentityAuditEntry:
    """One audit-log-ready record of an identity resolution decision
    (RFC §8). Every automatic decision, and every recomputation, produces
    exactly one of these.

    Persisting this via the domain AuditLogRepository is future wiring —
    Version 1 returns it as part of the engine's in-memory result, the same
    way CleaningResult.audit_trail is returned rather than written directly
    to a live database.
    """

    entry_id: str
    timestamp: datetime
    record_reference: str
    decision: ResolutionDecision
    candidates_considered: tuple[MatchCandidate, ...]
    chosen_identity_id: str | None
    profile_name: str
    profile_version: str
    rationale: str


@dataclass(frozen=True)
class ReviewQueueItem:
    """One record awaiting human review (RFC §6). Version 1 only produces
    and refreshes these — the reviewer actions themselves (confirm/reject/
    defer/escalate) are explicitly Version 2 scope."""

    item_id: str
    record_reference: str
    extracted_identity: ExtractedIdentity
    candidates: tuple[MatchCandidate, ...]
    status: ReviewStatus
    created_at: datetime


@dataclass(frozen=True)
class IdentityResolutionOutcome:
    """The engine's final decision for one record."""

    record_reference: str
    extracted_identity: ExtractedIdentity
    decision: ResolutionDecision
    matched_identity_id: str | None
    new_identity_id: str | None
    candidates: tuple[MatchCandidate, ...]


@dataclass(frozen=True)
class IdentityResolutionMetrics:
    """Aggregate metrics for one full IdentityResolutionEngine run."""

    records_processed: int
    signals_extracted: int
    candidates_generated: int
    auto_merged: int
    sent_to_review: int
    new_identities: int
    execution_time_total_ms: float


@dataclass(frozen=True)
class IdentityResolutionReport:
    """The human-readable digest of one IdentityResolutionEngine run."""

    profile_name: str
    profile_version: str
    started_at: datetime
    completed_at: datetime
    metrics: IdentityResolutionMetrics

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the run, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass(frozen=True)
class IdentityResolutionResult:
    """The Identity Resolution Engine's single output type.

    Attributes:
        outcomes: The final decision for every record processed.
        review_queue: Every ReviewQueueItem produced this run.
        audit_trail: Every IdentityAuditEntry produced this run, in
            processing order.
        report: The human-readable run digest.
        metrics: The raw numbers the report is built from (same object as
            `report.metrics` — exposed at the top level too, mirroring
            CleaningResult's convention).
    """

    outcomes: tuple[IdentityResolutionOutcome, ...]
    review_queue: tuple[ReviewQueueItem, ...]
    audit_trail: tuple[IdentityAuditEntry, ...]
    report: IdentityResolutionReport
    metrics: IdentityResolutionMetrics
