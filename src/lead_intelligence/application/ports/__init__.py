"""Abstract interfaces (contracts) the application layer depends on.

SourceReaderPort is implemented today by ExcelSourceReader.
NormalizationRule/QualityCheckRule are implemented by every cleaning rule
in application/cleaning/rules/. IdentityCandidatePort, EnrichmentProviderPort,
and VerificationProviderPort (with its EmailVerificationPort/
PhoneVerificationPort specializations) have no concrete implementations
yet — tests use in-memory fakes; real adapters (backed by
DigitalTwinRepository/CompanyRepository, each future enrichment source,
and each future email/phone verification vendor respectively) are future
infrastructure work.
Future ports to be added: LinkedInDataPort, AIMessageGeneratorPort,
EmailSenderPort. Infrastructure code implements these interfaces, which is
what lets a vendor be swapped out without touching any use case.
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
from lead_intelligence.application.ports.search_extraction_port import (
    SearchExtractionPort,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.application.ports.source_reader_port import SourceReaderPort
from lead_intelligence.application.ports.verification_provider_port import (
    EmailVerificationPort,
    PhoneVerificationPort,
    VerificationProviderPort,
)

__all__ = [
    "SourceReaderPort",
    "NormalizationRule",
    "QualityCheckRule",
    "RuleMetadata",
    "RuleStage",
    "RuleCategory",
    "IdentityCandidatePort",
    "EnrichmentProviderPort",
    "SearchProviderPort",
    "SearchExtractionPort",
    "VerificationProviderPort",
    "EmailVerificationPort",
    "PhoneVerificationPort",
]
