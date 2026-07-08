"""Pure value-comparison primitives: text normalization, fuzzy similarity,
and the exact-match normalizers for email/phone.

WHY difflib, NOT A THIRD-PARTY FUZZY-MATCHING LIBRARY:
`difflib.SequenceMatcher` is in the standard library, deterministic (no
randomness, no model calls), and sufficient for the kind of near-duplicate
matching this engine needs (minor casing/whitespace/punctuation
differences in names, titles, and company names). Adding a dependency for
this would be unjustified weight for what a stdlib tool already does well.
"""

from __future__ import annotations

import difflib
import re
from typing import Callable, Mapping

_WHITESPACE_PATTERN = re.compile(r"\s+")
_NON_DIGIT_PATTERN = re.compile(r"\D")


def normalize_text(value: str) -> str:
    """Lowercase, trim, and collapse internal whitespace.

    Used both as the fuzzy-comparison input and as the deduplication key
    for fuzzy fields (so "Ada Lovelace" and "ada   lovelace" are treated
    as the same candidate value, not a CONFLICT).
    """

    return _WHITESPACE_PATTERN.sub(" ", value).strip().lower()


def similarity(a: str, b: str) -> float:
    """A deterministic similarity ratio in [0.0, 1.0] between `a` and `b`,
    after normalize_text. 1.0 means identical (after normalization); 0.0
    means nothing in common.
    """

    return difflib.SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def normalize_email(value: str) -> str:
    """Case- and whitespace-insensitive email comparison key."""

    return value.strip().lower()


def normalize_phone_digits(value: str) -> str:
    """Digit-only phone comparison key, preserving a leading '+' if present.

    Strips formatting punctuation (spaces, dashes, parentheses) so
    "+1 (555) 123-4567" and "+15551234567" compare equal under EXACT
    strategy, without attempting any real phone-number intelligence
    (area-code equivalence, extension handling, etc.) — that is
    deliberately out of this engine's scope.
    """

    has_plus = value.strip().startswith("+")
    digits = _NON_DIGIT_PATTERN.sub("", value)
    return f"+{digits}" if has_plus else digits


#: field_name -> the normalizer used for EXACT-strategy equality and
#: deduplication. A field_name with no entry here falls back to
#: normalize_text (case/whitespace-insensitive), a reasonable default for
#: any future EXACT field that isn't email or phone.
EXACT_NORMALIZERS: Mapping[str, Callable[[str], str]] = {
    "email": normalize_email,
    "phone": normalize_phone_digits,
}


def normalizer_for(field_name: str) -> Callable[[str], str]:
    """The EXACT-strategy normalizer configured for `field_name`, or
    normalize_text as a sensible default."""

    return EXACT_NORMALIZERS.get(field_name, normalize_text)
