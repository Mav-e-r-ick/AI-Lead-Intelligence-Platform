"""Turns one CleanedLeadRecord into an ExtractedIdentity: the concrete
identity signals (RFC §1) present for one Subject in one record.

WHY THIS RUNS AFTER THE CLEANING ENGINE, NEVER BEFORE (RFC §9):
Signal comparison across records only works if values are already in a
consistent, comparable form (lowercased emails, E.164 phones, normalized
company names) — exactly what the Cleaning Engine's `cleaned_values`
already guarantees. This module never reads a RawRecord directly.

WHY EXTRACTION IS A SET OF SMALL, COMPOSABLE FUNCTIONS (Open/Closed):
Adding a new signal type (e.g. a future LinkedIn URL) means writing one
`_add_..._signal` helper, registering its weight/tier in config.py, and
calling the helper from the appropriate `_extract_*_signals` function — no
existing signal's extraction logic changes.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.identity_resolution_models import (
    ExtractedIdentity,
    IdentitySignal,
    SubjectType,
)
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
)

_DOMAIN_PATTERN = re.compile(r"@([\w.-]+\.\w+)")


def extract_identity(
    record: CleanedLeadRecord,
    subject_type: SubjectType,
    record_reference: str,
    profile: IdentityResolutionProfile,
) -> ExtractedIdentity:
    """Extract every available identity signal for `subject_type` from
    `record`'s already-cleaned values.

    Args:
        record: A CleanedLeadRecord — the Cleaning Engine's output.
        subject_type: Which Subject this record's signals describe. One
            record can be extracted twice, once per subject_type, since a
            D&B-style executive row carries both a person's and a
            company's identity signals.
        record_reference: An opaque, traceable reference to this record
            (e.g. "row:42"), carried through to every downstream decision
            and audit entry for explainability.
        profile: The active IdentityResolutionProfile, consulted for each
            signal's tier.

    Returns:
        An ExtractedIdentity. Never raises for missing fields — a signal
        is simply omitted when its source field(s) are blank; RFC §1
        requires the engine work even when "some fields are missing."
    """

    values = record.cleaned_values
    if subject_type is SubjectType.PERSON:
        signals = _extract_person_signals(values, profile)
    else:
        signals = _extract_company_signals(values, profile)
    return ExtractedIdentity(
        subject_type=subject_type,
        record_reference=record_reference,
        signals=tuple(signals),
    )


def _extract_person_signals(
    values: Mapping[str, Any], profile: IdentityResolutionProfile
) -> list[IdentitySignal]:
    signals: list[IdentitySignal] = []
    _add_email_signal(signals, values, profile)
    _add_full_name_signal(signals, values, profile)
    _add_phone_signal(signals, values, profile)
    _add_title_signal(signals, values, profile)
    return signals


def _extract_company_signals(
    values: Mapping[str, Any], profile: IdentityResolutionProfile
) -> list[IdentitySignal]:
    signals: list[IdentitySignal] = []
    _add_duns_signal(signals, values, profile)
    _add_company_domain_signal(signals, values, profile)
    _add_company_name_city_signal(signals, values, profile)
    return signals


def _add_signal(
    signals: list[IdentitySignal],
    profile: IdentityResolutionProfile,
    signal_type: str,
    raw_value: Any,
    source_fields: tuple[str, ...],
) -> None:
    """Normalize `raw_value` and, if non-empty, append its IdentitySignal.

    Every extractor helper below delegates here so normalization
    (stringify, strip, lowercase) and "skip if blank" are handled exactly
    once, not repeated per signal type.
    """

    if raw_value is None:
        return
    normalized = str(raw_value).strip().lower()
    if not normalized:
        return
    definition = profile.definition_for(signal_type)
    signals.append(
        IdentitySignal(
            signal_type=signal_type,
            value=normalized,
            tier=definition.tier,
            source_fields=source_fields,
        )
    )


def _add_email_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    email = (
        values.get(fc.PRIMARY_EMAIL)
        or values.get(fc.EMAIL)
        or values.get(fc.COMPANY_EMAIL)
    )
    _add_signal(signals, profile, "email_exact", email, (fc.PRIMARY_EMAIL,))


def _add_full_name_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    first = values.get(fc.FIRST_NAME)
    last = values.get(fc.LAST_NAME)
    if not first and not last:
        return
    full_name = f"{first or ''} {last or ''}".strip()
    _add_signal(signals, profile, "full_name", full_name, (fc.FIRST_NAME, fc.LAST_NAME))


def _add_phone_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    phone = (
        values.get(fc.PRIMARY_PHONE)
        or values.get(fc.DIRECT_PHONE)
        or values.get(fc.PHONE)
    )
    _add_signal(signals, profile, "phone", phone, (fc.PRIMARY_PHONE,))


def _add_title_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    _add_signal(signals, profile, "title", values.get(fc.TITLE), (fc.TITLE,))


def _add_duns_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    _add_signal(
        signals, profile, "duns_number", values.get(fc.DUNS_NUMBER), (fc.DUNS_NUMBER,)
    )


def _extract_domain(email: str | None) -> str | None:
    """The domain portion of an email address, or None.

    Strips a leading "www." for the same reason CLN-066 does in the
    Cleaning Engine (application/cleaning/rules/cross_field.py): a domain
    derived from a URL almost always carries "www.", while one derived
    from an email never does — without stripping it, this signal would
    rarely match even for the same company.
    """

    if not email:
        return None
    match = _DOMAIN_PATTERN.search(email)
    if not match:
        return None
    domain = match.group(1).lower()
    if domain.startswith("www."):
        domain = domain[len("www.") :]
    return domain


def _add_company_domain_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    company_name = values.get(fc.COMPANY_NAME_NORMALIZED) or values.get(fc.COMPANY_NAME)
    domain = _extract_domain(
        values.get(fc.PRIMARY_EMAIL) or values.get(fc.COMPANY_EMAIL)
    )
    if not company_name or not domain:
        return
    composite = f"{domain}|{company_name}"
    _add_signal(
        signals,
        profile,
        "company_domain_and_name",
        composite,
        (fc.COMPANY_NAME, fc.PRIMARY_EMAIL),
    )


def _add_company_name_city_signal(
    signals: list[IdentitySignal],
    values: Mapping[str, Any],
    profile: IdentityResolutionProfile,
) -> None:
    company_name = values.get(fc.COMPANY_NAME_NORMALIZED) or values.get(fc.COMPANY_NAME)
    city = values.get(fc.CITY)
    if not company_name or not city:
        return
    composite = f"{company_name}|{city}"
    _add_signal(
        signals, profile, "company_name_city", composite, (fc.COMPANY_NAME, fc.CITY)
    )
