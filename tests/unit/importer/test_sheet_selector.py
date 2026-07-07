"""Unit tests for ExcelSheetSelector.

These operate purely on SheetSummary data — no file I/O — since selection
logic is designed to be independently testable from openpyxl entirely.
"""

import pytest

from lead_intelligence.domain.exceptions import SheetSelectionError
from lead_intelligence.infrastructure.importers.excel.sheet_selector import (
    ExcelSheetSelector,
    SheetSummary,
)


def test_explicit_preferred_sheet_is_used_without_warnings() -> None:
    selector = ExcelSheetSelector()
    sheets = [
        SheetSummary(name="Data", row_count=10, column_count=5),
        SheetSummary(name="Notes", row_count=2, column_count=2),
    ]

    chosen, warnings = selector.select(sheets, preferred_sheet="Notes")

    assert chosen == "Notes"
    assert warnings == []


def test_unknown_preferred_sheet_raises() -> None:
    selector = ExcelSheetSelector()
    sheets = [SheetSummary(name="Data", row_count=10, column_count=5)]

    with pytest.raises(SheetSelectionError):
        selector.select(sheets, preferred_sheet="DoesNotExist")


def test_single_sheet_is_selected_automatically_without_warnings() -> None:
    selector = ExcelSheetSelector()
    sheets = [SheetSummary(name="OnlySheet", row_count=3, column_count=4)]

    chosen, warnings = selector.select(sheets)

    assert chosen == "OnlySheet"
    assert warnings == []


def test_one_tabular_candidate_among_metadata_sheets_is_auto_selected_with_warning() -> (
    None
):
    selector = ExcelSheetSelector()
    sheets = [
        SheetSummary(name="Results", row_count=100, column_count=10),
        SheetSummary(name="Details", row_count=13, column_count=2),
    ]

    chosen, warnings = selector.select(sheets)

    assert chosen == "Results"
    assert len(warnings) == 1
    assert warnings[0].code == "SHEET_AUTO_SELECTED"


def test_multiple_tabular_candidates_raises_ambiguous_error() -> None:
    selector = ExcelSheetSelector()
    sheets = [
        SheetSummary(name="January", row_count=50, column_count=6),
        SheetSummary(name="February", row_count=40, column_count=6),
    ]

    with pytest.raises(SheetSelectionError):
        selector.select(sheets)


def test_zero_tabular_candidates_raises_ambiguous_error() -> None:
    selector = ExcelSheetSelector()
    sheets = [
        SheetSummary(name="Details1", row_count=5, column_count=2),
        SheetSummary(name="Details2", row_count=5, column_count=2),
    ]

    with pytest.raises(SheetSelectionError):
        selector.select(sheets)


def test_no_sheets_at_all_raises() -> None:
    selector = ExcelSheetSelector()

    with pytest.raises(SheetSelectionError):
        selector.select([])
