"""Address category rules: CLN-035 through CLN-043.

See docs/CLEANING_RULES.md §9.4 for the full specification each rule below
implements.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.reference_data.country_codes import (
    COUNTRY_ISO_ALPHA2_TO_NAME,
    COUNTRY_NAME_TO_ISO_ALPHA2,
)
from lead_intelligence.application.cleaning.reference_data.street_abbreviations import (
    STREET_SUFFIX_ABBREVIATIONS_BY_COUNTRY,
)
from lead_intelligence.application.cleaning.reference_data.us_states import (
    US_STATE_ABBREVIATION_TO_NAME,
    US_STATE_NAME_TO_ABBREVIATION,
)
from lead_intelligence.application.cleaning.rules.common import (
    IdenticalFieldsWarningRule,
    MissingValueRepresentationRule,
    ReferenceTableStandardizationRule,
    WhitespaceNormalizationRule,
    is_field_present,
)
from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)

_CATEGORY = RuleCategory.ADDRESS
_ZIP_PLUS4_PATTERN = re.compile(r"^(\d{5})-(\d{4})$")
_POSTAL_CODE_PATTERNS_BY_COUNTRY: dict[str, re.Pattern[str]] = {
    "US": re.compile(r"^\d{5}(-\d{4})?$"),
}


def _resolve_country_iso(country_value: Any) -> str | None:
    if not isinstance(country_value, str) or not country_value.strip():
        return None
    candidate = country_value.strip()
    if len(candidate) == 2 and candidate.upper() in COUNTRY_ISO_ALPHA2_TO_NAME:
        return candidate.upper()
    return COUNTRY_NAME_TO_ISO_ALPHA2.get(candidate.lower())


class PostalCodeFormattingRule(NormalizationRule):
    """CLN-039 — Postal Code Formatting Policy.

    Off by default: the "5_digit" target truncates a real ZIP+4 extension,
    which is lossy by choice and must never be a silent default.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-039",
            name="Postal Code Formatting Policy",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.POSTAL_CODE,),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        target = params.get("target", "as_is")
        value = values.get(F.POSTAL_CODE)
        if not isinstance(value, str) or not value:
            return {}
        if target == "5_digit":
            match = _ZIP_PLUS4_PATTERN.match(value.strip())
            if match and match.group(1) != value:
                return {F.POSTAL_CODE: match.group(1)}
        return {}


class StreetAbbreviationStandardizationRule(NormalizationRule):
    """CLN-040 — Street Abbreviation Standardization.

    Region-scoped via Country/Region — never applies a US-specific table
    to a non-US address.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-040",
            name="Street Abbreviation Standardization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.ADDRESS_LINE_1, F.COUNTRY),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        target = params.get("target", "abbreviated")
        value = values.get(F.ADDRESS_LINE_1)
        if not isinstance(value, str) or not value or target != "abbreviated":
            return {}
        region = _resolve_country_iso(values.get(F.COUNTRY))
        table = STREET_SUFFIX_ABBREVIATIONS_BY_COUNTRY.get(region) if region else None
        if not table:
            return {}
        tokens = re.split(r"(\s+)", value)
        changed = False
        new_tokens: list[str] = []
        for token in tokens:
            key = token.lower().rstrip(".,")
            replacement = table.get(key)
            if replacement is not None:
                new_tokens.append(replacement)
                changed = True
            else:
                new_tokens.append(token)
        return {F.ADDRESS_LINE_1: "".join(new_tokens)} if changed else {}


class IncompleteAddressComponentWarningRule(QualityCheckRule):
    """CLN-041 — Incomplete Address Component Warning.

    Fires only when *some but not all* of City/State/Postal Code are
    populated — a fully-absent address is a different (non-)concern.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-041",
            name="Incomplete Address Component Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.CITY, F.STATE_OR_PROVINCE, F.POSTAL_CODE),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        flags = [is_field_present(values.get(f)) for f in self._metadata.fields]
        present_count = sum(flags)
        if 0 < present_count < len(flags):
            return [
                QualityWarningDraft(
                    code="INCOMPLETE_ADDRESS_COMPONENTS",
                    message="Only some of City/State/Postal Code are populated.",
                    field_names=self._metadata.fields,
                )
            ]
        return []


class PostalCodeShapeWarningRule(QualityCheckRule):
    """CLN-042 — Postal Code Shape Warning.

    Countries without a configured pattern are skipped, not guessed at.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-042",
            name="Postal Code Shape Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.POSTAL_CODE, F.COUNTRY),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        postal_code = values.get(F.POSTAL_CODE)
        if not isinstance(postal_code, str) or not postal_code:
            return []
        region = _resolve_country_iso(values.get(F.COUNTRY))
        pattern = _POSTAL_CODE_PATTERNS_BY_COUNTRY.get(region) if region else None
        if pattern is None:
            return []
        if not pattern.match(postal_code.strip()):
            return [
                QualityWarningDraft(
                    code="POSTAL_CODE_SHAPE_UNEXPECTED",
                    message=f"'{postal_code}' does not match the expected shape for {values.get(F.COUNTRY)}.",
                    field_names=(F.POSTAL_CODE, F.COUNTRY),
                )
            ]
        return []


ADDRESS_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    WhitespaceNormalizationRule(
        "CLN-035",
        "Trim & Normalize Whitespace (Address Fields)",
        _CATEGORY,
        (
            F.ADDRESS_LINE_1,
            F.ADDRESS_LINE_2,
            F.ADDRESS_LINE_3,
            F.CITY,
            F.STATE_OR_PROVINCE,
            F.POSTAL_CODE,
            F.COUNTRY,
        ),
    ),
    MissingValueRepresentationRule(
        "CLN-036",
        "Normalize Empty Address Line Representation",
        _CATEGORY,
        (F.ADDRESS_LINE_1, F.ADDRESS_LINE_2, F.ADDRESS_LINE_3),
    ),
    ReferenceTableStandardizationRule(
        "CLN-037",
        "State/Province Standardization",
        _CATEGORY,
        F.STATE_OR_PROVINCE,
        US_STATE_NAME_TO_ABBREVIATION,
        US_STATE_ABBREVIATION_TO_NAME,
    ),
    ReferenceTableStandardizationRule(
        "CLN-038",
        "Country Standardization (ISO 3166)",
        _CATEGORY,
        F.COUNTRY,
        COUNTRY_NAME_TO_ISO_ALPHA2,
        COUNTRY_ISO_ALPHA2_TO_NAME,
    ),
    PostalCodeFormattingRule(),
    StreetAbbreviationStandardizationRule(),
    IncompleteAddressComponentWarningRule(),
    PostalCodeShapeWarningRule(),
    IdenticalFieldsWarningRule(
        "CLN-043",
        "Address Line Duplicate Content Warning",
        _CATEGORY,
        (F.ADDRESS_LINE_1,),
        F.CITY,
        "ADDRESS_LINE_DUPLICATES_CITY",
        "Address Line 1 duplicates City.",
    ),
)
