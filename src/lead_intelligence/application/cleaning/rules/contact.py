"""Contact category rules: CLN-011 through CLN-023.

Fields: Email, Company Email, Direct Phone, Phone, Fax.
See docs/CLEANING_RULES.md §9.2 for the full specification each rule below
implements.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.reference_data.role_based_email_patterns import (
    DEFAULT_ROLE_BASED_PREFIXES,
)
from lead_intelligence.application.cleaning.rules.common import (
    AllFieldsAbsentWarningRule,
    DigitCountWarningRule,
    MissingFieldWarningRuleSet,
    PrimarySelectionRule,
    RegexShapeWarningRule,
    WhitespaceNormalizationRule,
)
from lead_intelligence.application.cleaning.rules.phone_formatting import format_e164
from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)
from lead_intelligence.domain.exceptions import InvalidCleaningConfigurationError

_CATEGORY = RuleCategory.CONTACT
_PHONE_ARTIFACT_PATTERN = re.compile(r"^'+")


class EmailDomainLowercasingRule(NormalizationRule):
    """CLN-013 — Email Domain Lowercasing. Safe: DNS hostnames are
    case-insensitive by specification."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-013",
            name="Email Domain Lowercasing",
            category=_CATEGORY,
            stage=RuleStage.SAFE,
            fields=(F.EMAIL, F.COMPANY_EMAIL),
            configurable=False,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, str) and "@" in value:
                local, _, domain = value.rpartition("@")
                lowered = domain.lower()
                if lowered != domain:
                    changes[field_name] = f"{local}@{lowered}"
        return changes


class EmailLocalPartLowercasingRule(NormalizationRule):
    """CLN-014 — Email Local-Part Lowercasing. Business: near-universal
    practice, but not RFC-guaranteed like the domain (CLN-013)."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-014",
            name="Email Local-Part Lowercasing",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.EMAIL, F.COMPANY_EMAIL),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, str) and "@" in value:
                local, _, domain = value.rpartition("@")
                lowered = local.lower()
                if lowered != local:
                    changes[field_name] = f"{lowered}@{domain}"
        return changes


class PhoneE164FormattingRule(NormalizationRule):
    """CLN-016 — Phone Number Canonical Formatting (E.164).

    Off by default and requires an explicit `default_region` parameter —
    enabling it without one is a configuration error caught before any
    record is processed, not a silent "assume US" guess.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-016",
            name="Phone Number Canonical Formatting (E.164)",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.DIRECT_PHONE, F.PHONE),
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
        if not params.get("default_region"):
            raise InvalidCleaningConfigurationError(
                f"{self._metadata.rule_id} is enabled but no 'default_region' "
                "parameter is configured."
            )

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        default_region = params.get("default_region")
        if not default_region:
            return {}
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, str) and value:
                formatted = format_e164(value, default_region)
                if formatted and formatted != value:
                    changes[field_name] = formatted
        return changes


def _has_no_at_or_multiple_at(value: str) -> bool:
    return value.count("@") != 1


def _domain_has_no_dot(value: str) -> bool:
    if "@" not in value:
        return False
    _, _, domain = value.rpartition("@")
    return "." not in domain


class MalformedEmailShapeWarningRule(QualityCheckRule):
    """CLN-019 — Malformed Email Shape Warning.

    Deliberately conservative: checks only the most basic shape signals
    (exactly one '@', a '.' in the domain), not a full RFC 5322 validator.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-019",
            name="Malformed Email Shape Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.EMAIL, F.COMPANY_EMAIL),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        warnings: list[QualityWarningDraft] = []
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if not isinstance(value, str) or not value:
                continue
            if _has_no_at_or_multiple_at(value) or _domain_has_no_dot(value):
                warnings.append(
                    QualityWarningDraft(
                        code="MALFORMED_EMAIL_SHAPE",
                        message=f"'{value}' does not have the basic shape of an email address.",
                        field_names=(field_name,),
                    )
                )
        return warnings


class RoleBasedEmailPatternWarningRule(QualityCheckRule):
    """CLN-020 — Role-Based Email Pattern Warning."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-020",
            name="Role-Based Email Pattern Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.EMAIL,),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        params = profile.parameters_for(self._metadata.rule_id)
        prefixes = frozenset(params.get("prefixes", DEFAULT_ROLE_BASED_PREFIXES))
        value = values.get(F.EMAIL)
        if not isinstance(value, str) or "@" not in value:
            return []
        local, _, _ = value.rpartition("@")
        if local.lower() in prefixes:
            return [
                QualityWarningDraft(
                    code="ROLE_BASED_EMAIL_PATTERN",
                    message=f"'{value}' looks like a role-based/generic inbox, not a personal one.",
                    field_names=(F.EMAIL,),
                )
            ]
        return []


CONTACT_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    WhitespaceNormalizationRule(
        "CLN-011",
        "Trim & Normalize Whitespace (Email Fields)",
        _CATEGORY,
        (F.EMAIL, F.COMPANY_EMAIL),
        remove_internal_whitespace=True,
    ),
    WhitespaceNormalizationRule(
        "CLN-012",
        "Strip Phone Force-Text Artifact",
        _CATEGORY,
        (F.DIRECT_PHONE, F.PHONE, F.FAX),
        artifact_pattern=_PHONE_ARTIFACT_PATTERN,
    ),
    EmailDomainLowercasingRule(),
    EmailLocalPartLowercasingRule(),
    PrimarySelectionRule(
        "CLN-015",
        "Primary Email Selection",
        _CATEGORY,
        (F.EMAIL, F.COMPANY_EMAIL),
        F.PRIMARY_EMAIL,
    ),
    PhoneE164FormattingRule(),
    PrimarySelectionRule(
        "CLN-017",
        "Primary Phone Selection",
        _CATEGORY,
        (F.DIRECT_PHONE, F.PHONE),
        F.PRIMARY_PHONE,
    ),
    MissingFieldWarningRuleSet(
        "CLN-018",
        "Missing Email Warning",
        _CATEGORY,
        ((F.EMAIL, "MISSING_EMAIL", "Email is missing."),),
    ),
    MalformedEmailShapeWarningRule(),
    RoleBasedEmailPatternWarningRule(),
    AllFieldsAbsentWarningRule(
        "CLN-021",
        "Missing Phone Warning",
        _CATEGORY,
        (F.DIRECT_PHONE, F.PHONE),
        "MISSING_PHONE",
        "Neither Direct Phone nor Phone is populated.",
    ),
    DigitCountWarningRule(
        "CLN-022",
        "Implausible Phone Digit Count Warning",
        _CATEGORY,
        (F.DIRECT_PHONE, F.PHONE),
        7,
        "IMPLAUSIBLE_PHONE_DIGIT_COUNT",
        "Only {digit_count} digit(s) found, below the {min_digits}-digit plausibility threshold.",
    ),
    RegexShapeWarningRule(
        "CLN-023",
        "Phone Contains Non-Numeric Characters Warning",
        _CATEGORY,
        (F.DIRECT_PHONE, F.PHONE),
        re.compile(r"[A-Za-z]"),
        False,
        "PHONE_CONTAINS_LETTERS",
        "Phone value contains letters.",
    ),
)
