"""Abstract interfaces (contracts) the application layer depends on.

SourceReaderPort is implemented today by ExcelSourceReader.
NormalizationRule/QualityCheckRule are implemented by every cleaning rule
in application/cleaning/rules/.
Future ports to be added: EmailVerifierPort, PhoneVerifierPort,
LinkedInDataPort, AIMessageGeneratorPort, EmailSenderPort. Infrastructure
code implements these interfaces, which is what lets a vendor be swapped
out without touching any use case.
"""

from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)
from lead_intelligence.application.ports.source_reader_port import SourceReaderPort

__all__ = [
    "SourceReaderPort",
    "NormalizationRule",
    "QualityCheckRule",
    "RuleMetadata",
    "RuleStage",
    "RuleCategory",
]
