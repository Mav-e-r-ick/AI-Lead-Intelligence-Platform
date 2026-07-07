"""Unit tests for the Import Engine's shared DTOs (application/dto/models.py)."""

from datetime import datetime, timezone

import pytest

from lead_intelligence.application.dto.models import (
    ImportedLeadDataset,
    ImportWarning,
    RawRecord,
    SourceMetadata,
)


def test_raw_record_values_cannot_be_mutated_after_construction() -> None:
    record = RawRecord(row_number=2, sheet_name="Sheet1", values={"Name": "Ada"})

    with pytest.raises(TypeError):
        record.values["Name"] = "Changed"


def test_imported_lead_dataset_record_count_matches_records_length() -> None:
    metadata = SourceMetadata(
        source_path="x",
        source_type="excel",
        sheet_name="Sheet1",
        available_sheets=("Sheet1",),
        column_names=("Name",),
        row_count=2,
        imported_at=datetime.now(timezone.utc),
    )
    records = (
        RawRecord(row_number=2, sheet_name="Sheet1", values={"Name": "Ada"}),
        RawRecord(row_number=3, sheet_name="Sheet1", values={"Name": "Grace"}),
    )

    dataset = ImportedLeadDataset(records=records, metadata=metadata, warnings=())

    assert dataset.record_count == 2


def test_import_warning_optional_fields_default_to_none() -> None:
    warning = ImportWarning(code="SOME_CODE", message="Something happened.")

    assert warning.row_number is None
    assert warning.column_name is None
