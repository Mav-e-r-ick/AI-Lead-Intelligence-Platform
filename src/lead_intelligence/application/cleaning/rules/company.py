"""Company category rules: CLN-024 through CLN-034.

See docs/CLEANING_RULES.md §9.3 for the full specification each rule below
implements.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.reference_data.legal_suffixes import (
    DEFAULT_LEGAL_SUFFIXES,
)
from lead_intelligence.application.cleaning.rules.common import (
    BooleanRepresentationNormalizationRule,
    IdenticalFieldsWarningRule,
    MissingFieldWarningRuleSet,
    RegexShapeWarningRule,
    ThresholdWarningRule,
    WhitespaceNormalizationRule,
    WhitespaceOnlyTrimRule,
)
from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)

_CATEGORY = RuleCategory.COMPANY


class LegalSuffixStandardizationRule(NormalizationRule):
    """CLN-026 — Legal Suffix Standardization. Writes a derived attribute;
    never overwrites Company Name."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-026",
            name="Legal Suffix Standardization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.COMPANY_NAME,),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        mode = params.get("mode", "canonicalize")
        table = {**DEFAULT_LEGAL_SUFFIXES, **params.get("suffixes", {})}
        value = values.get(F.COMPANY_NAME)
        if not isinstance(value, str) or not value.strip():
            return {}
        last_token = value.strip().split(" ")[-1]
        key = last_token.lower().rstrip(".,")
        canonical = table.get(key)
        if canonical is None:
            return {}
        prefix = value[: -len(last_token)].rstrip(" ,")
        normalized = prefix if mode == "strip" else f"{prefix} {canonical}"
        return {F.COMPANY_NAME_NORMALIZED: normalized}


_DEFAULT_BRAND_EXCEPTIONS: dict[str, str] = {
    "ebay": "eBay",
    "iheartmedia": "iHeartMedia",
    "pwc": "PwC",
}


class CompanyNameCasingStandardizationRule(NormalizationRule):
    """CLN-027 — Company Name Casing Standardization.

    Off by default: unbounded, idiosyncratic brand capitalization makes
    this materially riskier than CLN-002's name casing.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-027",
            name="Company Name Casing Standardization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.COMPANY_NAME,),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        exceptions = {**_DEFAULT_BRAND_EXCEPTIONS, **params.get("exceptions", {})}
        value = values.get(F.COMPANY_NAME)
        if not isinstance(value, str) or not value:
            return {}
        tokens = re.split(r"(\s+)", value)
        changed = False
        new_tokens: list[str] = []
        for token in tokens:
            if not token.strip():
                new_tokens.append(token)
                continue
            stripped = token.rstrip(".,")
            key = stripped.lower()
            if key in exceptions:
                suffix = token[len(stripped) :]
                new_tokens.append(exceptions[key] + suffix)
                changed = True
            else:
                cased = token.capitalize()
                new_tokens.append(cased)
                changed = changed or cased != token
        return {F.COMPANY_NAME: "".join(new_tokens)} if changed else {}


class TickerWithoutPublicOwnershipWarningRule(QualityCheckRule):
    """CLN-031 — Ticker Present Without Public Ownership Warning.

    Ownership Type is a comma-separated multi-value field in the reference
    dataset (e.g. "Private, Public, Partnership") — handled accordingly.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-031",
            name="Ticker Present Without Public Ownership Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.TICKER, F.OWNERSHIP_TYPE),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        ticker = values.get(F.TICKER)
        if not isinstance(ticker, str) or not ticker.strip():
            return []
        ownership = values.get(F.OWNERSHIP_TYPE)
        ownership_values = (
            {part.strip().lower() for part in ownership.split(",")}
            if isinstance(ownership, str)
            else set()
        )
        if "public" not in ownership_values:
            return [
                QualityWarningDraft(
                    code="TICKER_WITHOUT_PUBLIC_OWNERSHIP",
                    message=(
                        f"Ticker '{ticker}' present but Ownership Type "
                        f"('{ownership}') does not indicate public ownership."
                    ),
                    field_names=(F.TICKER, F.OWNERSHIP_TYPE),
                )
            ]
        return []


COMPANY_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    WhitespaceNormalizationRule(
        "CLN-024",
        "Trim & Normalize Whitespace (Company Text Fields)",
        _CATEGORY,
        (
            F.COMPANY_NAME,
            F.TRADESTYLE,
            F.OWNERSHIP_TYPE,
            F.ENTITY_TYPE,
            F.PARENT_COMPANY,
            F.GLOBAL_ULTIMATE_COMPANY,
            F.BUSINESS_DESCRIPTION,
        ),
    ),
    WhitespaceOnlyTrimRule(
        "CLN-025", "D-U-N-S Number Whitespace-Only Trim", _CATEGORY, (F.DUNS_NUMBER,)
    ),
    LegalSuffixStandardizationRule(),
    CompanyNameCasingStandardizationRule(),
    BooleanRepresentationNormalizationRule(
        "CLN-028",
        "Boolean Flag Representation Normalization (Is Headquarters)",
        _CATEGORY,
        (F.IS_HEADQUARTERS,),
    ),
    MissingFieldWarningRuleSet(
        "CLN-029",
        "Missing Company Name Warning",
        _CATEGORY,
        ((F.COMPANY_NAME, "MISSING_COMPANY_NAME", "Company Name is missing."),),
    ),
    IdenticalFieldsWarningRule(
        "CLN-030",
        "Company Name Equals Parent Company Warning",
        _CATEGORY,
        (F.COMPANY_NAME,),
        F.PARENT_COMPANY,
        "COMPANY_EQUALS_PARENT",
        "Company Name and Parent Company are identical.",
    ),
    TickerWithoutPublicOwnershipWarningRule(),
    ThresholdWarningRule(
        "CLN-032",
        "Business Description Suspiciously Short Warning",
        _CATEGORY,
        F.BUSINESS_DESCRIPTION,
        10,
        "lt",
        "BUSINESS_DESCRIPTION_SUSPICIOUSLY_SHORT",
        "Business Description is only {length} characters, below the {threshold}-character threshold.",
    ),
    RegexShapeWarningRule(
        "CLN-033",
        "D-U-N-S Number Shape Warning",
        _CATEGORY,
        (F.DUNS_NUMBER,),
        re.compile(r"^\d{9}$"),
        True,
        "DUNS_SHAPE_UNEXPECTED",
        "D-U-N-S Number does not match the expected 9-digit numeric shape.",
    ),
    MissingFieldWarningRuleSet(
        "CLN-034",
        "Key ID Missing Warning",
        _CATEGORY,
        ((F.KEY_ID, "MISSING_KEY_ID", "Key ID is missing."),),
    ),
)
