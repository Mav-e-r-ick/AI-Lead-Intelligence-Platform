"""Abstract interfaces (contracts) the application layer depends on.

SourceReaderPort is implemented today by ExcelSourceReader.
NormalizationRule/QualityCheckRule are implemented by every cleaning rule
in application/cleaning/rules/. IdentityCandidatePort and
EnrichmentProviderPort have no concrete implementations yet — tests use
in-memory fakes; real adapters (backed by DigitalTwinRepository/
CompanyRepository, and by each future enrichment source respectively) are
future infrastructure work.
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
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.application.ports.identity_candidate_port import (
    IdentityCandidatePort,
)
from lead_intelligence.application.ports.source_reader_port import SourceReaderPort

__all__ = [
    "SourceReaderPort",
    "NormalizationRule",
    "QualityCheckRule",
    "RuleMetadata",
    "RuleStage",
    "RuleCategory",
    "IdentityCandidatePort",
    "EnrichmentProviderPort",
]
