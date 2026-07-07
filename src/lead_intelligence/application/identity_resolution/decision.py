"""Aggregates every scored MatchCandidate for one record into a single
ResolutionDecision (RFC §4-6): the engine's actual action.

Kept separate from scoring.py on purpose: scoring answers "how well does
this one candidate match?"; this module answers "given every candidate we
scored, what does the engine actually do?" — different questions, each
independently testable.
"""

from __future__ import annotations

from lead_intelligence.application.dto.identity_resolution_models import (
    ConfidenceBand,
    MatchCandidate,
    ResolutionDecision,
)


def decide(candidates: tuple[MatchCandidate, ...]) -> ResolutionDecision:
    """Choose one decision from every scored candidate for one record.

    - Any candidate scored in the Auto-merge band -> AUTO_MERGE (the
      specific surviving match is chosen deterministically by
      `select_merge_target`).
    - Else, any candidate scored in the Candidate-review band ->
      CANDIDATE_REVIEW (RFC §6: every such candidate is queued for review,
      not just the single best one).
    - Else -> NEW_IDENTITY.
    """

    if any(match.score.band is ConfidenceBand.AUTO_MERGE for match in candidates):
        return ResolutionDecision.AUTO_MERGE
    if any(match.score.band is ConfidenceBand.CANDIDATE_REVIEW for match in candidates):
        return ResolutionDecision.CANDIDATE_REVIEW
    return ResolutionDecision.NEW_IDENTITY


def select_merge_target(candidates: tuple[MatchCandidate, ...]) -> MatchCandidate:
    """Deterministically pick the surviving match among Auto-merge-band
    candidates.

    Ordered by score (highest first), with `identity_id` as a stable
    tiebreaker — never insertion/port order, which this engine makes no
    guarantee is reproducible across runs.

    Raises:
        ValueError: If no candidate is in the Auto-merge band. Callers
            must only invoke this after `decide()` returned AUTO_MERGE.
    """

    auto_merge_candidates = [
        match for match in candidates if match.score.band is ConfidenceBand.AUTO_MERGE
    ]
    if not auto_merge_candidates:
        raise ValueError(
            "select_merge_target() called with no Auto-merge-band candidate; "
            "call decide() first and only proceed on ResolutionDecision.AUTO_MERGE."
        )
    return max(
        auto_merge_candidates,
        key=lambda match: (match.score.value, match.candidate.identity_id),
    )


def review_candidates(
    candidates: tuple[MatchCandidate, ...]
) -> tuple[MatchCandidate, ...]:
    """Every candidate worth a human's attention, most-plausible first,
    with `identity_id` as a stable tiebreaker for equal scores."""

    filtered = [
        match
        for match in candidates
        if match.score.band is ConfidenceBand.CANDIDATE_REVIEW
    ]
    return tuple(
        sorted(
            filtered,
            key=lambda match: (-match.score.value, match.candidate.identity_id),
        )
    )
