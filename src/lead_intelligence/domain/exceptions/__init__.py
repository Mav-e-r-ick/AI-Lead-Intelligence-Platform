"""Custom exceptions describing business-rule violations in plain language."""

from lead_intelligence.domain.exceptions.cleaning_exceptions import (
    InvalidCleaningConfigurationError,
    LeadCleaningError,
    RuleExecutionError,
)
from lead_intelligence.domain.exceptions.enrichment_exceptions import (
    DuplicateProviderError,
    InvalidEnrichmentConfigurationError,
    LeadEnrichmentError,
)
from lead_intelligence.domain.exceptions.identity_resolution_exceptions import (
    InvalidIdentityResolutionConfigurationError,
    LeadIdentityResolutionError,
)
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
    "LeadCleaningError",
    "InvalidCleaningConfigurationError",
    "RuleExecutionError",
    "LeadIdentityResolutionError",
    "InvalidIdentityResolutionConfigurationError",
    "LeadEnrichmentError",
    "InvalidEnrichmentConfigurationError",
    "DuplicateProviderError",
]
