"""Unit tests for candidate_generation.generate_candidates."""

from __future__ import annotations

from lead_intelligence.application.dto.identity_resolution_models import (
    ExtractedIdentity,
    IdentityRecord,
    IdentitySignal,
    SignalTier,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.candidate_generation import (
    generate_candidates,
)
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
)
from tests.unit.identity_resolution.fixtures import FakeIdentityCandidatePort


def _signal(
    signal_type: str, value: str, tier: SignalTier = SignalTier.MODERATE
) -> IdentitySignal:
    return IdentitySignal(
        signal_type=signal_type, value=value, tier=tier, source_fields=()
    )


def _record(identity_id: str, *signals: IdentitySignal) -> IdentityRecord:
    return IdentityRecord(
        identity_id=identity_id, subject_type=SubjectType.PERSON, signals=tuple(signals)
    )


def _extracted(*signals: IdentitySignal) -> ExtractedIdentity:
    return ExtractedIdentity(
        subject_type=SubjectType.PERSON, record_reference="row:1", signals=signals
    )


def test_title_signal_never_generates_candidates_alone() -> None:
    profile = IdentityResolutionProfile(name="t")
    title_signal = _signal("title", "ceo", SignalTier.WEAK)
    port = FakeIdentityCandidatePort([_record("A", title_signal)])

    candidates = generate_candidates(_extracted(title_signal), port, profile)

    assert candidates == ()


def test_matching_email_signal_surfaces_candidate() -> None:
    profile = IdentityResolutionProfile(name="t")
    email_signal = _signal("email_exact", "ada@example.com")
    match = _record("A", email_signal)
    port = FakeIdentityCandidatePort([match])

    candidates = generate_candidates(_extracted(email_signal), port, profile)

    assert candidates == (match,)


def test_no_matching_signal_returns_no_candidates() -> None:
    profile = IdentityResolutionProfile(name="t")
    port = FakeIdentityCandidatePort(
        [_record("A", _signal("email_exact", "other@example.com"))]
    )

    candidates = generate_candidates(
        _extracted(_signal("email_exact", "ada@example.com")), port, profile
    )

    assert candidates == ()


def test_candidates_deduplicated_across_multiple_matching_signals() -> None:
    profile = IdentityResolutionProfile(name="t")
    email_signal = _signal("email_exact", "ada@example.com")
    name_signal = _signal("full_name", "ada lovelace", SignalTier.WEAK)
    record = _record("A", email_signal, name_signal)
    port = FakeIdentityCandidatePort([record])

    candidates = generate_candidates(
        _extracted(email_signal, name_signal), port, profile
    )

    assert candidates == (record,)


def test_candidates_capped_and_sorted_deterministically() -> None:
    profile = IdentityResolutionProfile(name="t", max_candidates_considered=2)
    shared_signal = _signal("email_exact", "shared@example.com")
    records = [
        _record("C", shared_signal),
        _record("A", shared_signal),
        _record("B", shared_signal),
    ]
    port = FakeIdentityCandidatePort(records)

    candidates = generate_candidates(_extracted(shared_signal), port, profile)

    assert [c.identity_id for c in candidates] == ["A", "B"]
