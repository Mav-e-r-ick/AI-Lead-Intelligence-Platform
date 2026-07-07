"""IdentityResolutionEngine: the Identity Resolution Engine's single
orchestration point (RFC §12: Signal Extraction -> Candidate Generation ->
Confidence Scoring -> Decision -> Audit Log).

WHY THIS CLASS TAKES id_factory AND clock AS CONSTRUCTOR ARGUMENTS:
Every decision this engine makes must be deterministic and reproducible
(RFC requirement, and this task's explicit "keep the engine deterministic"
requirement). Defaulting to `uuid4()`/`datetime.now()` is fine for real
use but makes tests non-reproducible unless both are injectable — the same
dependency-injection seam CleaningPipeline uses for its rule set.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from loguru import logger

from lead_intelligence.application.dto.cleaning_models import (
    CleanedLeadDataset,
    CleanedLeadRecord,
)
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityAuditEntry,
    IdentityResolutionMetrics,
    IdentityResolutionOutcome,
    IdentityResolutionReport,
    IdentityResolutionResult,
    MatchCandidate,
    ResolutionDecision,
    ReviewQueueItem,
    ReviewStatus,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.candidate_generation import (
    generate_candidates,
)
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
)
from lead_intelligence.application.identity_resolution.decision import (
    decide,
    review_candidates,
    select_merge_target,
)
from lead_intelligence.application.identity_resolution.scoring import score_candidate
from lead_intelligence.application.identity_resolution.signal_extraction import (
    extract_identity,
)
from lead_intelligence.application.ports.identity_candidate_port import (
    IdentityCandidatePort,
)


class IdentityResolutionEngine:
    """Resolves the Subject identity of every record in a CleanedLeadDataset."""

    def __init__(
        self,
        candidate_port: IdentityCandidatePort,
        profile: IdentityResolutionProfile,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure an engine bound to one candidate source and one profile.

        Args:
            candidate_port: Where to look up previously known identities
                (dependency injection — see identity_candidate_port.py).
            profile: The active IdentityResolutionProfile.
            id_factory: Generates ids for new identities, review items, and
                audit entries. Override with a deterministic sequence in tests.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._port = candidate_port
        self._profile = profile
        self._id_factory = id_factory
        self._clock = clock

    def resolve_record(
        self,
        record: CleanedLeadRecord,
        subject_type: SubjectType,
        record_reference: str,
    ) -> tuple[IdentityResolutionOutcome, IdentityAuditEntry, ReviewQueueItem | None]:
        """Resolve one record's identity and return its outcome, audit
        entry, and (if applicable) review queue item.

        Every path — auto-merge, candidate review, or new identity —
        produces exactly one IdentityAuditEntry (RFC §8: every automatic
        decision must be logged, with no exceptions).
        """

        extracted = extract_identity(
            record, subject_type, record_reference, self._profile
        )
        candidates = generate_candidates(extracted, self._port, self._profile)

        scored = tuple(
            MatchCandidate(
                candidate=candidate,
                score=score_candidate(extracted, candidate, self._profile),
            )
            for candidate in candidates
        )
        decision = decide(scored)

        matched_identity_id: str | None = None
        new_identity_id: str | None = None
        review_item: ReviewQueueItem | None = None
        relevant_candidates: tuple[MatchCandidate, ...] = scored

        if decision is ResolutionDecision.AUTO_MERGE:
            target = select_merge_target(scored)
            matched_identity_id = target.candidate.identity_id
            relevant_candidates = (target,)
            logger.info(
                "Identity resolution: {} auto-merged into {} (score={:.3f})",
                record_reference,
                matched_identity_id,
                target.score.value,
            )
        elif decision is ResolutionDecision.CANDIDATE_REVIEW:
            relevant_candidates = review_candidates(scored)
            review_item = ReviewQueueItem(
                item_id=self._id_factory(),
                record_reference=record_reference,
                extracted_identity=extracted,
                candidates=relevant_candidates,
                status=ReviewStatus.OPEN,
                created_at=self._clock(),
            )
            logger.info(
                "Identity resolution: {} queued for manual review ({} candidate(s))",
                record_reference,
                len(relevant_candidates),
            )
        else:
            new_identity_id = self._id_factory()
            relevant_candidates = ()
            logger.info(
                "Identity resolution: {} has no plausible match -> new identity {}",
                record_reference,
                new_identity_id,
            )

        outcome = IdentityResolutionOutcome(
            record_reference=record_reference,
            extracted_identity=extracted,
            decision=decision,
            matched_identity_id=matched_identity_id,
            new_identity_id=new_identity_id,
            candidates=relevant_candidates,
        )
        audit_entry = IdentityAuditEntry(
            entry_id=self._id_factory(),
            timestamp=self._clock(),
            record_reference=record_reference,
            decision=decision,
            candidates_considered=scored,
            chosen_identity_id=matched_identity_id or new_identity_id,
            profile_name=self._profile.name,
            profile_version=self._profile.version,
            rationale=_rationale(decision, scored),
        )
        return outcome, audit_entry, review_item

    def resolve_dataset(
        self, dataset: CleanedLeadDataset, subject_type: SubjectType
    ) -> IdentityResolutionResult:
        """Resolve every record in `dataset` and return one
        IdentityResolutionResult.

        Raises:
            InvalidIdentityResolutionConfigurationError: If the profile
                itself is invalid — raised before any record is processed.
        """

        self._profile.validate()

        started_at = self._clock()
        logger.info(
            "Identity resolution starting: profile='{}', subject_type={}, {} record(s)",
            self._profile.name,
            subject_type.value,
            dataset.record_count,
        )

        start_perf = time.perf_counter()
        outcomes: list[IdentityResolutionOutcome] = []
        audit_trail: list[IdentityAuditEntry] = []
        review_queue: list[ReviewQueueItem] = []
        signals_extracted = 0
        candidates_generated = 0

        for record in dataset.cleaned_records:
            record_reference = f"row:{record.raw_record.row_number}"
            outcome, audit_entry, review_item = self.resolve_record(
                record, subject_type, record_reference
            )
            outcomes.append(outcome)
            audit_trail.append(audit_entry)
            if review_item is not None:
                review_queue.append(review_item)
            signals_extracted += len(outcome.extracted_identity.signals)
            candidates_generated += len(audit_entry.candidates_considered)

        execution_time_total_ms = (time.perf_counter() - start_perf) * 1000
        completed_at = self._clock()

        metrics = IdentityResolutionMetrics(
            records_processed=len(outcomes),
            signals_extracted=signals_extracted,
            candidates_generated=candidates_generated,
            auto_merged=sum(
                1 for o in outcomes if o.decision is ResolutionDecision.AUTO_MERGE
            ),
            sent_to_review=sum(
                1 for o in outcomes if o.decision is ResolutionDecision.CANDIDATE_REVIEW
            ),
            new_identities=sum(
                1 for o in outcomes if o.decision is ResolutionDecision.NEW_IDENTITY
            ),
            execution_time_total_ms=execution_time_total_ms,
        )
        report = IdentityResolutionReport(
            profile_name=self._profile.name,
            profile_version=self._profile.version,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics,
        )

        logger.info(
            "Identity resolution complete: {} auto-merged, {} sent to review, "
            "{} new identities, {:.1f}ms",
            metrics.auto_merged,
            metrics.sent_to_review,
            metrics.new_identities,
            metrics.execution_time_total_ms,
        )

        return IdentityResolutionResult(
            outcomes=tuple(outcomes),
            review_queue=tuple(review_queue),
            audit_trail=tuple(audit_trail),
            report=report,
            metrics=metrics,
        )


def _rationale(decision: ResolutionDecision, scored: tuple[MatchCandidate, ...]) -> str:
    """A one-line, human-readable summary for this record's audit entry."""

    if not scored:
        return (
            "No candidates were generated by any blocking-eligible signal; "
            "treated as a new identity."
        )
    best = max(scored, key=lambda match: match.score.value)
    return (
        f"decision={decision.value}; best_candidate={best.candidate.identity_id} "
        f"({best.score.explanation.reason})"
    )
