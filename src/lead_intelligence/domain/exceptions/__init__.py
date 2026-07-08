"""Custom exceptions describing business-rule violations in plain language."""

from lead_intelligence.domain.exceptions.cleaning_exceptions import (
    InvalidCleaningConfigurationError,
    LeadCleaningError,
    RuleExecutionError,
)
from lead_intelligence.domain.exceptions.comparison_exceptions import (
    InvalidComparisonConfigurationError,
    LeadComparisonError,
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
from lead_intelligence.domain.exceptions.inflection_exceptions import (
    DuplicateInflectionRuleError,
    InvalidInflectionConfigurationError,
    LeadInflectionError,
)
from lead_intelligence.domain.exceptions.search_exceptions import (
    DuplicateSearchProviderError,
    InvalidSearchConfigurationError,
    LeadSearchError,
)
from lead_intelligence.domain.exceptions.verification_exceptions import (
    DuplicateVerificationProviderError,
    InvalidVerificationConfigurationError,
    LeadVerificationError,
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
    "LeadComparisonError",
    "InvalidComparisonConfigurationError",
    "LeadInflectionError",
    "InvalidInflectionConfigurationError",
    "DuplicateInflectionRuleError",
    "LeadVerificationError",
    "InvalidVerificationConfigurationError",
    "DuplicateVerificationProviderError",
    "LeadSearchError",
    "InvalidSearchConfigurationError",
    "DuplicateSearchProviderError",
]
