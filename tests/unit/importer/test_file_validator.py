"""Unit tests for ExcelFileValidator."""

from pathlib import Path

import pytest

from lead_intelligence.domain.exceptions import (
    CorruptedSourceError,
    SourceNotFoundError,
    UnsupportedSourceFormatError,
)
from lead_intelligence.infrastructure.importers.excel.file_validator import (
    ExcelFileValidator,
)
from tests.fixtures.excel_builder import build_workbook


def test_missing_file_raises_source_not_found(tmp_path: Path) -> None:
    validator = ExcelFileValidator()

    with pytest.raises(SourceNotFoundError):
        validator.validate(tmp_path / "does_not_exist.xlsx")


def test_unsupported_extension_raises_unsupported_format(tmp_path: Path) -> None:
    validator = ExcelFileValidator()
    bad_file = tmp_path / "leads.csv"
    bad_file.write_text("a,b,c")

    with pytest.raises(UnsupportedSourceFormatError):
        validator.validate(bad_file)


def test_corrupted_file_raises_corrupted_source(tmp_path: Path) -> None:
    validator = ExcelFileValidator()
    fake_xlsx = tmp_path / "corrupted.xlsx"
    fake_xlsx.write_bytes(b"this is not a real xlsx file")

    with pytest.raises(CorruptedSourceError):
        validator.validate(fake_xlsx)


def test_valid_workbook_passes_validation(tmp_path: Path) -> None:
    validator = ExcelFileValidator()
    path = build_workbook(tmp_path, {"Sheet1": [["Name"], ["Alice"]]})

    validator.validate(path)  # should not raise
