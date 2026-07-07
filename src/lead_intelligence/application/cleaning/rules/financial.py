"""Financial category rules: CLN-044 through CLN-050.

See docs/CLEANING_RULES.md §9.5 for the full specification each rule below
implements.
"""

from __future__ import annotations

from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.rules.common import (
    CrossFieldGreaterThanWarningRule,
    MissingValueRepresentationRule,
    NegativeValueWarningRule,
    PresenceConsistencyWarningRule,
)
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)
from lead_intelligence.domain.exceptions import InvalidCleaningConfigurationError

_CATEGORY = RuleCategory.FINANCIAL
_FINANCIAL_FIELDS = (F.SALES_USD, F.PRE_TAX_PROFIT_USD, F.ASSETS_USD, F.LIABILITIES_USD)
_SCALE_FACTORS: dict[str, float] = {
    "units": 1,
    "thousands": 1_000,
    "millions": 1_000_000,
}


class CurrencyUnitTaggingRule(NormalizationRule):
    """CLN-045 — Currency Unit Tagging. Never inferred from magnitude or
    column name — requires an explicit `currency` parameter."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-045",
            name="Currency Unit Tagging",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=_FINANCIAL_FIELDS,
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def validate_config(self, profile: Any) -> None:
        if not profile.is_enabled(self):
            return
        params = profile.parameters_for(self._metadata.rule_id)
        if not params.get("currency"):
            raise InvalidCleaningConfigurationError(
                f"{self._metadata.rule_id} is enabled but no 'currency' parameter is configured."
            )

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        currency = params.get("currency")
        if not currency:
            return {}
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            if values.get(field_name) is not None:
                changes[f"{field_name}_currency"] = currency
        return changes


class UnitScaleNormalizationRule(NormalizationRule):
    """CLN-046 — Unit Scale Normalization. The single highest-consequence
    misconfiguration risk in the registry — a wrong/missing scale produces
    numbers wrong by orders of magnitude, so `scale` is required and
    validated before any record is processed."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-046",
            name="Unit Scale Normalization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.SALES_USD, F.ASSETS_USD, F.LIABILITIES_USD),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def validate_config(self, profile: Any) -> None:
        if not profile.is_enabled(self):
            return
        params = profile.parameters_for(self._metadata.rule_id)
        if params.get("scale") not in _SCALE_FACTORS:
            raise InvalidCleaningConfigurationError(
                f"{self._metadata.rule_id} is enabled but 'scale' is missing/invalid "
                f"(expected one of {sorted(_SCALE_FACTORS)})."
            )

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        factor = _SCALE_FACTORS.get(params.get("scale", ""))
        if not factor or factor == 1:
            return {}
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, (int, float)):
                changes[field_name] = value * factor
        return changes


class PrecisionRoundingRule(NormalizationRule):
    """CLN-047 — Precision Rounding. Off by default and always additive —
    writes a derived `{field}_rounded` attribute, never overwrites the
    original precise value."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-047",
            name="Precision Rounding",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=_FINANCIAL_FIELDS,
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        precision = params.get("round_to_nearest")
        if not precision:
            return {}
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, (int, float)):
                changes[f"{field_name}_rounded"] = round(value / precision) * precision
        return changes


FINANCIAL_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    MissingValueRepresentationRule(
        "CLN-044",
        "Normalize Missing-Value Representation (Financial Fields)",
        _CATEGORY,
        (*_FINANCIAL_FIELDS, F.EMPLOYEES_SINGLE_SITE, F.EMPLOYEES_TOTAL),
        sentinels=frozenset({"", "n/a", "null"}),
    ),
    CurrencyUnitTaggingRule(),
    UnitScaleNormalizationRule(),
    PrecisionRoundingRule(),
    NegativeValueWarningRule(
        "CLN-048",
        "Implausible Negative Value Warning",
        _CATEGORY,
        # Deliberately excludes Pre Tax Profit (USD) and Liabilities (USD):
        # profiling found 140 real rows with legitimately negative pre-tax
        # profit. Do not add either back without re-reading CLN-048's
        # Potential Risks in docs/CLEANING_RULES.md.
        (F.SALES_USD, F.ASSETS_USD, F.EMPLOYEES_TOTAL),
        "IMPLAUSIBLE_NEGATIVE_VALUE",
        "{field} is negative ({value}), which is implausible for this field.",
    ),
    CrossFieldGreaterThanWarningRule(
        "CLN-049",
        "Employees Single-Site Exceeds Total Warning",
        _CATEGORY,
        F.EMPLOYEES_SINGLE_SITE,
        F.EMPLOYEES_TOTAL,
        "SINGLE_SITE_EXCEEDS_TOTAL_EMPLOYEES",
        "Employees (Single Site) exceeds Employees (Total).",
    ),
    PresenceConsistencyWarningRule(
        "CLN-050",
        "Financial Field Populated Without Sales Warning",
        _CATEGORY,
        (F.ASSETS_USD, F.PRE_TAX_PROFIT_USD, F.LIABILITIES_USD),
        "any",
        (F.SALES_USD,),
        "any",
        "FINANCIAL_DATA_WITHOUT_SALES",
        "A financial field is populated while Sales (USD) is absent.",
    ),
)
