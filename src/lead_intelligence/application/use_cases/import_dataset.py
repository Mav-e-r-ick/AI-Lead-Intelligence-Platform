"""The Import Engine's single orchestration point.

WHY THIS FILE EXISTS, AND WHY IT'S SO SHORT:
This class deliberately contains zero source-specific code — no mention of
Excel, openpyxl, or file paths. It depends only on the abstract
SourceReaderPort. That's not an oversight; it's the entire payoff of the
port/adapter design: this exact class, unmodified, will be able to import
from CSV, Google Sheets, or SQL once those adapters exist, because it never
had any Excel-specific knowledge to begin with.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.dto.models import ImportedLeadDataset
from lead_intelligence.application.ports.source_reader_port import SourceReaderPort


class ImportDatasetUseCase:
    """Imports a dataset from any configured SourceReaderPort implementation."""

    def __init__(self, source_reader: SourceReaderPort) -> None:
        """Bind this use case to one already-configured source reader.

        Args:
            source_reader: Any SourceReaderPort implementation (e.g. an
                ExcelSourceReader already pointed at a specific file).
        """

        self._source_reader = source_reader

    def list_available_sheets(self) -> list[str]:
        """Return the sheet/table names available from the configured source."""

        return self._source_reader.list_available_sheets()

    def execute(self, sheet_name: str | None = None) -> ImportedLeadDataset:
        """Import one sheet/table from the configured source.

        Args:
            sheet_name: Optional explicit sheet/table to import. If
                omitted, the adapter selects one automatically.

        Returns:
            The ImportedLeadDataset produced by the source reader,
            unmodified — this use case does not alter records, metadata,
            or warnings in any way.
        """

        logger.info("Import use case starting (sheet={})", sheet_name or "auto")
        dataset = self._source_reader.read(sheet_name=sheet_name)
        logger.info(
            "Import use case finished: {} record(s) from sheet '{}', {} warning(s)",
            dataset.record_count,
            dataset.metadata.sheet_name,
            len(dataset.warnings),
        )
        return dataset
