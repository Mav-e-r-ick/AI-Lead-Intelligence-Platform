"""Plain data shapes passed between the Import Engine's classes.

WHY THIS FILE EXISTS:
Every class in the Import Engine — the port, the Excel adapter, and (later)
CSV/Google Sheets/SQL adapters — needs to agree on exactly what "the result
of an import" looks like. These four classes are that shared agreement.

They intentionally contain **no behavior** beyond simple, structural
convenience (e.g. a length) and **no interpretation** of what the data
means — a RawRecord doesn't know what a "Lead" is; it's just "row 42 of
sheet X contained these column-name -> value pairs." Turning raw records
into business entities (domain/entities/) is explicitly a future task, not
this one.

All four are immutable (frozen dataclasses, tuple fields instead of lists)
on purpose: once the Import Engine hands back an ImportedLeadDataset, no
downstream code should be able to silently mutate it — any change to the
data must happen in a deliberate, later, separately-reviewable stage
(cleaning), never by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class RawRecord:
    """One row of source data, exactly as read — no cleaning, no renaming.

    Attributes:
        row_number: The 1-based row number in the source sheet/table,
            counting the header as row 1. Kept for traceability: if a value
            looks wrong later, this is how you find it in the original file.
        sheet_name: The sheet/table this row came from.
        values: Original column name -> original cell value. Keys are the
            literal column headers from the source (unrenamed). Values keep
            whatever native type the source library returned (str, int,
            float, bool, datetime, or None for an empty cell) — the Import
            Engine never coerces a value to a different type.
    """

    row_number: int
    sheet_name: str
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Wrap in MappingProxyType so `values` is genuinely read-only, not
        # just a plain dict that happens to be reachable from a frozen
        # dataclass (frozen only stops attribute *reassignment*, not
        # in-place dict mutation).
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True)
class SourceMetadata:
    """Facts about where an ImportedLeadDataset came from.

    Attributes:
        source_path: Where the source was read from (e.g. a file path).
        source_type: Which kind of adapter produced this data (e.g. "excel").
        sheet_name: The sheet/table that was actually read.
        available_sheets: Every sheet/table name the source contained,
            whether or not it was the one selected.
        column_names: The original, unmodified column headers, in their
            original order — including duplicates, if any existed.
        row_count: Number of data rows returned (blank/skipped rows excluded;
            see warnings for what was skipped and why).
        imported_at: UTC timestamp of when this import ran.
    """

    source_path: str
    source_type: str
    sheet_name: str
    available_sheets: tuple[str, ...]
    column_names: tuple[str, ...]
    row_count: int
    imported_at: datetime


@dataclass(frozen=True)
class ImportWarning:
    """A non-fatal structural observation made while importing.

    Warnings describe facts about the *shape* of the source (a blank row
    was skipped, a column header was missing, two columns share a name) —
    never judgments about data *quality* (that's a future cleaning stage's
    job). Import continues after a warning; it only stops on a
    LeadImportError.

    Attributes:
        code: A short, machine-readable identifier (e.g. "SKIPPED_BLANK_ROW"),
            useful for filtering/counting warnings programmatically.
        message: A human-readable explanation.
        row_number: The row this warning relates to, if any.
        column_name: The column this warning relates to, if any.
    """

    code: str
    message: str
    row_number: int | None = None
    column_name: str | None = None


@dataclass(frozen=True)
class ImportedLeadDataset:
    """The complete, unmodified result of one Import Engine run.

    Attributes:
        records: Every imported row, as RawRecord objects.
        metadata: Facts about the source this data came from.
        warnings: Structural observations raised during import.
    """

    records: tuple[RawRecord, ...]
    metadata: SourceMetadata
    warnings: tuple[ImportWarning, ...]

    @property
    def record_count(self) -> int:
        """Number of records in this dataset (convenience for len(records))."""

        return len(self.records)
