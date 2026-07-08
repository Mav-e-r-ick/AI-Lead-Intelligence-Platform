"""Existing-value resolvers: how each comparable field's value is read
from an existing (cleaned) executive record.

WHY THESE ARE FIXED FUNCTIONS, NOT PART OF ComparisonProfile:
ComparisonProfile (config.py) is the *configurable* surface — which fields
exist, their comparison strategy, their fuzzy threshold, which
observation attributes count as "new value" sources. How to read the
existing side of the comparison is tied directly to
`field_contract.py`'s schema (the same canonical vocabulary the Cleaning
Engine and Identity Resolution Engine already use) and isn't a per-run
tuning knob — it belongs here as code, the same way
`identity_resolution/signal_extraction.py` hardcodes its own field
fallback chains rather than making them profile-configurable. Keeping
function objects out of the (otherwise plain-data) ComparisonProfile also
keeps that dataclass comparable/inspectable, matching every other
Profile in this platform.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from lead_intelligence.application.cleaning import field_contract as fc

ExistingValueResolver = Callable[[Mapping[str, Any]], "str | None"]


def _first_present(values: Mapping[str, Any], *keys: str) -> str | None:
    """The first non-blank value found under `keys`, in order, or None."""

    for key in keys:
        value = values.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def resolve_name(values: Mapping[str, Any]) -> str | None:
    """Full name, combined from first + last name — mirrors
    identity_resolution/signal_extraction.py's `_add_full_name_signal`."""

    first = values.get(fc.FIRST_NAME)
    last = values.get(fc.LAST_NAME)
    if not first and not last:
        return None
    full_name = f"{first or ''} {last or ''}".strip()
    return full_name or None


def resolve_title(values: Mapping[str, Any]) -> str | None:
    return _first_present(values, fc.TITLE)


def resolve_company(values: Mapping[str, Any]) -> str | None:
    return _first_present(values, fc.COMPANY_NAME_NORMALIZED, fc.COMPANY_NAME)


def resolve_email(values: Mapping[str, Any]) -> str | None:
    return _first_present(values, fc.PRIMARY_EMAIL, fc.EMAIL, fc.COMPANY_EMAIL)


def resolve_phone(values: Mapping[str, Any]) -> str | None:
    return _first_present(values, fc.PRIMARY_PHONE, fc.DIRECT_PHONE, fc.PHONE)


#: field_name (matching ComparisonFieldRule.field_name) -> resolver.
#: A ComparisonProfile whose field_rules reference a field_name not listed
#: here cannot be run — see ComparisonEngine's lookup and
#: InvalidComparisonConfigurationError.
EXISTING_VALUE_RESOLVERS: Mapping[str, ExistingValueResolver] = {
    "name": resolve_name,
    "title": resolve_title,
    "company": resolve_company,
    "email": resolve_email,
    "phone": resolve_phone,
}
