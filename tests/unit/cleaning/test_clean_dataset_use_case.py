"""Unit tests for CleanDatasetUseCase — a thin wrapper, tested as such."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.cleaning.config import CleaningProfile
from lead_intelligence.application.cleaning.pipeline import CleaningPipeline
from lead_intelligence.application.dto.models import (
    ImportedLeadDataset,
    RawRecord,
    SourceMetadata,
)
from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase


def _dataset() -> ImportedLeadDataset:
    record = RawRecord(row_number=2, sheet_name="Sheet1", values={"Name": "Ada"})
    metadata = SourceMetadata(
        source_path="fake",
        source_type="fake",
        sheet_name="Sheet1",
        available_sheets=("Sheet1",),
        column_names=("Name",),
        row_count=1,
        imported_at=datetime.now(timezone.utc),
    )
    return ImportedLeadDataset(records=(record,), metadata=metadata, warnings=())


def test_execute_returns_a_cleaning_result_from_the_pipeline() -> None:
    profile = CleaningProfile(name="test", field_mapping={"name": "Name"})
    pipeline = CleaningPipeline([], profile)
    use_case = CleanDatasetUseCase(pipeline)

    result = use_case.execute(_dataset())

    assert result.metrics.records_processed == 1
    assert result.report.profile_name == "test"
