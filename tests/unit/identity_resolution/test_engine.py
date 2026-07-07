"""End-to-end unit tests for IdentityResolutionEngine, using
FakeIdentityCandidatePort instead of a real (not-yet-built) infrastructure
adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pytest

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.cleaning_models import (
    CleanedLeadDataset,
    CleanedLeadRecord,
)
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityRecord,
    IdentitySignal,
    ResolutionDecision,
    SignalTier,
    SubjectType,
)
from lead_intelligence.application.dto.models import SourceMetadata
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
    default_profile,
)
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.domain.exceptions import (
    InvalidIdentityResolutionConfigurationError,
)
from tests.unit.identity_resolution.fixtures import (
    FakeIdentityCandidatePort,
    make_cleaned_record,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc)


def _id_factory() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def factory() -> str:
        return f"id-{next(counter)}"

    return factory


def _dataset(*records: CleanedLeadRecord) -> CleanedLeadDataset:
    metadata = SourceMetadata(
        source_path="fake",
        source_type="fake",
        sheet_name="Sheet1",
        available_sheets=("Sheet1",),
        column_names=(),
        row_count=len(records),
        imported_at=datetime.now(timezone.utc),
    )
    return CleanedLeadDataset(cleaned_records=tuple(records), source_metadata=metadata)


def test_resolve_record_auto_merges_on_strong_signal_match() -> None:
    duns_signal = IdentitySignal(
        signal_type="duns_number",
        value="001234567",
        tier=SignalTier.STRONG,
        source_fields=(),
    )
    existing = IdentityRecord(
        identity_id="twin-1", subject_type=SubjectType.COMPANY, signals=(duns_signal,)
    )
    port = FakeIdentityCandidatePort([existing])
    engine = IdentityResolutionEngine(
        port, default_profile(), id_factory=_id_factory(), clock=_fixed_clock
    )
    record = make_cleaned_record(
        1, **{fc.DUNS_NUMBER: "001234567", fc.COMPANY_NAME: "Acme"}
    )

    outcome, audit_entry, review_item = engine.resolve_record(
        record, SubjectType.COMPANY, "row:1"
    )

    assert outcome.decision is ResolutionDecision.AUTO_MERGE
    assert outcome.matched_identity_id == "twin-1"
    assert outcome.new_identity_id is None
    assert review_item is None
    assert audit_entry.decision is ResolutionDecision.AUTO_MERGE
    assert audit_entry.chosen_identity_id == "twin-1"
    assert len(audit_entry.candidates_considered) == 1
    assert audit_entry.timestamp == _fixed_clock()


def test_resolve_record_queues_candidate_review_on_moderate_confidence() -> None:
    email_signal = IdentitySignal(
        signal_type="email_exact",
        value="exec@acme.com",
        tier=SignalTier.MODERATE,
        source_fields=(),
    )
    name_signal = IdentitySignal(
        signal_type="full_name",
        value="ada lovelace",
        tier=SignalTier.WEAK,
        source_fields=(),
    )
    existing = IdentityRecord(
        identity_id="twin-2",
        subject_type=SubjectType.PERSON,
        signals=(email_signal, name_signal),
    )
    port = FakeIdentityCandidatePort([existing])
    engine = IdentityResolutionEngine(
        port, default_profile(), id_factory=_id_factory(), clock=_fixed_clock
    )
    record = make_cleaned_record(
        2,
        **{
            fc.PRIMARY_EMAIL: "exec@acme.com",
            fc.FIRST_NAME: "Ada",
            fc.LAST_NAME: "Lovelace",
        },
    )

    outcome, audit_entry, review_item = engine.resolve_record(
        record, SubjectType.PERSON, "row:2"
    )

    assert outcome.decision is ResolutionDecision.CANDIDATE_REVIEW
    assert outcome.matched_identity_id is None
    assert review_item is not None
    assert review_item.record_reference == "row:2"
    assert len(review_item.candidates) == 1
    assert review_item.candidates[0].candidate.identity_id == "twin-2"
    assert audit_entry.decision is ResolutionDecision.CANDIDATE_REVIEW


def test_resolve_record_creates_new_identity_when_no_candidates_found() -> None:
    port = FakeIdentityCandidatePort([])
    engine = IdentityResolutionEngine(
        port, default_profile(), id_factory=_id_factory(), clock=_fixed_clock
    )
    record = make_cleaned_record(3, **{fc.PRIMARY_EMAIL: "new@example.com"})

    outcome, audit_entry, review_item = engine.resolve_record(
        record, SubjectType.PERSON, "row:3"
    )

    assert outcome.decision is ResolutionDecision.NEW_IDENTITY
    assert outcome.new_identity_id == "id-1"
    assert outcome.matched_identity_id is None
    assert review_item is None
    assert audit_entry.chosen_identity_id == "id-1"


def test_resolve_dataset_aggregates_metrics_across_records() -> None:
    duns_signal = IdentitySignal(
        signal_type="duns_number",
        value="001234567",
        tier=SignalTier.STRONG,
        source_fields=(),
    )
    existing = IdentityRecord(
        identity_id="twin-1", subject_type=SubjectType.COMPANY, signals=(duns_signal,)
    )
    port = FakeIdentityCandidatePort([existing])
    engine = IdentityResolutionEngine(
        port, default_profile(), id_factory=_id_factory(), clock=_fixed_clock
    )
    auto_merge_record = make_cleaned_record(
        1, **{fc.DUNS_NUMBER: "001234567", fc.COMPANY_NAME: "Acme"}
    )
    new_identity_record = make_cleaned_record(
        2, **{fc.COMPANY_NAME: "Totally Different Co"}
    )
    dataset = _dataset(auto_merge_record, new_identity_record)

    result = engine.resolve_dataset(dataset, SubjectType.COMPANY)

    assert result.metrics.records_processed == 2
    assert result.metrics.auto_merged == 1
    assert result.metrics.new_identities == 1
    assert result.metrics.sent_to_review == 0
    assert len(result.audit_trail) == 2
    assert result.report.profile_name == "default"
    assert result.report.duration_ms >= 0.0


def test_resolve_dataset_raises_before_processing_any_record_when_profile_invalid() -> (
    None
):
    invalid_profile = IdentityResolutionProfile(name="broken", signal_definitions={})
    port = FakeIdentityCandidatePort([])
    engine = IdentityResolutionEngine(port, invalid_profile)
    dataset = _dataset(make_cleaned_record(1, **{fc.COMPANY_NAME: "Acme"}))

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        engine.resolve_dataset(dataset, SubjectType.COMPANY)


def test_engine_is_deterministic_given_the_same_inputs_and_injected_dependencies() -> (
    None
):
    duns_signal = IdentitySignal(
        signal_type="duns_number",
        value="001234567",
        tier=SignalTier.STRONG,
        source_fields=(),
    )
    existing = IdentityRecord(
        identity_id="twin-1", subject_type=SubjectType.COMPANY, signals=(duns_signal,)
    )
    record = make_cleaned_record(
        1, **{fc.DUNS_NUMBER: "001234567", fc.COMPANY_NAME: "Acme"}
    )

    engine_a = IdentityResolutionEngine(
        FakeIdentityCandidatePort([existing]),
        default_profile(),
        id_factory=_id_factory(),
        clock=_fixed_clock,
    )
    engine_b = IdentityResolutionEngine(
        FakeIdentityCandidatePort([existing]),
        default_profile(),
        id_factory=_id_factory(),
        clock=_fixed_clock,
    )

    outcome_a, audit_a, _ = engine_a.resolve_record(
        record, SubjectType.COMPANY, "row:1"
    )
    outcome_b, audit_b, _ = engine_b.resolve_record(
        record, SubjectType.COMPANY, "row:1"
    )

    assert outcome_a == outcome_b
    assert audit_a == audit_b
