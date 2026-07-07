"""Shared E.164 phone-formatting helper for CLN-016 and CLN-067.

A deliberately simplified formatter (no external phone-number library
dependency) covering the region(s) with real evidence from dataset
profiling. Never guesses a region — every caller must supply one
explicitly, per CLEANING_RULES.md's repeated "don't hardcode to this
file's assumptions" principle.
"""

from __future__ import annotations

import re

REGION_CALLING_CODES: dict[str, str] = {"US": "1", "CA": "1"}
REGION_NATIONAL_LENGTH: dict[str, int] = {"US": 10, "CA": 10}


def format_e164(value: str, default_region: str) -> str | None:
    """Best-effort E.164 formatting of `value`, using `default_region` when
    no country code is already present. Returns None if no digits found.
    """

    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if value.strip().startswith("+"):
        return f"+{digits}"

    calling_code = REGION_CALLING_CODES.get(default_region)
    national_length = REGION_NATIONAL_LENGTH.get(default_region)
    if calling_code and national_length and digits.startswith(calling_code):
        if len(digits) == len(calling_code) + national_length:
            return f"+{digits}"
    if calling_code:
        return f"+{calling_code}{digits}"
    return f"+{digits}"
