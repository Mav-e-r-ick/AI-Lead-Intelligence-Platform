"""Industry category rules: CLN-051 through CLN-055.

See docs/CLEANING_RULES.md §9.6 for the full specification each rule below
implements.
"""

from __future__ import annotations

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.reference_data.industry_codes import (
    KNOWN_CLASSIFICATION_CODES,
)
from lead_intelligence.application.cleaning.rules.common import (
    PairedFieldsConsistencyWarningRule,
    PresenceConsistencyWarningRule,
    ReferenceTableMembershipWarningRule,
    WhitespaceNormalizationRule,
    WhitespaceOnlyTrimRule,
)
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
)

_CATEGORY = RuleCategory.INDUSTRY
_ALL_CODE_FIELDS = tuple(code for code, _ in F.CLASSIFICATION_CODE_DESCRIPTION_PAIRS)
_ALL_DESC_FIELDS = tuple(desc for _, desc in F.CLASSIFICATION_CODE_DESCRIPTION_PAIRS)

INDUSTRY_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    WhitespaceNormalizationRule(
        "CLN-051",
        "Trim & Normalize Whitespace (Industry Text Fields)",
        _CATEGORY,
        (F.INDUSTRY_LABEL, *_ALL_DESC_FIELDS),
    ),
    WhitespaceOnlyTrimRule(
        "CLN-052",
        "Classification Code Whitespace-Only Trim",
        _CATEGORY,
        _ALL_CODE_FIELDS,
    ),
    PairedFieldsConsistencyWarningRule(
        "CLN-053",
        "Code/Description Pairing Consistency Warning",
        _CATEGORY,
        F.CLASSIFICATION_CODE_DESCRIPTION_PAIRS,
        "CODE_DESCRIPTION_PAIR_INCOMPLETE",
        "Exactly one of {field_a}/{field_b} is populated.",
    ),
    ReferenceTableMembershipWarningRule(
        "CLN-054",
        "Unrecognized Classification Code Warning",
        _CATEGORY,
        KNOWN_CLASSIFICATION_CODES,
        "UNRECOGNIZED_CLASSIFICATION_CODE",
        "{field} value '{value}' was not found in the bundled reference table.",
    ),
    PresenceConsistencyWarningRule(
        "CLN-055",
        "Industry Description Missing While Code Present Warning",
        _CATEGORY,
        _ALL_CODE_FIELDS,
        "any",
        (F.INDUSTRY_LABEL,),
        "any",
        "INDUSTRY_LABEL_MISSING",
        "A classification code is populated while D&B Hoovers Industry is absent.",
    ),
)
