"""Unit tests for resolvers.py's existing-value extraction functions."""

from __future__ import annotations

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison.resolvers import (
    EXISTING_VALUE_RESOLVERS,
    resolve_company,
    resolve_email,
    resolve_name,
    resolve_phone,
    resolve_title,
)


def test_resolve_name_combines_first_and_last() -> None:
    values = {fc.FIRST_NAME: "Ada", fc.LAST_NAME: "Lovelace"}

    assert resolve_name(values) == "Ada Lovelace"


def test_resolve_name_returns_none_when_both_missing() -> None:
    assert resolve_name({}) is None


def test_resolve_name_works_with_only_first_name() -> None:
    assert resolve_name({fc.FIRST_NAME: "Ada"}) == "Ada"


def test_resolve_title_returns_none_when_missing() -> None:
    assert resolve_title({}) is None


def test_resolve_title_returns_value() -> None:
    assert resolve_title({fc.TITLE: "CEO"}) == "CEO"


def test_resolve_company_prefers_normalized_name() -> None:
    values = {fc.COMPANY_NAME_NORMALIZED: "Acme", fc.COMPANY_NAME: "Acme Corp."}

    assert resolve_company(values) == "Acme"


def test_resolve_company_falls_back_to_company_name() -> None:
    assert resolve_company({fc.COMPANY_NAME: "Acme Corp."}) == "Acme Corp."


def test_resolve_email_fallback_chain() -> None:
    assert resolve_email({fc.EMAIL: "bob@example.com"}) == "bob@example.com"
    assert (
        resolve_email({fc.PRIMARY_EMAIL: "a@x.com", fc.EMAIL: "b@x.com"}) == "a@x.com"
    )
    assert resolve_email({fc.COMPANY_EMAIL: "info@example.com"}) == "info@example.com"
    assert resolve_email({}) is None


def test_resolve_phone_fallback_chain() -> None:
    assert resolve_phone({fc.DIRECT_PHONE: "+15550000000"}) == "+15550000000"
    assert resolve_phone({fc.PRIMARY_PHONE: "+1", fc.DIRECT_PHONE: "+2"}) == "+1"
    assert resolve_phone({fc.PHONE: "+15559999999"}) == "+15559999999"
    assert resolve_phone({}) is None


def test_blank_string_values_are_treated_as_absent() -> None:
    assert resolve_title({fc.TITLE: "   "}) is None


def test_every_default_field_has_a_registered_resolver() -> None:
    for field_name in ("name", "title", "company", "email", "phone"):
        assert field_name in EXISTING_VALUE_RESOLVERS
