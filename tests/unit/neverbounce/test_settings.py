"""Tests for NeverBounceSettings."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NEVERBOUNCE_API_KEY_ENV_VAR,
    NeverBounceSettings,
)


class TestNeverBounceSettingsValidate:
    def test_valid_settings_pass(self) -> None:
        NeverBounceSettings(api_key="secret-key").validate()

    def test_blank_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            NeverBounceSettings(api_key="").validate()

    def test_whitespace_only_api_key_raises(self) -> None:
        with pytest.raises(ValueError, match="api_key"):
            NeverBounceSettings(api_key="   ").validate()

    def test_blank_base_url_raises(self) -> None:
        with pytest.raises(ValueError, match="base_url"):
            NeverBounceSettings(api_key="secret-key", base_url=" ").validate()

    def test_non_positive_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds"):
            NeverBounceSettings(api_key="secret-key", timeout_seconds=0).validate()

    def test_negative_max_retries_raises(self) -> None:
        with pytest.raises(ValueError, match="max_retries"):
            NeverBounceSettings(api_key="secret-key", max_retries=-1).validate()

    def test_negative_retry_backoff_raises(self) -> None:
        with pytest.raises(ValueError, match="retry_backoff_seconds"):
            NeverBounceSettings(
                api_key="secret-key", retry_backoff_seconds=-0.1
            ).validate()


class TestNeverBounceSettingsFromEnv:
    def test_reads_api_key_from_given_mapping(self) -> None:
        settings = NeverBounceSettings.from_env({NEVERBOUNCE_API_KEY_ENV_VAR: "abc123"})

        assert settings.api_key == "abc123"

    def test_missing_env_var_yields_blank_api_key(self) -> None:
        settings = NeverBounceSettings.from_env({})

        assert settings.api_key == ""

    def test_accepts_field_overrides(self) -> None:
        settings = NeverBounceSettings.from_env(
            {NEVERBOUNCE_API_KEY_ENV_VAR: "abc123"}, timeout_seconds=5.0, max_retries=5
        )

        assert settings.timeout_seconds == 5.0
        assert settings.max_retries == 5

    def test_defaults_to_real_os_environ_when_no_mapping_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(NEVERBOUNCE_API_KEY_ENV_VAR, "from-real-env")

        settings = NeverBounceSettings.from_env()

        assert settings.api_key == "from-real-env"
