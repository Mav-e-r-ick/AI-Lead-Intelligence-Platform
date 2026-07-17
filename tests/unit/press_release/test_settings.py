"""Unit tests for PressReleaseProviderSettings."""

from __future__ import annotations

import pytest

from tests.unit.press_release.fixtures import build_settings


def test_defaults_pass_validation() -> None:
    build_settings().validate()


def test_blank_user_agent_raises() -> None:
    with pytest.raises(ValueError, match="user_agent"):
        build_settings(user_agent="").validate()


def test_non_positive_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        build_settings(timeout_seconds=0).validate()


def test_negative_max_retries_raises() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        build_settings(max_retries=-1).validate()


def test_negative_retry_backoff_raises() -> None:
    with pytest.raises(ValueError, match="retry_backoff_seconds"):
        build_settings(retry_backoff_seconds=-1).validate()


def test_max_pages_below_one_raises() -> None:
    with pytest.raises(ValueError, match="max_pages"):
        build_settings(max_pages=0).validate()


def test_max_depth_below_one_raises() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        build_settings(max_depth=0).validate()


def test_max_results_below_one_raises() -> None:
    with pytest.raises(ValueError, match="max_results"):
        build_settings(max_results=0).validate()
