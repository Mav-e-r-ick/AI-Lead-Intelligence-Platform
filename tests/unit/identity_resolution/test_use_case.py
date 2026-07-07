"""Unit tests for ResolveIdentityUseCase — a thin wrapper, tested as such."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.cleaning_models import CleanedLeadDataset
from lead_intelligence.application.dto.identity_resolution_models import SubjectType
from lead_intelligence.application.dto.models import SourceMetadata
from lead_intelligence.application.identity_resolution.config import default_profile
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.application.use_cases.resolve_identity import (
    ResolveIdentityUseCase,
)
from tests.unit.identity_resolution.fixtures import (
    FakeIdentityCandidatePort,
    make_cleaned_record,
)


def _dataset() -> CleanedLeadDataset:
    record = make_cleaned_record(1, **{fc.COMPANY_NAME: "Acme"})
    metadata = SourceMetadata(
        source_path="fake",
        source_type="fake",
        sheet_name="Sheet1",
        available_sheets=("Sheet1",),
        column_names=(),
        row_count=1,
        imported_at=datetime.now(timezone.utc),
    )
    return CleanedLeadDataset(cleaned_records=(record,), source_metadata=metadata)


def test_execute_returns_an_identity_resolution_result_from_the_engine() -> None:
    engine = IdentityResolutionEngine(FakeIdentityCandidatePort([]), default_profile())
    use_case = ResolveIdentityUseCase(engine)

    result = use_case.execute(_dataset(), SubjectType.COMPANY)

    assert result.metrics.records_processed == 1
    assert result.metrics.new_identities == 1
    assert result.report.profile_name == "default"
