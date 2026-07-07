"""Unit tests for ImportDatasetUseCase.

Uses a fake, in-memory SourceReaderPort instead of the real Excel adapter —
this is the direct proof that the use case is source-agnostic, exactly as
the approved architecture intended: it never needs to know an Excel
adapter exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.models import (
    ImportedLeadDataset,
    RawRecord,
    SourceMetadata,
)
from lead_intelligence.application.ports.source_reader_port import SourceReaderPort
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase


class FakeSourceReader(SourceReaderPort):
    """A minimal, in-memory SourceReaderPort stand-in for testing the use case."""

    def __init__(self, dataset: ImportedLeadDataset, sheets: list[str]) -> None:
        self._dataset = dataset
        self._sheets = sheets
        self.requested_sheet_names: list[str | None] = []

    def list_available_sheets(self) -> list[str]:
        return self._sheets

    def read(self, sheet_name: str | None = None) -> ImportedLeadDataset:
        self.requested_sheet_names.append(sheet_name)
        return self._dataset


def _sample_dataset() -> ImportedLeadDataset:
    metadata = SourceMetadata(
        source_path="fake://source",
        source_type="fake",
        sheet_name="Sheet1",
        available_sheets=("Sheet1",),
        column_names=("Name",),
        row_count=1,
        imported_at=datetime.now(timezone.utc),
    )
    record = RawRecord(row_number=2, sheet_name="Sheet1", values={"Name": "Ada"})
    return ImportedLeadDataset(records=(record,), metadata=metadata, warnings=())


def test_execute_returns_the_readers_dataset_unmodified() -> None:
    dataset = _sample_dataset()
    fake_reader = FakeSourceReader(dataset, sheets=["Sheet1"])
    use_case = ImportDatasetUseCase(fake_reader)

    result = use_case.execute()

    assert result is dataset


def test_execute_passes_through_explicit_sheet_name() -> None:
    dataset = _sample_dataset()
    fake_reader = FakeSourceReader(dataset, sheets=["Sheet1"])
    use_case = ImportDatasetUseCase(fake_reader)

    use_case.execute(sheet_name="Sheet1")

    assert fake_reader.requested_sheet_names == ["Sheet1"]


def test_execute_defaults_to_automatic_sheet_selection() -> None:
    dataset = _sample_dataset()
    fake_reader = FakeSourceReader(dataset, sheets=["Sheet1"])
    use_case = ImportDatasetUseCase(fake_reader)

    use_case.execute()

    assert fake_reader.requested_sheet_names == [None]


def test_list_available_sheets_delegates_to_reader() -> None:
    dataset = _sample_dataset()
    fake_reader = FakeSourceReader(dataset, sheets=["Sheet1", "Sheet2"])
    use_case = ImportDatasetUseCase(fake_reader)

    assert use_case.list_available_sheets() == ["Sheet1", "Sheet2"]
