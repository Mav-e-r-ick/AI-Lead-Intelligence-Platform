"""Custom exceptions describing business-rule violations in plain language."""

from lead_intelligence.domain.exceptions.import_exceptions import (
    CorruptedSourceError,
    EmptySourceError,
    LeadImportError,
    SheetSelectionError,
    SourceNotFoundError,
    UnsupportedSourceFormatError,
)

__all__ = [
    "LeadImportError",
    "SourceNotFoundError",
    "UnsupportedSourceFormatError",
    "CorruptedSourceError",
    "EmptySourceError",
    "SheetSelectionError",
]
