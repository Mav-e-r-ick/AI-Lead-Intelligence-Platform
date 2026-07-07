"""Targeted behavior tests for the bespoke (non-generic) rules — the ones
with real logic beyond a common.py instantiation, where a bug would be
easy to introduce and hard to notice.
"""

from __future__ import annotations

import pytest

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.config import CleaningProfile, RuleOverride
from lead_intelligence.application.cleaning.rules.company import (
    CompanyNameCasingStandardizationRule,
    LegalSuffixStandardizationRule,
    TickerWithoutPublicOwnershipWarningRule,
)
from lead_intelligence.application.cleaning.rules.contact import (
    MalformedEmailShapeWarningRule,
    PhoneE164FormattingRule,
    RoleBasedEmailPatternWarningRule,
)
from lead_intelligence.application.cleaning.rules.cross_field import (
    CountryAwarePhoneFormattingRule,
    EmailDomainCompanyDomainMismatchWarningRule,
)
from lead_intelligence.application.cleaning.rules.identity import (
    ContactLevelTitleConsistencyWarningRule,
    NameCasingStandardizationRule,
    NameSuffixNormalizationRule,
    TitleAcronymCasingRule,
)
from lead_intelligence.domain.exceptions import InvalidCleaningConfigurationError

_PROFILE = CleaningProfile(name="test")


def _profile_with(rule_id: str, *, enabled: bool = True, **params) -> CleaningProfile:
    return CleaningProfile(
        name="test",
        rule_overrides={rule_id: RuleOverride(enabled=enabled, parameters=params)},
    )


# --- CLN-002: Name Casing --------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("o'brien", "O'Brien"),
        ("mcdonald", "McDonald"),
        ("VAN DER BERG", "van der Berg"),
        ("jean-pierre", "Jean-Pierre"),
    ],
)
def test_name_casing_standardization(raw: str, expected: str) -> None:
    rule = NameCasingStandardizationRule()
    assert rule.apply({F.FIRST_NAME: raw}, _PROFILE)[F.FIRST_NAME] == expected


# --- CLN-003: Name Suffix ---------------------------------------------------


def test_name_suffix_detaches_suffix_only_when_strip_configured() -> None:
    rule = NameSuffixNormalizationRule()
    profile = _profile_with("CLN-003", strip=True)
    result = rule.apply({F.LAST_NAME: "Smith III"}, profile)
    assert result == {F.LAST_NAME: "Smith", F.NAME_SUFFIX: "III"}


def test_name_suffix_keep_mode_is_a_no_op() -> None:
    rule = NameSuffixNormalizationRule()
    assert rule.apply({F.LAST_NAME: "Smith III"}, _PROFILE) == {}


# --- CLN-004: Title Acronym Casing ------------------------------------------


def test_title_acronym_correction_fixes_known_defect_pattern() -> None:
    rule = TitleAcronymCasingRule()
    result = rule.apply({F.TITLE: "Director, Crm Product Development"}, _PROFILE)
    assert result[F.TITLE] == "Director, CRM Product Development"


def test_title_acronym_correction_no_op_when_no_acronyms_present() -> None:
    rule = TitleAcronymCasingRule()
    assert rule.apply({F.TITLE: "Regional Sales Manager"}, _PROFILE) == {}


# --- CLN-010: Contact Level / Title Consistency ----------------------------


def test_contact_level_title_consistency_no_warning_when_consistent() -> None:
    rule = ContactLevelTitleConsistencyWarningRule()
    warnings = rule.apply(
        {F.CONTACT_LEVEL: "C-Level", F.TITLE: "Chief Experience Officer"}, _PROFILE
    )
    assert warnings == []


def test_contact_level_title_consistency_warns_when_mismatched() -> None:
    rule = ContactLevelTitleConsistencyWarningRule()
    warnings = rule.apply(
        {F.CONTACT_LEVEL: "C-Level", F.TITLE: "Regional Sales Manager"}, _PROFILE
    )
    assert len(warnings) == 1
    assert warnings[0].code == "CONTACT_LEVEL_TITLE_MISMATCH"


def test_contact_level_title_consistency_no_warning_when_level_empty() -> None:
    rule = ContactLevelTitleConsistencyWarningRule()
    assert rule.apply({F.CONTACT_LEVEL: None, F.TITLE: "Anything"}, _PROFILE) == []


# --- CLN-019: Malformed Email Shape -----------------------------------------


@pytest.mark.parametrize(
    "value,should_warn",
    [
        ("a.example.com", True),
        ("a@b@c.com", True),
        ("a@localhost", True),
        ("cristinaf@justfoodfordogs.com", False),
    ],
)
def test_malformed_email_shape(value: str, should_warn: bool) -> None:
    rule = MalformedEmailShapeWarningRule()
    warnings = rule.apply({F.EMAIL: value}, _PROFILE)
    assert bool(warnings) == should_warn


# --- CLN-020: Role-Based Email --------------------------------------------


