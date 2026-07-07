"""Confidence scoring (RFC §3): given one ExtractedIdentity and one
IdentityRecord candidate, compute an explainable match ConfidenceScore.

WHY THIS IS A PURE FUNCTION OF ITS ARGUMENTS:
Determinism and replayability (RFC §3, §10) both fall out for free if
scoring depends on nothing but `extracted`, `candidate`, and `profile`: the
same triple always produces the same score. That is also exactly what
makes confidence *recomputation* (RFC §10) trivial rather than a second
algorithm — see `recompute_confidence` at the bottom of this file.
"""

from __future__ import annotations

from lead_intelligence.application.dto.identity_resolution_models import (
    ConfidenceBand,
    ConfidenceScore,
    ExtractedIdentity,
    IdentityRecord,
    MatchExplanation,
    SignalMatch,
    SignalTier,
)
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
)


def score_candidate(
    extracted: ExtractedIdentity,
    candidate: IdentityRecord,
    profile: IdentityResolutionProfile,
) -> ConfidenceScore:
    """Score how likely `extracted` and `candidate` are the same Subject.

    Algorithm (deterministic, no randomness, no external calls):
    1. For every incoming signal that has a same-type signal on the
       candidate: an equal value is `supporting`; a different value is
       `contradicting` *only* if that signal type is contradiction-
       sensitive (RFC §2) — anything else that merely wasn't observed on
       one side is neither support nor contradiction.
    2. RFC §2's hard rule — "a single weak signal is never sufficient" —
       is enforced structurally, not by tuning weights so it merely tends
       to work out: with no Strong-tier support, at least
       `profile.min_independent_signals_without_strong_match` distinct
       signal types must support the match, or the score is forced to
       0.0/NO_MATCH regardless of how large the raw weighted sum would
       otherwise be.
    3. Otherwise, the score is the sum of supporting weights minus the
       configured penalty per contradiction, clamped to [0.0, 1.0], then
       banded against the profile's two thresholds.

    Every supporting and contradicting signal considered is retained in
    the returned MatchExplanation — nothing here is a "black box" number.
    """

    candidate_by_type = {signal.signal_type: signal for signal in candidate.signals}

    supporting: list[SignalMatch] = []
    contradicting: list[SignalMatch] = []

    for incoming in extracted.signals:
        candidate_signal = candidate_by_type.get(incoming.signal_type)
        if candidate_signal is None:
            continue
        definition = profile.definition_for(incoming.signal_type)
        if candidate_signal.value == incoming.value:
            supporting.append(
                SignalMatch(
                    signal_type=incoming.signal_type,
                    tier=incoming.tier,
                    incoming_value=incoming.value,
                    candidate_value=candidate_signal.value,
                    contribution=definition.weight,
                )
            )
        elif definition.contradiction_sensitive:
            contradicting.append(
                SignalMatch(
                    signal_type=incoming.signal_type,
                    tier=incoming.tier,
                    incoming_value=incoming.value,
                    candidate_value=candidate_signal.value,
                    contribution=-profile.contradiction_penalty,
                )
            )

    has_strong_match = any(match.tier is SignalTier.STRONG for match in supporting)
    independent_signal_types = {match.signal_type for match in supporting}

    if (
        not has_strong_match
        and len(independent_signal_types)
        < profile.min_independent_signals_without_strong_match
    ):
        reason = (
            "No Strong-tier signal matched, and fewer than "
            f"{profile.min_independent_signals_without_strong_match} independent "
            "corroborating signal type(s) were found "
            f"({sorted(independent_signal_types) or 'none'}) — a single weak or "
            "moderate signal is never sufficient on its own."
        )
        return ConfidenceScore(
            value=0.0,
            band=ConfidenceBand.NO_MATCH,
            explanation=MatchExplanation(
                supporting=tuple(supporting),
                contradicting=tuple(contradicting),
                reason=reason,
            ),
        )

    raw_score = sum(match.contribution for match in supporting) + sum(
        match.contribution for match in contradicting
    )
    value = max(0.0, min(1.0, raw_score))

    if value >= profile.auto_merge_threshold:
        band = ConfidenceBand.AUTO_MERGE
    elif value >= profile.candidate_review_threshold:
        band = ConfidenceBand.CANDIDATE_REVIEW
    else:
        band = ConfidenceBand.NO_MATCH

    reason = _describe(supporting, contradicting, value, band)
    return ConfidenceScore(
        value=value,
        band=band,
        explanation=MatchExplanation(
            supporting=tuple(supporting),
            contradicting=tuple(contradicting),
            reason=reason,
        ),
    )


def _describe(
    supporting: list[SignalMatch],
    contradicting: list[SignalMatch],
    value: float,
    band: ConfidenceBand,
) -> str:
    supporting_desc = ", ".join(match.signal_type for match in supporting) or "none"
    contradicting_desc = (
        ", ".join(match.signal_type for match in contradicting) or "none"
    )
    return (
        f"score={value:.3f} -> {band.value}; supporting=[{supporting_desc}]; "
        f"contradicting=[{contradicting_desc}]"
    )


def recompute_confidence(
    extracted: ExtractedIdentity,
    candidate: IdentityRecord,
    profile: IdentityResolutionProfile,
) -> ConfidenceScore:
    """Recompute a match score from current evidence (RFC §10).

    Deliberately just `score_candidate` again: because scoring is a pure
    function of its inputs, "recomputing" a score means calling it again
    with the latest `extracted`/`candidate` state — the same call, at a
    later time, with updated evidence, produces a directly comparable
    result (same units, same bands), which is what lets a caller detect a
    band transition (e.g. CANDIDATE_REVIEW -> AUTO_MERGE) by simply
    diffing two ConfidenceScore values. See recomputation.py for that
    comparison.
    """

    return score_candidate(extracted, candidate, profile)
