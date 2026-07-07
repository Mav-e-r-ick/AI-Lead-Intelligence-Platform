"""Unit tests for scoring.score_candidate / recompute_confidence.

Uses the default profile's real weights throughout, so these tests double
as living documentation of what the out-of-the-box thresholds actually do:
    duns_number:               STRONG,   weight=1.00, contradiction-sensitive
    email_exact:                MODERATE, weight=0.50, contradiction-sensitive
    company_domain_and_name:    MODERATE, weight=0.45
    company_name_city:          MODERATE, weight=0.35
    full_name:                  WEAK,     weight=0.15
    phone:                      WEAK,     weight=0.12
    auto_merge_threshold=0.90, candidate_review_threshold=0.55,
    contradiction_penalty=0.35, min_independent_signals_without_strong_match=2
"""

from __future__ import annotations

from lead_intelligence.application.dto.identity_resolution_models import (
    ConfidenceBand,
    ExtractedIdentity,
    IdentityRecord,
    IdentitySignal,
    SignalTier,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.config import default_profile
from lead_intelligence.application.identity_resolution.scoring import (
    recompute_confidence,
    score_candidate,
)

PROFILE = default_profile()


def _signal(signal_type: str, value: str, tier: SignalTier) -> IdentitySignal:
    return IdentitySignal(
        signal_type=signal_type, value=value, tier=tier, source_fields=()
    )


def _extracted(*signals: IdentitySignal) -> ExtractedIdentity:
    return ExtractedIdentity(
        subject_type=SubjectType.COMPANY, record_reference="row:1", signals=signals
    )


def _candidate(*signals: IdentitySignal) -> IdentityRecord:
    return IdentityRecord(
        identity_id="cand-1", subject_type=SubjectType.COMPANY, signals=signals
    )


def test_single_strong_match_alone_crosses_auto_merge() -> None:
    duns = _signal("duns_number", "001234567", SignalTier.STRONG)

    score = score_candidate(_extracted(duns), _candidate(duns), PROFILE)

    assert score.band is ConfidenceBand.AUTO_MERGE
    assert score.value == 1.0
    assert len(score.explanation.supporting) == 1


def test_single_weak_signal_alone_is_never_sufficient() -> None:
    name = _signal("full_name", "ada lovelace", SignalTier.WEAK)

    score = score_candidate(_extracted(name), _candidate(name), PROFILE)

    assert score.band is ConfidenceBand.NO_MATCH
    assert score.value == 0.0
    assert "never sufficient" in score.explanation.reason


def test_two_independent_moderate_signals_can_reach_auto_merge_without_a_strong_signal() -> (
    None
):
    email = _signal("email_exact", "exec@acme.com", SignalTier.MODERATE)
    domain = _signal(
        "company_domain_and_name", "acme.com|acme corp", SignalTier.MODERATE
    )

    score = score_candidate(
        _extracted(email, domain), _candidate(email, domain), PROFILE
    )

    assert score.value == 0.95
    assert score.band is ConfidenceBand.AUTO_MERGE


def test_two_independent_weak_signals_corroborate_but_stay_below_review_threshold() -> (
    None
):
    name = _signal("full_name", "ada lovelace", SignalTier.WEAK)
    phone = _signal("phone", "+15551234567", SignalTier.WEAK)

    score = score_candidate(_extracted(name, phone), _candidate(name, phone), PROFILE)

    assert score.value == 0.27
    assert score.band is ConfidenceBand.NO_MATCH
    assert "never sufficient" not in score.explanation.reason


def test_moderate_and_weak_signal_together_land_in_candidate_review_band() -> None:
    email = _signal("email_exact", "exec@acme.com", SignalTier.MODERATE)
    name = _signal("full_name", "ada lovelace", SignalTier.WEAK)

    score = score_candidate(_extracted(email, name), _candidate(email, name), PROFILE)

    assert round(score.value, 2) == 0.65
    assert score.band is ConfidenceBand.CANDIDATE_REVIEW


def test_contradicting_sensitive_signal_downgrades_a_strong_match_to_candidate_review() -> (
    None
):
    duns = _signal("duns_number", "001234567", SignalTier.STRONG)
    incoming_email = _signal("email_exact", "exec@acme.com", SignalTier.MODERATE)
    candidate_email = _signal(
        "email_exact", "someone-else@acme.com", SignalTier.MODERATE
    )

    score = score_candidate(
        _extracted(duns, incoming_email), _candidate(duns, candidate_email), PROFILE
    )

    assert round(score.value, 2) == 0.65
    assert score.band is ConfidenceBand.CANDIDATE_REVIEW
    assert len(score.explanation.contradicting) == 1
    assert score.explanation.contradicting[0].signal_type == "email_exact"


def test_non_contradiction_sensitive_mismatch_is_ignored_not_penalized() -> None:
    duns = _signal("duns_number", "001234567", SignalTier.STRONG)
    incoming_phone = _signal("phone", "+15550000000", SignalTier.WEAK)
    candidate_phone = _signal("phone", "+15559999999", SignalTier.WEAK)

    score = score_candidate(
        _extracted(duns, incoming_phone), _candidate(duns, candidate_phone), PROFILE
    )

    assert score.value == 1.0
    assert score.band is ConfidenceBand.AUTO_MERGE
    assert score.explanation.contradicting == ()


def test_no_overlapping_signal_types_yields_no_match() -> None:
    incoming = _signal("full_name", "ada lovelace", SignalTier.WEAK)
    candidate_only = _signal("phone", "+15550000000", SignalTier.WEAK)

    score = score_candidate(_extracted(incoming), _candidate(candidate_only), PROFILE)

    assert score.band is ConfidenceBand.NO_MATCH
    assert score.explanation.supporting == ()
    assert score.explanation.contradicting == ()


def test_scoring_is_deterministic_across_repeated_calls() -> None:
    email = _signal("email_exact", "exec@acme.com", SignalTier.MODERATE)
    domain = _signal(
        "company_domain_and_name", "acme.com|acme corp", SignalTier.MODERATE
    )
    extracted = _extracted(email, domain)
    candidate = _candidate(email, domain)

    first = score_candidate(extracted, candidate, PROFILE)
    second = score_candidate(extracted, candidate, PROFILE)

    assert first == second


def test_recompute_confidence_is_identical_to_scoring_again() -> None:
    duns = _signal("duns_number", "001234567", SignalTier.STRONG)
    extracted = _extracted(duns)
    candidate = _candidate(duns)

    assert recompute_confidence(extracted, candidate, PROFILE) == score_candidate(
        extracted, candidate, PROFILE
    )


def test_score_never_exceeds_one_even_with_many_supporting_signals() -> None:
    duns = _signal("duns_number", "001234567", SignalTier.STRONG)
    email = _signal("email_exact", "exec@acme.com", SignalTier.MODERATE)
    domain = _signal(
        "company_domain_and_name", "acme.com|acme corp", SignalTier.MODERATE
    )
    city = _signal("company_name_city", "acme corp|springfield", SignalTier.MODERATE)

    score = score_candidate(
        _extracted(duns, email, domain, city),
        _candidate(duns, email, domain, city),
        PROFILE,
    )

    assert score.value == 1.0
