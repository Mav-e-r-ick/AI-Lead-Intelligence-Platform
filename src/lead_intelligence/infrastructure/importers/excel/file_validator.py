"""Structural validation for Excel source files.

WHY THIS FILE EXISTS:
Before we try to read a single row of data, we need to know the file is
actually safe to open. This class answers exactly one question — "can this
be opened as a valid Excel workbook?" — and nothing else. It never looks at
sheet names, column headers, or cell values; that's ExcelSheetSelector's
and ExcelSourceReader's job. Keeping this check isolated means it can be
tested (and reused, e.g. by a future "pre-flight check this file before
upload" feature) completely independently of row-reading logic.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
from loguru import logger

from lead_intelligence.domain.exceptions import (
    CorruptedSourceError,
    SourceNotFoundError,
    UnsupportedSourceFormatError,
)


class ExcelFileValidator:
    """Confirms a path points to an openable, well-formed .xlsx/.xlsm file."""

    SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm"}

    def validate(self, file_path: Path) -> None:
        """Raise a LeadImportError subclass if file_path is not safely openable.

        Checks are performed in this order, each answering one question:
            1. Does the file exist on disk?          -> SourceNotFoundError
            2. Does it have a supported extension?    -> UnsupportedSourceFormatError
            3. Can it actually be opened as a valid,
               non-corrupted Excel workbook?          -> CorruptedSourceError

        Args:
            file_path: Path to the candidate Excel file.

        Returns:
            None. Success is the absence of a raised exception.
        """

        logger.debug("Validating Excel source file: {}", file_path)

        if not file_path.exists() or not file_path.is_file():
            raise SourceNotFoundError(f"Source file not found: {file_path}")

        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedSourceFormatError(
                f"Unsupported file extension '{file_path.suffix}' for {file_path}. "
                f"Supported extensions: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        # A broad except is deliberate here: this is the one place whose job
        # is to translate *any* failure to open the file (corrupted zip
        # container, missing required XML parts, password protection, etc.)
        # into our own domain vocabulary, so nothing above this layer ever
        # has to know openpyxl exists.
        try:
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            workbook.close()
        except Exception as exc:
            raise CorruptedSourceError(
                f"Could not open '{file_path}' as a valid Excel workbook: {exc}"
            ) from exc

        logger.info("Excel source file passed validation: {}", file_path)
