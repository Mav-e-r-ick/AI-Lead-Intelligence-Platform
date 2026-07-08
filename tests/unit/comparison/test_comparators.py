"""Unit tests for comparators.py."""

from __future__ import annotations

from lead_intelligence.application.comparison.comparators import (
    normalize_email,
    normalize_phone_digits,
    normalize_text,
    normalizer_for,
    similarity,
)


def test_normalize_text_lowercases_trims_and_collapses_whitespace() -> None:
    assert normalize_text("  Ada   Lovelace  ") == "ada lovelace"


def test_similarity_is_one_for_identical_after_normalization() -> None:
    assert similarity("Ada Lovelace", "  ada   LOVELACE ") == 1.0


def test_similarity_is_zero_for_completely_different_strings() -> None:
    assert similarity("aaaa", "zzzz") == 0.0


def test_similarity_is_between_zero_and_one_for_partial_overlap() -> None:
    score = similarity("Chief Executive Officer", "Chief Technology Officer")
    assert 0.0 < score < 1.0


def test_normalize_email_lowercases_and_trims() -> None:
    assert normalize_email("  Ada@ACME.com ") == "ada@acme.com"


def test_normalize_phone_digits_strips_formatting_punctuation() -> None:
    assert normalize_phone_digits("+1 (555) 123-4567") == "+15551234567"


def test_normalize_phone_digits_without_leading_plus() -> None:
    assert normalize_phone_digits("555-123-4567") == "5551234567"


def test_normalize_phone_digits_equal_after_normalization() -> None:
    assert normalize_phone_digits("+1 555 123 4567") == normalize_phone_digits(
        "+15551234567"
    )


def test_normalizer_for_email_uses_normalize_email() -> None:
    assert normalizer_for("email") is normalize_email


def test_normalizer_for_phone_uses_normalize_phone_digits() -> None:
    assert normalizer_for("phone") is normalize_phone_digits


def test_normalizer_for_unknown_field_falls_back_to_normalize_text() -> None:
    assert normalizer_for("some_future_field") is normalize_text
