"""Unit tests for ExcelSourceReader.

Uses small, synthetic in-memory workbooks built via
tests/fixtures/excel_builder.py — never the real (gitignored) sample
dataset — so these tests are fast, deterministic, and runnable anywhere.
"""

from pathlib import Path

import pytest

from lead_intelligence.domain.exceptions import EmptySourceError, SourceNotFoundError
from lead_intelligence.infrastructure.importers.excel.excel_reader import (
    ExcelSourceReader,
)
from tests.fixtures.excel_builder import build_workbook


def test_read_preserves_columns_values_and_row_numbers(tmp_path: Path) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Leads": [
                ["First Name", "Last Name", "Email"],
                ["Ada", "Lovelace", "ada@example.com"],
                ["Grace", "Hopper", "grace@example.com"],
            ]
        },
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    assert dataset.metadata.sheet_name == "Leads"
    assert dataset.metadata.column_names == ("First Name", "Last Name", "Email")
    assert dataset.record_count == 2
    assert dataset.records[0].row_number == 2
    assert dataset.records[0].values["First Name"] == "Ada"
    assert dataset.records[1].values["Email"] == "grace@example.com"
    assert dataset.warnings == ()


def test_read_preserves_leading_zeros_on_text_identifier_columns(
    tmp_path: Path,
) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Leads": [
                ["Name", "D-U-N-S Number"],
                ["Ada", "036611498"],  # Python str -> stored as Excel text
            ]
        },
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    duns = dataset.records[0].values["D-U-N-S Number"]
    assert duns == "036611498"
    assert isinstance(duns, str)


def test_read_preserves_special_characters_in_column_names(tmp_path: Path) -> None:
    path = build_workbook(
        tmp_path,
        {"Leads": [["Name", "D-U-N-S® Number"], ["Ada", "036611498"]]},
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    assert "D-U-N-S® Number" in dataset.metadata.column_names
    assert dataset.records[0].values["D-U-N-S® Number"] == "036611498"


def test_read_auto_selects_data_sheet_and_skips_metadata_sheet(tmp_path: Path) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Results": [
                ["Name", "Email", "Title"],
                ["Ada", "ada@example.com", "CEO"],
            ],
            "Details": [
                ["Field", "Value"],
                ["Country", "United States"],
            ],
        },
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    assert dataset.metadata.sheet_name == "Results"
    assert dataset.metadata.available_sheets == ("Results", "Details")
    assert any(w.code == "SHEET_AUTO_SELECTED" for w in dataset.warnings)


def test_read_skips_fully_blank_rows_and_warns(tmp_path: Path) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Leads": [
                ["Name", "Email"],
                ["Ada", "ada@example.com"],
                [None, None],
                ["Grace", "grace@example.com"],
            ]
        },
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    assert dataset.record_count == 2
    assert any(w.code == "SKIPPED_BLANK_ROW" for w in dataset.warnings)
    # Row numbers reflect original position; the blank row is not renumbered away.
    assert [record.row_number for record in dataset.records] == [2, 4]


def test_read_handles_blank_column_header_with_placeholder_and_warning(
    tmp_path: Path,
) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Leads": [
                ["Name", None, "Email"],
                ["Ada", "extra-value", "ada@example.com"],
            ]
        },
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    assert "Unnamed: 2" in dataset.metadata.column_names
    assert dataset.records[0].values["Unnamed: 2"] == "extra-value"
    assert any(w.code == "BLANK_COLUMN_HEADER" for w in dataset.warnings)


def test_read_handles_duplicate_column_headers_with_warning(tmp_path: Path) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Leads": [
                ["Email", "Email"],
                ["first@example.com", "second@example.com"],
            ]
        },
    )
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    # The full, literal header (duplicates included) is preserved in metadata.
    assert dataset.metadata.column_names == ("Email", "Email")
    # A dict-keyed row can only keep one value per duplicate name; documented
    # in excel_reader.py's _build_header docstring as a known limitation.
    assert dataset.records[0].values["Email"] == "second@example.com"
    assert any(w.code == "DUPLICATE_COLUMN_HEADER" for w in dataset.warnings)


def test_read_raises_empty_source_error_when_sheet_has_no_data_rows(
    tmp_path: Path,
) -> None:
    path = build_workbook(tmp_path, {"Leads": [["Name", "Email"]]})
    reader = ExcelSourceReader(path)

    with pytest.raises(EmptySourceError):
        reader.read()


def test_read_raises_source_not_found_for_missing_file(tmp_path: Path) -> None:
    reader = ExcelSourceReader(tmp_path / "missing.xlsx")

    with pytest.raises(SourceNotFoundError):
        reader.read()


def test_list_available_sheets_returns_all_sheet_names(tmp_path: Path) -> None:
    path = build_workbook(
        tmp_path,
        {
            "Results": [["Name"], ["Ada"]],
            "Details": [["Field", "Value"], ["Country", "US"]],
        },
    )
    reader = ExcelSourceReader(path)

    assert reader.list_available_sheets() == ["Results", "Details"]


def test_raw_record_values_are_immutable(tmp_path: Path) -> None:
    path = build_workbook(tmp_path, {"Leads": [["Name"], ["Ada"]]})
    reader = ExcelSourceReader(path)

    dataset = reader.read()

    with pytest.raises(TypeError):
        dataset.records[0].values["Name"] = "Changed"
