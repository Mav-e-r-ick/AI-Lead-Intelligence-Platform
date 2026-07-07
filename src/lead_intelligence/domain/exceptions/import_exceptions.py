"""Source-agnostic error vocabulary for the Import Engine.

WHY THIS FILE EXISTS:
Every source adapter (Excel today; CSV/Google Sheets/SQL later) fails in the
same handful of conceptual ways: the source doesn't exist, it's not a
supported format, it's corrupted, it's empty, or we can't tell which
sheet/table to read. By raising these shared exception types instead of
library-specific ones (e.g. openpyxl's own exceptions), any calling code —
today's use case, or a future API/CLI layer — can handle import failures
without knowing or caring which adapter produced them.

These are domain exceptions, not infrastructure exceptions: they describe
*what went wrong in terms the business understands* ("we don't have this
data"), not *how* a particular library failed internally.
"""


class LeadImportError(Exception):
    """Base class for every error the Import Engine can raise.

    Catch this to handle "something went wrong during import" generically,
    or catch one of the specific subclasses below to handle a particular
    failure differently.
    """


class SourceNotFoundError(LeadImportError):
    """Raised when the configured source (e.g. a file path) does not exist."""


class UnsupportedSourceFormatError(LeadImportError):
    """Raised when the source exists but is not a format this adapter reads.

    Example: an ExcelSourceReader given a ".csv" file.
    """


class CorruptedSourceError(LeadImportError):
    """Raised when the source has the right format but can't actually be
    opened/parsed — e.g. a corrupted .xlsx file, or one that is
    password-protected.
    """


class EmptySourceError(LeadImportError):
    """Raised when the source (or the selected sheet/table within it)
    contains no data rows to import.
    """


class SheetSelectionError(LeadImportError):
    """Raised when the Import Engine cannot determine a single sheet/table
    to read — either the requested one doesn't exist, or automatic
    selection found zero or multiple equally-plausible candidates.
    """
