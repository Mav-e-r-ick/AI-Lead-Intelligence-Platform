"""Identity confidence recomputation (RFC §10): confidence is not fixed at
first sight — it is re-evaluated as new evidence arrives, in a strictly
deterministic, replayable way (see scoring.py's docstring for why that
falls out for free from scoring being a pure function).

VERSION 2 SCOPE, EXPLICITLY NOT IMPLEMENTED HERE:
This module recomputes and reports the *new* decision for one review item.
It does not implement identity lineage redirects, merge rollback windows,
or multi-stage lineage graphs — an upgraded decision here still only
produces an IdentityAuditEntry describing the transition; wiring that into
an actual merge/persistence action is future work, once concrete
repositories exist.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from loguru import logger

from lead_intelligence.application.dto.identity_resolution_models import (
    ExtractedIdentity,
    IdentityAuditEntry,
    MatchCandidate,
    ReviewQueueItem,
)
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
)
from lead_intelligence.application.identity_resolution.decision import decide
from lead_intelligence.application.identity_resolution.scoring import (
    recompute_confidence,
)


def recompute_review_item(
    item: ReviewQueueItem,
    updated_extracted: ExtractedIdentity,
    profile: IdentityResolutionProfile,
    id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> tuple[ReviewQueueItem, IdentityAuditEntry]:
    """Re-score every candidate on `item` against `updated_extracted`, and
    return a refreshed ReviewQueueItem plus an audit entry recording the
    transition.

    Args:
        item: A previously generated ReviewQueueItem.
        updated_extracted: The same underlying record's identity, re-
            extracted after new evidence arrived — this may carry more, or
            different, signals than `item.extracted_identity` did; that
            difference is precisely the "new evidence" this function exists
            to react to. Callers are responsible for producing this (e.g.
            by re-running signal_extraction.extract_identity against a
            newly cleaned record).
        profile: The same IdentityResolutionProfile used originally, or a
            deliberately updated one — recomputation is a pure function of
            whatever profile is passed, so a profile change is itself
            replayable evidence.
        id_factory: Generates the new audit entry's id. Override in tests.
        clock: Returns the current UTC time. Override in tests.

    Returns:
        A tuple of (refreshed ReviewQueueItem with rescored candidates, an
        IdentityAuditEntry documenting every candidate's before/after band).
    """

    previous_band_by_id = {
        match.candidate.identity_id: match.score.band for match in item.candidates
    }
    rescored = tuple(
        MatchCandidate(
            candidate=match.candidate,
            score=recompute_confidence(updated_extracted, match.candidate, profile),
        )
        for match in item.candidates
    )
    new_decision = decide(rescored)

    transitions = [
        f"{match.candidate.identity_id}: "
        f"{previous_band_by_id[match.candidate.identity_id].value} -> {match.score.band.value}"
        for match in rescored
    ]
    transitions_desc = "; ".join(transitions) or "no candidates"
    logger.info(
        "Identity confidence recomputed for review item {}: {}",
        item.item_id,
        transitions_desc,
    )

    refreshed_item = ReviewQueueItem(
        item_id=item.item_id,
        record_reference=item.record_reference,
        extracted_identity=updated_extracted,
        candidates=rescored,
        status=item.status,
        created_at=item.created_at,
    )
    audit_entry = IdentityAuditEntry(
        entry_id=id_factory(),
        timestamp=clock(),
        record_reference=item.record_reference,
        decision=new_decision,
        candidates_considered=rescored,
        chosen_identity_id=None,
        profile_name=profile.name,
        profile_version=profile.version,
        rationale=f"Recomputation triggered by new evidence: {transitions_desc}",
    )
    return refreshed_item, audit_entry
