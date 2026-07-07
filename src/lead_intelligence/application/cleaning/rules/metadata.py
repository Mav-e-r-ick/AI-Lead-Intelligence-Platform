"""Metadata category rules: CLN-056 through CLN-062.

See docs/CLEANING_RULES.md §9.7 for the full specification each rule below
implements. row_number/sheet_name (RawRecord's own provenance) are never
part of the canonical `values` mapping rules operate on — they survive
automatically via CleanedLeadRecord.raw_record, untouched. CLN-059 exists
purely to make that guarantee an explicit, documented registry entry.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.rules.common import (
    FieldPresentWarningRule,
    MissingFieldWarningRuleSet,
    PassthroughRule,
    WhitespaceNormalizationRule,
)
from lead_intelligence.application.cleaning.rules.common import (
    BooleanRepresentationNormalizationRule,
)
from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)

_CATEGORY = RuleCategory.METADATA
_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_BARE_DOMAIN_PATTERN = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$")


class UrlSchemeNormalizationRule(NormalizationRule):
    """CLN-057 — URL Scheme Normalization. Off by default: prepending a
    scheme is a guess (e.g. http:// might be correct instead of https://)."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-057",
            name="URL Scheme Normalization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.URL,),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        value = values.get(F.URL)
        if not isinstance(value, str) or not value.strip():
            return {}
        stripped = value.strip()
        if _SCHEME_PATTERN.match(stripped):
            return {}
        if _BARE_DOMAIN_PATTERN.match(stripped):
            return {F.URL: f"https://{stripped}"}
        return {}


class MalformedUrlShapeWarningRule(QualityCheckRule):
    """CLN-061 — Malformed URL Shape Warning."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-061",
            name="Malformed URL Shape Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.URL,),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        value = values.get(F.URL)
        if not isinstance(value, str) or not value.strip():
            return []
        stripped = value.strip()
        has_scheme = _SCHEME_PATTERN.match(stripped) is not None
        is_bare_domain = _BARE_DOMAIN_PATTERN.match(stripped) is not None
        if not has_scheme and not is_bare_domain:
            return [
                QualityWarningDraft(
                    code="MALFORMED_URL_SHAPE",
                    message=f"'{value}' does not look like a URL or a bare domain.",
                    field_names=(F.URL,),
                )
            ]
        return []


METADATA_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    WhitespaceNormalizationRule(
        "CLN-056",
        "Trim Whitespace (Metadata Text Fields)",
        _CATEGORY,
        (
            F.SOURCE,
            F.DIRECT_MARKETING_STATUS,
            F.URL,
            F.EMAIL_USAGE_RESTRICTION,
            F.DIRECT_PHONE_USAGE_RESTRICTION,
        ),
    ),
    UrlSchemeNormalizationRule(),
    BooleanRepresentationNormalizationRule(
        "CLN-058",
        "Boolean Flag Representation Normalization (TPS Flag)",
        _CATEGORY,
        (F.TPS_FLAG,),
    ),
    PassthroughRule(
        "CLN-059",
        "Provenance Field Passthrough (row_number, sheet_name)",
        _CATEGORY,
        ("row_number", "sheet_name"),
    ),
    MissingFieldWarningRuleSet(
        "CLN-060",
        "Missing Source Warning",
        _CATEGORY,
        ((F.SOURCE, "MISSING_SOURCE", "Source is missing."),),
    ),
    MalformedUrlShapeWarningRule(),
    FieldPresentWarningRule(
        "CLN-062",
        "Dedup ID Reliability Disclaimer Warning",
        _CATEGORY,
        F.DEDUP_ID,
        "DEDUP_ID_NOT_RELIABLE",
        (
            "Dedup ID is populated but is not a reliable per-contact unique key "
            "(confirmed during Import Engine dataset profiling: unrelated companies "
            "were observed sharing the same Dedup ID value). Do not rely on it for "
            "deduplication."
        ),
    ),
)
