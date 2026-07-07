"""Data Transfer Objects: plain data shapes passed into/out of use cases."""

from lead_intelligence.application.dto.cleaning_models import (
    CleanedLeadDataset,
    CleanedLeadRecord,
    CleaningMetrics,
    CleaningReport,
    CleaningResult,
    FieldChange,
    QualityWarning,
    QualityWarningDraft,
    RuleExecutionFailure,
    RuleMetrics,
)
from lead_intelligence.application.dto.models import (
    ImportedLeadDataset,
    ImportWarning,
    RawRecord,
    SourceMetadata,
)

__all__ = [
    "RawRecord",
    "SourceMetadata",
    "ImportWarning",
    "ImportedLeadDataset",
    "FieldChange",
    "QualityWarningDraft",
    "QualityWarning",
    "RuleExecutionFailure",
    "CleanedLeadRecord",
    "CleanedLeadDataset",
    "RuleMetrics",
    "CleaningMetrics",
    "CleaningReport",
    "CleaningResult",
]