def test_role_based_email_pattern_detected() -> None:
    rule = RoleBasedEmailPatternWarningRule()
    assert rule.apply({F.EMAIL: "info@acmecorp.com"}, _PROFILE) != []
    assert rule.apply({F.EMAIL: "cristinaf@justfoodfordogs.com"}, _PROFILE) == []


# --- CLN-016: Phone E.164 ---------------------------------------------------


def test_phone_e164_formats_us_number_with_configured_region() -> None:
    rule = PhoneE164FormattingRule()
    profile = _profile_with("CLN-016", default_region="US")
    result = rule.apply({F.DIRECT_PHONE: "1-949-722-3647"}, profile)
    assert result[F.DIRECT_PHONE] == "+19497223647"


def test_phone_e164_leaves_already_formatted_number_unchanged() -> None:
    rule = PhoneE164FormattingRule()
    profile = _profile_with("CLN-016", default_region="US")
    assert rule.apply({F.DIRECT_PHONE: "+19497223647"}, profile) == {}


def test_phone_e164_validate_config_requires_default_region() -> None:
    rule = PhoneE164FormattingRule()
    profile = _profile_with("CLN-016")  # enabled, no default_region
    with pytest.raises(InvalidCleaningConfigurationError):
        rule.validate_config(profile)


def test_phone_e164_validate_config_is_a_no_op_when_disabled() -> None:
    rule = PhoneE164FormattingRule()
    rule.validate_config(_PROFILE)  # disabled by default -> should not raise


# --- CLN-067: Country-Aware Phone Formatting --------------------------------


def test_country_aware_phone_formatting_uses_record_country() -> None:
    rule = CountryAwarePhoneFormattingRule()
    profile = _profile_with("CLN-067", default_region="US")
    result = rule.apply(
        {F.COUNTRY: "United States", F.DIRECT_PHONE: "1-949-722-3647", F.PHONE: None},
        profile,
    )
    assert result[F.DIRECT_PHONE] == "+19497223647"


def test_country_aware_phone_formatting_and_cln_016_are_mutually_exclusive() -> None:
    rule = CountryAwarePhoneFormattingRule()
    profile = CleaningProfile(
        name="test",
        rule_overrides={
            "CLN-016": RuleOverride(enabled=True, parameters={"default_region": "US"}),
            "CLN-067": RuleOverride(enabled=True, parameters={"default_region": "US"}),
        },
    )
    with pytest.raises(InvalidCleaningConfigurationError):
        rule.validate_config(profile)


# --- CLN-026: Legal Suffix ---------------------------------------------------


def test_legal_suffix_strip_derives_normalized_name_without_touching_original() -> None:
    rule = LegalSuffixStandardizationRule()
    profile = _profile_with("CLN-026", mode="strip")
    result = rule.apply({F.COMPANY_NAME: "Abercrombie & Fitch Co."}, profile)
    assert result == {F.COMPANY_NAME_NORMALIZED: "Abercrombie & Fitch"}


# --- CLN-027: Company Name Casing -------------------------------------------


def test_company_name_casing_respects_brand_exception_list() -> None:
    rule = CompanyNameCasingStandardizationRule()
    result = rule.apply({F.COMPANY_NAME: "EBAY INC."}, _PROFILE)
    assert result[F.COMPANY_NAME] == "eBay Inc."


# --- CLN-031: Ticker Without Public Ownership -------------------------------


def test_ticker_without_public_ownership_handles_multi_value_field() -> None:
    rule = TickerWithoutPublicOwnershipWarningRule()
    assert rule.apply({F.TICKER: "ABC", F.OWNERSHIP_TYPE: "Private"}, _PROFILE) != []
    assert (
        rule.apply(
            {F.TICKER: "ABC", F.OWNERSHIP_TYPE: "Private, Public, Partnership"},
            _PROFILE,
        )
        == []
    )


# --- CLN-066: Email/Company Domain Mismatch ---------------------------------


def test_email_domain_mismatch_strips_www_prefix_before_comparing() -> None:
    """Regression test: URLs in the reference dataset are almost always
    'http://www.example.com' while emails never carry a www. subdomain —
    without stripping it, this rule would false-positive on nearly every
    record (found and fixed during end-to-end verification)."""

    rule = EmailDomainCompanyDomainMismatchWarningRule()
    result = rule.apply(
        {
            F.EMAIL: "cristinaf@justfoodfordogs.com",
            F.URL: "http://www.justfoodfordogs.com",
        },
        _PROFILE,
    )
    assert result == []


def test_email_domain_mismatch_still_fires_on_a_real_mismatch() -> None:
    rule = EmailDomainCompanyDomainMismatchWarningRule()
    result = rule.apply(
        {F.EMAIL: "cristinaf@justfoodfordogs.com", F.URL: "https://acmecorp.com"},
        _PROFILE,
    )
    assert len(result) == 1


def test_email_domain_mismatch_excludes_generic_providers() -> None:
    rule = EmailDomainCompanyDomainMismatchWarningRule()
    result = rule.apply(
        {F.EMAIL: "someone@gmail.com", F.URL: "https://acmecorp.com"}, _PROFILE
    )
    assert result == []
