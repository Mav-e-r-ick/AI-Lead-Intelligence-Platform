"""Unit tests for decision.decide / select_merge_target / review_candidates."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.identity_resolution_models import (
    ConfidenceBand,
    ConfidenceScore,
    IdentityRecord,
    MatchCandidate,
    MatchExplanation,
    ResolutionDecision,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.decision import (
    decide,
    review_candidates,
    select_merge_target,
)


def _candidate(identity_id: str, band: ConfidenceBand, value: float) -> MatchCandidate:
    record = IdentityRecord(
        identity_id=identity_id, subject_type=SubjectType.PERSON, signals=()
    )
    score = ConfidenceScore(
        value=value,
        band=band,
        explanation=MatchExplanation(supporting=(), contradicting=(), reason="test"),
    )
    return MatchCandidate(candidate=record, score=score)


def test_decide_returns_new_identity_for_no_candidates() -> None:
    assert decide(()) is ResolutionDecision.NEW_IDENTITY


def test_decide_returns_new_identity_when_every_candidate_is_no_match() -> None:
    candidates = (_candidate("A", ConfidenceBand.NO_MATCH, 0.1),)

    assert decide(candidates) is ResolutionDecision.NEW_IDENTITY


def test_decide_returns_candidate_review_when_any_candidate_is_in_that_band() -> None:
    candidates = (
        _candidate("A", ConfidenceBand.NO_MATCH, 0.1),
        _candidate("B", ConfidenceBand.CANDIDATE_REVIEW, 0.6),
    )

    assert decide(candidates) is ResolutionDecision.CANDIDATE_REVIEW


def test_decide_prefers_auto_merge_over_candidate_review() -> None:
    candidates = (
        _candidate("A", ConfidenceBand.CANDIDATE_REVIEW, 0.6),
        _candidate("B", ConfidenceBand.AUTO_MERGE, 0.95),
    )

    assert decide(candidates) is ResolutionDecision.AUTO_MERGE


def test_select_merge_target_picks_highest_score() -> None:
    candidates = (
        _candidate("A", ConfidenceBand.AUTO_MERGE, 0.91),
        _candidate("B", ConfidenceBand.AUTO_MERGE, 0.99),
    )

    target = select_merge_target(candidates)

    assert target.candidate.identity_id == "B"


def test_select_merge_target_breaks_ties_by_identity_id() -> None:
    candidates = (
        _candidate("Z", ConfidenceBand.AUTO_MERGE, 0.95),
        _candidate("A", ConfidenceBand.AUTO_MERGE, 0.95),
    )

    target = select_merge_target(candidates)

    assert target.candidate.identity_id == "Z"


def test_select_merge_target_raises_without_any_auto_merge_candidate() -> None:
    candidates = (_candidate("A", ConfidenceBand.CANDIDATE_REVIEW, 0.6),)

    with pytest.raises(ValueError):
        select_merge_target(candidates)


def test_review_candidates_filters_and_sorts_by_score_descending() -> None:
    candidates = (
        _candidate("A", ConfidenceBand.CANDIDATE_REVIEW, 0.6),
        _candidate("B", ConfidenceBand.NO_MATCH, 0.1),
        _candidate("C", ConfidenceBand.CANDIDATE_REVIEW, 0.8),
    )

    result = review_candidates(candidates)

    assert [c.candidate.identity_id for c in result] == ["C", "A"]


def test_review_candidates_breaks_ties_by_identity_id() -> None:
    candidates = (
        _candidate("Z", ConfidenceBand.CANDIDATE_REVIEW, 0.7),
        _candidate("A", ConfidenceBand.CANDIDATE_REVIEW, 0.7),
    )

    result = review_candidates(candidates)

    assert [c.candidate.identity_id for c in result] == ["A", "Z"]
