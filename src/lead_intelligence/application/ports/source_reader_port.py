"""The contract every tabular data-source adapter must implement.

WHY THIS FILE EXISTS:
This is the one seam that lets the rest of the application stay completely
unaware of *which* technology a dataset came from. Today only
ExcelSourceReader exists (infrastructure/importers/excel/); later, a
CsvSourceReader, GoogleSheetsSourceReader, or SqlSourceReader can be added
by implementing this same contract — no other code in the application
needs to change, because it only ever talks to a SourceReaderPort, never to
a concrete adapter class.

This is Dependency Inversion in practice: the application layer owns and
defines this interface; infrastructure adapters depend on (implement) it —
never the other way around.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lead_intelligence.application.dto.models import ImportedLeadDataset


class SourceReaderPort(ABC):
    """Abstract contract for reading a tabular data source.

    Implementations are responsible only for *structural* correctness:
    can the source be opened, what sheets/tables does it contain, and can
    its rows be handed back as plain, unmodified records. Implementations
    must not clean, validate content, deduplicate, or otherwise interpret
    the data — see the concrete adapter's own docstring for the exact
    boundary.
    """

    @abstractmethod
    def list_available_sheets(self) -> list[str]:
        """Return the names of every sheet/table this source contains.

        This does not read row data — it's a lightweight structural probe,
        useful for letting a caller choose a sheet/table before committing
        to a full read().

        Raises:
            LeadImportError subclasses (e.g. SourceNotFoundError,
            CorruptedSourceError) if the source cannot be opened at all.
        """

    @abstractmethod
    def read(self, sheet_name: str | None = None) -> ImportedLeadDataset:
        """Read one sheet/table from the source and return it unmodified.

        Args:
            sheet_name: The specific sheet/table to read. If None, the
                adapter selects one automatically and records how/why it
                did so in the returned dataset's warnings.

        Returns:
            An ImportedLeadDataset containing every row as a RawRecord,
            source metadata, and any structural warnings encountered.

        Raises:
            LeadImportError subclasses if the source cannot be opened, the
            requested/selected sheet cannot be determined, or the selected
            sheet contains no data rows.
        """
