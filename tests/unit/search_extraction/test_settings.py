"""Unit tests for SearchExtractionSettings."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lead_intelligence.infrastructure.search.extraction.settings import (
    SearchExtractionSettings,
)


def test_default_settings_pass_validation() -> None:
    SearchExtractionSettings().validate()


def test_blank_user_agent_raises() -> None:
    with pytest.raises(ValueError, match="user_agent"):
        SearchExtractionSettings(user_agent="  ").validate()


def test_non_positive_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        SearchExtractionSettings(timeout_seconds=0).validate()


def test_negative_max_retries_raises() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        SearchExtractionSettings(max_retries=-1).validate()


def test_negative_retry_backoff_raises() -> None:
    with pytest.raises(ValueError, match="retry_backoff_seconds"):
        SearchExtractionSettings(retry_backoff_seconds=-0.1).validate()


def test_negative_cache_ttl_raises() -> None:
    with pytest.raises(ValueError, match="cache_ttl"):
        SearchExtractionSettings(cache_ttl=timedelta(seconds=-1)).validate()


def test_max_text_chars_below_one_raises() -> None:
    with pytest.raises(ValueError, match="max_text_chars"):
        SearchExtractionSettings(max_text_chars=0).validate()


def test_excerpt_chars_below_one_raises() -> None:
    with pytest.raises(ValueError, match="excerpt_chars"):
        SearchExtractionSettings(excerpt_chars=0).validate()
