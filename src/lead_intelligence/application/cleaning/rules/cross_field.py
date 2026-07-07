"""Cross-Field category rules: CLN-063 through CLN-068.

Rules here span two or more of the other 7 categories. A rule relating
multiple fields *within* one category lives in that category's module
instead (e.g. CLN-010, Contact Level vs. Title, is entirely within
Identity). See docs/CLEANING_RULES.md §9.8.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.reference_data.role_based_email_patterns import (
    DEFAULT_GENERIC_EMAIL_DOMAINS,
)
from lead_intelligence.application.cleaning.rules.address import _resolve_country_iso
from lead_intelligence.application.cleaning.rules.common import (
    AllFieldsAbsentWarningRule,
    IdenticalFieldsWarningRule,
    PresenceConsistencyWarningRule,
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

_CATEGORY = RuleCategory.CROSS_FIELD
_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _extract_domain(value: Any, *, is_url: bool = False) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if is_url:
        stripped = _SCHEME_PATTERN.sub("", value.strip())
        domain = stripped.split("/")[0].lower()
        # "www." is a near-universal web-facing subdomain convention that
        # email domains never carry (observed on the vast majority of URLs
        # during dataset profiling) — comparing "www.acme.com" to
        # "acme.com" without stripping it would make this warning fire on
        # almost every record, defeating its purpose as a useful signal.
        if domain.startswith("www."):
            domain = domain[len("www.") :]
        return domain or None
    if "@" not in value:
        return None
    return value.rpartition("@")[2].lower() or None


class EmailDomainCompanyDomainMismatchWarningRule(QualityCheckRule):
    """CLN-066 — Email Domain Does Not Match Company Domain Warning."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-066",
            name="Email Domain Does Not Match Company Domain Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.EMAIL, F.URL),
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
        generic_domains = frozenset(
            params.get("generic_domains", DEFAULT_GENERIC_EMAIL_DOMAINS)
        )
        email_domain = _extract_domain(values.get(F.EMAIL))
        url_domain = _extract_domain(values.get(F.URL), is_url=True)
        if not email_domain or not url_domain or email_domain in generic_domains:
            return []
        if email_domain != url_domain:
            return [
                QualityWarningDraft(
                    code="EMAIL_DOMAIN_COMPANY_DOMAIN_MISMATCH",
                    message=f"Email domain '{email_domain}' does not match company domain '{url_domain}'.",
                    field_names=(F.EMAIL, F.URL),
                )
            ]
        return []


class CountryAwarePhoneFormattingRule(NormalizationRule):
    """CLN-067 — Country-Aware Phone Default-Region Formatting.

    An alternative to CLN-016 that uses each record's own (already
    country-standardized, per CLN-038) Country/Region instead of one global
    default. Mutually exclusive with CLN-016 — enabling both is a
    configuration error, caught before any record is processed.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-067",
            name="Country-Aware Phone Default-Region Formatting",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.COUNTRY, F.DIRECT_PHONE, F.PHONE),
            configurable=True,
            default_enabled=False,
            dependencies=("CLN-038",),
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
                f"{self._metadata.rule_id} is enabled but no fallback 'default_region' "
                "parameter is configured."
            )
        from lead_intelligence.application.cleaning.rules.contact import (
            PhoneE164FormattingRule,
        )

        if profile.is_enabled(PhoneE164FormattingRule()):
            raise InvalidCleaningConfigurationError(
                "CLN-067 and CLN-016 are mutually exclusive alternatives and cannot "
                "both be enabled in the same profile."
            )

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        fallback_region = params.get("default_region")
        if not fallback_region:
            return {}
        region = _resolve_country_iso(values.get(F.COUNTRY)) or fallback_region
        changes: dict[str, Any] = {}
        for field_name in (F.DIRECT_PHONE, F.PHONE):
            value = values.get(field_name)
            if isinstance(value, str) and value:
                formatted = format_e164(value, region)
                if formatted and formatted != value:
                    changes[field_name] = formatted
        return changes


CROSS_FIELD_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    AllFieldsAbsentWarningRule(
        "CLN-063",
        "No Contact Method Available Warning",
        _CATEGORY,
        (F.EMAIL, F.DIRECT_PHONE, F.PHONE),
        "NO_CONTACT_METHOD_AVAILABLE",
        "Email, Direct Phone, and Phone are all absent — no contact method available.",
    ),
    IdenticalFieldsWarningRule(
        "CLN-064",
        "Person Name Duplicates Company Name Warning",
        _CATEGORY,
        (F.FIRST_NAME, F.LAST_NAME),
        F.COMPANY_NAME,
        "NAME_DUPLICATES_COMPANY_NAME",
        "First Name + Last Name duplicates Company Name.",
    ),
    IdenticalFieldsWarningRule(
        "CLN-065",
        "Address Duplicates Company Name Warning",
        _CATEGORY,
        (F.ADDRESS_LINE_1,),
        F.COMPANY_NAME,
        "ADDRESS_DUPLICATES_COMPANY_NAME",
        "Address Line 1 duplicates Company Name.",
    ),
    EmailDomainCompanyDomainMismatchWarningRule(),
    CountryAwarePhoneFormattingRule(),
    PresenceConsistencyWarningRule(
        "CLN-068",
        "Financial Data Present Without Industry Classification Warning",
        _CATEGORY,
        (F.SALES_USD,),
        "any",
        (
            F.INDUSTRY_LABEL,
            *[code for code, _ in F.CLASSIFICATION_CODE_DESCRIPTION_PAIRS],
        ),
        "any",
        "FINANCIAL_DATA_WITHOUT_INDUSTRY_CLASSIFICATION",
        "Sales (USD) is populated while no industry classification field is populated.",
    ),
)
