"""The complete Cleaning Rule Registry: every CLN-### rule instance.

WHY THIS FILE EXISTS:
ALL_RULES is the single list CleaningPipeline (or a CleaningProfile
builder) needs to run the full registry. Adding rule CLN-069 means adding
one entry to the appropriate category module and appending it here —
nothing else in the Cleaning Engine changes, which is the concrete
Open/Closed guarantee described in application/cleaning/README.md.
"""

from __future__ import annotations

from lead_intelligence.application.cleaning.rules.address import ADDRESS_RULES
from lead_intelligence.application.cleaning.rules.company import COMPANY_RULES
from lead_intelligence.application.cleaning.rules.contact import CONTACT_RULES
from lead_intelligence.application.cleaning.rules.cross_field import CROSS_FIELD_RULES
from lead_intelligence.application.cleaning.rules.financial import FINANCIAL_RULES
from lead_intelligence.application.cleaning.rules.identity import IDENTITY_RULES
from lead_intelligence.application.cleaning.rules.industry import INDUSTRY_RULES
from lead_intelligence.application.cleaning.rules.metadata import METADATA_RULES
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
)

#: Every rule in the platform, in Rule ID order (CLN-001 -> CLN-068).
ALL_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    *IDENTITY_RULES,
    *CONTACT_RULES,
    *COMPANY_RULES,
    *ADDRESS_RULES,
    *FINANCIAL_RULES,
    *INDUSTRY_RULES,
    *METADATA_RULES,
    *CROSS_FIELD_RULES,
)

__all__ = ["ALL_RULES"]
