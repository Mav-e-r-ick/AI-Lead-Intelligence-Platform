"""Decides which single worksheet in a workbook to import.

WHY THIS FILE EXISTS:
A workbook can contain more than one sheet, and not every sheet holds
importable lead data — our own reference file has a "Details" sheet that is
just export metadata (2 columns, 13 rows) next to a "Results" sheet with the
real data (59 columns, 2,644 rows). Guessing wrong here would silently try
to import metadata as if it were contacts.

This class makes that one decision, and only that decision. It never opens
a file or touches openpyxl — it works on plain SheetSummary facts handed to
it, which makes it fast to unit-test with fake data and keeps sheet-
selection logic reusable independent of how those facts were computed.

Design principle (see approved architecture): explicit configuration
always wins over guessing. When there's no explicit answer, a narrow,
explainable heuristic may pick a single, unambiguous candidate — but it
always says so via a warning. When even the heuristic can't find exactly
one candidate, this class refuses to guess and raises instead.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from lead_intelligence.application.dto.models import ImportWarning
from lead_intelligence.domain.exceptions import SheetSelectionError


@dataclass(frozen=True)
class SheetSummary:
    """Cheap, pre-computed facts about one worksheet, used only for selection.

    Attributes:
        name: The sheet's name.
        row_count: Number of data rows (header row excluded).
        column_count: Number of columns in the sheet's used range.
    """

    name: str
    row_count: int
    column_count: int


class ExcelSheetSelector:
    """Chooses which worksheet contains the tabular data to import."""

    # A sheet with fewer columns than this looks like a key/value metadata
    # sheet (e.g. "Details": Field | Value, exactly 2 columns) rather than a
    # table of records. Real lead/contact data needs at least a name plus
    # two other attributes to be useful, so 3 is the threshold: it correctly
    # excludes 2-column key/value sheets — a very common export convention
    # for "about this export" metadata — without hardcoding any sheet name.
    MIN_COLUMNS_FOR_TABULAR_DATA = 3

    def select(
        self,
        sheets: list[SheetSummary],
        preferred_sheet: str | None = None,
    ) -> tuple[str, list[ImportWarning]]:
        """Choose one sheet name to import from `sheets`.

        Selection rules, in order:
            1. If `preferred_sheet` is given, it is used as-is — it must
               exist among `sheets`, or this raises SheetSelectionError.
               No heuristics apply once a sheet is explicitly named.
            2. If there is exactly one sheet, it is used.
            3. Otherwise, sheets with fewer than MIN_COLUMNS_FOR_TABULAR_DATA
               columns or zero data rows are excluded as "not a data table."
               If exactly one candidate remains, it is selected and a
               warning is recorded explaining the automatic choice.
            4. If zero or more than one candidate remains, selection is
               genuinely ambiguous: SheetSelectionError is raised rather
               than guessing.

        Args:
            sheets: Summaries of every sheet in the workbook.
            preferred_sheet: An explicit sheet name to use, if the caller
                already knows which one they want.

        Returns:
            A tuple of (selected_sheet_name, warnings_recorded_during_selection).

        Raises:
            SheetSelectionError: If no sheet can be safely determined.
        """

        if not sheets:
            raise SheetSelectionError("The workbook contains no sheets to import.")

        available_names = [sheet.name for sheet in sheets]

        if preferred_sheet is not None:
            if preferred_sheet not in available_names:
                raise SheetSelectionError(
                    f"Requested sheet '{preferred_sheet}' was not found. "
                    f"Available sheets: {available_names}"
                )
            logger.info("Using explicitly requested sheet: '{}'", preferred_sheet)
            return preferred_sheet, []

        if len(sheets) == 1:
            only_sheet = sheets[0].name
            logger.info(
                "Only one sheet present; selected automatically: '{}'", only_sheet
            )
            return only_sheet, []

        candidates = [
            sheet
            for sheet in sheets
            if sheet.column_count >= self.MIN_COLUMNS_FOR_TABULAR_DATA
            and sheet.row_count > 0
        ]

        if len(candidates) == 1:
            chosen = candidates[0].name
            excluded = [name for name in available_names if name != chosen]
            warning = ImportWarning(
                code="SHEET_AUTO_SELECTED",
                message=(
                    f"Multiple sheets found; automatically selected '{chosen}' as the "
                    f"only sheet that looks like tabular data (at least "
                    f"{self.MIN_COLUMNS_FOR_TABULAR_DATA} columns and 1+ data rows). "
                    f"Excluded as non-tabular: {excluded}."
                ),
            )
            logger.warning(warning.message)
            return chosen, [warning]

        raise SheetSelectionError(
            "Could not automatically determine which sheet to import: found "
            f"{len(candidates)} tabular-looking candidate(s) among {available_names}. "
            "Pass an explicit sheet_name to resolve this."
        )
