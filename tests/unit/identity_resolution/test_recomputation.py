"""Unit tests for recomputation.recompute_review_item."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.identity_resolution_models import (
    ConfidenceBand,
    ExtractedIdentity,
    IdentityRecord,
    IdentitySignal,
    MatchCandidate,
    ReviewQueueItem,
    ReviewStatus,
    SignalTier,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.config import default_profile
from lead_intelligence.application.identity_resolution.recomputation import (
    recompute_review_item,
)
from lead_intelligence.application.identity_resolution.scoring import score_candidate

PROFILE = default_profile()


def _signal(signal_type: str, value: str, tier: SignalTier) -> IdentitySignal:
    return IdentitySignal(
        signal_type=signal_type, value=value, tier=tier, source_fields=()
    )


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_recompute_upgrades_a_review_item_to_auto_merge_when_new_evidence_confirms_it() -> (
    None
):
    email_signal = _signal("email_exact", "exec@acme.com", SignalTier.MODERATE)
    city_signal = _signal(
        "company_name_city", "acme corp|springfield", SignalTier.MODERATE
    )
    domain_signal = _signal(
        "company_domain_and_name", "acme.com|acme corp", SignalTier.MODERATE
    )
    candidate_record = IdentityRecord(
        identity_id="twin-1",
        subject_type=SubjectType.COMPANY,
        signals=(email_signal, city_signal, domain_signal),
    )

    # Original evidence only supports two of the candidate's three signals
    # (0.50 + 0.35 = 0.85) — plausible, but below the auto-merge threshold.
    original_extracted = ExtractedIdentity(
        subject_type=SubjectType.COMPANY,
        record_reference="row:1",
        signals=(email_signal, city_signal),
    )
    original_score = score_candidate(original_extracted, candidate_record, PROFILE)
    assert original_score.band is ConfidenceBand.CANDIDATE_REVIEW

    item = ReviewQueueItem(
        item_id="review-1",
        record_reference="row:1",
        extracted_identity=original_extracted,
        candidates=(MatchCandidate(candidate=candidate_record, score=original_score),),
        status=ReviewStatus.OPEN,
        created_at=_fixed_clock(),
    )

    # New evidence arrives: the same record now also carries a matching
    # company_domain_and_name signal, pushing the score over the threshold.
    updated_extracted = ExtractedIdentity(
        subject_type=SubjectType.COMPANY,
        record_reference="row:1",
        signals=(email_signal, city_signal, domain_signal),
    )

    refreshed_item, audit_entry = recompute_review_item(
        item,
        updated_extracted,
        PROFILE,
        id_factory=lambda: "audit-1",
        clock=_fixed_clock,
    )

    assert refreshed_item.candidates[0].score.band is ConfidenceBand.AUTO_MERGE
    assert refreshed_item.extracted_identity == updated_extracted
    assert refreshed_item.item_id == item.item_id
    assert refreshed_item.created_at == item.created_at
    assert audit_entry.entry_id == "audit-1"
    assert audit_entry.timestamp == _fixed_clock()
    assert "candidate_review -> auto_merge" in audit_entry.rationale


def test_recompute_is_idempotent_when_called_again_with_the_same_evidence() -> None:
    duns_signal = _signal("duns_number", "001234567", SignalTier.STRONG)
    candidate_record = IdentityRecord(
        identity_id="twin-1", subject_type=SubjectType.COMPANY, signals=(duns_signal,)
    )
    extracted = ExtractedIdentity(
        subject_type=SubjectType.COMPANY,
        record_reference="row:1",
        signals=(duns_signal,),
    )
    score = score_candidate(extracted, candidate_record, PROFILE)
    item = ReviewQueueItem(
        item_id="review-1",
        record_reference="row:1",
        extracted_identity=extracted,
        candidates=(MatchCandidate(candidate=candidate_record, score=score),),
        status=ReviewStatus.OPEN,
        created_at=_fixed_clock(),
    )

    first_item, _ = recompute_review_item(
        item, extracted, PROFILE, id_factory=lambda: "a", clock=_fixed_clock
    )
    second_item, _ = recompute_review_item(
        item, extracted, PROFILE, id_factory=lambda: "a", clock=_fixed_clock
    )

    assert first_item.candidates == second_item.candidates


def test_recompute_preserves_candidate_count_and_status() -> None:
    signal = _signal("full_name", "ada lovelace", SignalTier.WEAK)
    candidate_record = IdentityRecord(
        identity_id="twin-1", subject_type=SubjectType.PERSON, signals=(signal,)
    )
    extracted = ExtractedIdentity(
        subject_type=SubjectType.PERSON, record_reference="row:1", signals=(signal,)
    )
    score = score_candidate(extracted, candidate_record, PROFILE)
    item = ReviewQueueItem(
        item_id="review-1",
        record_reference="row:1",
        extracted_identity=extracted,
        candidates=(MatchCandidate(candidate=candidate_record, score=score),),
        status=ReviewStatus.OPEN,
        created_at=_fixed_clock(),
    )

    refreshed_item, _ = recompute_review_item(
        item, extracted, PROFILE, id_factory=lambda: "a", clock=_fixed_clock
    )

    assert len(refreshed_item.candidates) == len(item.candidates)
    assert refreshed_item.status is ReviewStatus.OPEN
