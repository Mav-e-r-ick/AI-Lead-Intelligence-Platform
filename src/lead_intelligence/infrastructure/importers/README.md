# Import Engine

The Import Engine turns an external data source (an Excel file today; CSV,
Google Sheets, and SQL later) into plain, unmodified records the rest of
the platform can work with. This document explains how its pieces fit
together — see `docs/ARCHITECTURE.md` (project root) for the broader
Clean Architecture reasoning behind the split.

## Scope: what this module does and does not do

**Does:**
- Confirm a source can actually be opened (exists, right format, not corrupted).
- Discover what sheets/tables a source contains.
- Choose which one to import (explicitly, or via a narrow, explainable heuristic).
- Read every row and every column exactly as stored — no dropped columns,
  no coerced types, no renamed headers.
- Report structural facts (row/column counts, skipped blank rows, blank or
  duplicate headers) as **warnings** — observations, not judgments.

**Does not:**
- Clean, standardize, or "fix" any value.
- Validate whether an email, phone number, or any other value is correct.
- Deduplicate records.
- Write to a database.
- Know what a "Lead" is — its output is `RawRecord`s, not business entities.

Those are all future stages, built on top of this module's output, never inside it.

## The classes, and how they talk to each other

```
ImportDatasetUseCase                    (application/use_cases/import_dataset.py)
        |
        | depends only on the abstract port — never on ExcelSourceReader directly
        v
SourceReaderPort                        (application/ports/source_reader_port.py)
        ^
        | implements
        |
ExcelSourceReader                       (infrastructure/importers/excel/excel_reader.py)
        |
        |-- uses --> ExcelFileValidator  (file_validator.py)  "can this file be opened?"
        |-- uses --> ExcelSheetSelector  (sheet_selector.py)  "which sheet do we read?"
        |
        v
ImportedLeadDataset                     (application/dto/models.py)
  = records: tuple[RawRecord, ...]
  + metadata: SourceMetadata
  + warnings: tuple[ImportWarning, ...]
```

**Call sequence for one import:**
1. Caller builds an `ExcelSourceReader(file_path)` and wraps it in an `ImportDatasetUseCase`.
2. `use_case.execute()` calls `reader.read()`.
3. The reader calls `ExcelFileValidator.validate()` first — this raises a
   `LeadImportError` subclass (see below) and stops everything if the file
   can't be opened at all.
4. The reader opens the workbook itself, computes a cheap `SheetSummary`
   (row/column counts) per sheet, and calls `ExcelSheetSelector.select()` —
   a pure function with no file I/O — to decide which sheet to read.
5. The reader reads that sheet's header and data rows, building one
   `RawRecord` per row and an `ImportWarning` for every structural
   observation (blank row skipped, blank/duplicate header, etc.).
6. The reader assembles a `SourceMetadata` and returns one
   `ImportedLeadDataset` — this is the module's only output shape.

Every arrow above points toward an abstraction (`SourceReaderPort`,
`ImportedLeadDataset`), never toward a concrete Excel detail — that's what
lets a future `CsvSourceReader` or `SqlSourceReader` slot in as a sibling
of `ExcelSourceReader`, implementing the same port, with
`ImportDatasetUseCase` unchanged.

## Errors vs. warnings

- **`domain/exceptions/import_exceptions.py`** defines the errors that stop
  an import: `SourceNotFoundError`, `UnsupportedSourceFormatError`,
  `CorruptedSourceError`, `EmptySourceError`, `SheetSelectionError` — all
  subclasses of `LeadImportError`.
- **`ImportWarning`** (in `models.py`) is for everything that's worth
  knowing but doesn't stop the import: an auto-selected sheet, a skipped
  blank row, a blank or duplicate column header.

## Known, deliberate limitation: duplicate column headers

If a sheet has two columns with the exact same header text, `RawRecord.values`
(a `dict`) cannot hold two values under one key. Rather than invent a
suffix (which would violate "don't rename columns"), the last occurrence's
value wins per row, and a `DUPLICATE_COLUMN_HEADER` warning is raised. The
complete, literal header list — duplicates included — is still preserved,
unmodified, in `SourceMetadata.column_names`, so nothing is silently lost;
it's a named, auditable trade-off rather than a hidden one.

## Why `openpyxl` directly, never `pandas`

Profiling the reference dataset found that `pandas.read_excel` silently
stripped leading zeros from a text-stored identifier column (D-U-N-S
numbers), because pandas performs its own column-wide type inference on
top of whatever's in the file. `openpyxl`, read cell-by-cell, returns
exactly the type Excel itself recorded for that cell — no extra inference
layer. `excel_reader.py` never converts a cell's value; it only uses
whatever native type `openpyxl` already determined. That one rule is the
entire mechanism behind "preserve identifiers as strings" and "preserve
leading zeros" — it isn't special-cased to any one column or file.

## Usage

```
reader = ExcelSourceReader("path/to/file.xlsx")
use_case = ImportDatasetUseCase(reader)

sheets = use_case.list_available_sheets()      # e.g. ["Results", "Details"]
dataset = use_case.execute()                    # auto-selects a sheet
# or: dataset = use_case.execute(sheet_name="Results")

dataset.record_count       # number of rows imported
dataset.metadata           # source_path, sheet_name, column_names, ...
dataset.warnings           # structural observations, if any
dataset.records[0].values  # {"First Name": "Ada", "D-U-N-S® Number": "036611498", ...}
```

## Files in this module

| File | Responsibility |
|---|---|
| `application/ports/source_reader_port.py` | The `SourceReaderPort` contract every adapter implements. |
| `application/dto/models.py` | Shared, immutable output shapes: `RawRecord`, `SourceMetadata`, `ImportWarning`, `ImportedLeadDataset`. |
| `application/use_cases/import_dataset.py` | `ImportDatasetUseCase` — thin, source-agnostic orchestration. |
| `domain/exceptions/import_exceptions.py` | The shared error vocabulary raised by any adapter. |
| `infrastructure/importers/excel/file_validator.py` | `ExcelFileValidator` — "can this file be opened?" only. |
| `infrastructure/importers/excel/sheet_selector.py` | `ExcelSheetSelector` — pure sheet-choice logic, no I/O. |
| `infrastructure/importers/excel/excel_reader.py` | `ExcelSourceReader` — the actual `openpyxl` I/O and row-building. |

Tests: `tests/unit/importer/`, using synthetic fixtures built by
`tests/fixtures/excel_builder.py` (never the real, gitignored sample file).
