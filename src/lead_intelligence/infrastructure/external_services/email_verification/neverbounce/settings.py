"""NeverBounceSettings: every knob this one provider needs.

WHY THIS ISN'T PART OF THE FRAMEWORK'S VerificationProviderConfiguration:
VerificationProviderConfiguration (application/verification/config.py) is
deliberately generic — enabled/priority/a timeout the framework itself
doesn't enforce — plus a fully opaque `parameters` mapping the framework
never interprets. Real per-provider behavior (the API key, the base URL,
retry counts, backoff) is exactly what "no provider-specific business
logic in the framework" pushes down into the provider itself. This
dataclass is where that lives, fully typed rather than pulled out of
`parameters` at call time.

WHY from_env() EXISTS, SEPARATE FROM THE DATACLASS ITSELF:
Reading `os.environ` directly inside the dataclass would make every test
either mutate real process environment variables or monkeypatch `os.environ`.
Instead, `from_env()` takes an injectable `env` mapping (defaulting to
`os.environ`), so tests can pass a plain dict and production code can call
`NeverBounceSettings.from_env()` with no arguments — only the real
`NEVERBOUNCE_API_KEY` environment variable is needed once one exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

#: The one environment variable this provider requires.
NEVERBOUNCE_API_KEY_ENV_VAR = "NEVERBOUNCE_API_KEY"


@dataclass(frozen=True)
class NeverBounceSettings:
    """Immutable, typed configuration for one NeverBounceEmailProvider instance.

    Attributes:
        api_key: NeverBounce API key, sent as the `key` query parameter on
            every request. Read from the `NEVERBOUNCE_API_KEY` environment
            variable via `from_env()` — never hardcoded.
        base_url: NeverBounce API base URL. Overridable for testing against
            a mock server; production code never needs to change it.
        timeout_seconds: Per-request timeout, applied to every verification
            call.
        max_retries: How many additional attempts are made after an initial
            failed request (timeout, connection error, 5xx response,
            `throttle_triggered`, or `temp_unavail`) before giving up.
            Non-transient API errors (auth_failure, general_failure,
            bad_referrer, and ordinary 4xx responses) are never retried —
            retrying a bad API key cannot succeed.
        retry_backoff_seconds: Base delay before a retry; multiplied by the
            attempt number for simple linear backoff.
    """

    api_key: str
    base_url: str = "https://api.neverbounce.com/v4"
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    def validate(self) -> None:
        """Raise ValueError if this settings object is self-contradictory.

        Called once, at provider construction time — a misconfigured
        provider should fail immediately, not on its first request.
        """

        if not self.api_key.strip():
            raise ValueError(
                "NeverBounceSettings.api_key must not be blank. Set the "
                f"{NEVERBOUNCE_API_KEY_ENV_VAR} environment variable."
            )
        if not self.base_url.strip():
            raise ValueError("NeverBounceSettings.base_url must not be blank.")
        if self.timeout_seconds <= 0:
            raise ValueError(
                "NeverBounceSettings.timeout_seconds must be > 0, got "
                f"{self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                f"NeverBounceSettings.max_retries must be >= 0, got {self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "NeverBounceSettings.retry_backoff_seconds must be >= 0, got "
                f"{self.retry_backoff_seconds}."
            )

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None, **overrides: object
    ) -> NeverBounceSettings:
        """Build settings from environment variables.

        Args:
            env: Mapping to read `NEVERBOUNCE_API_KEY` from. Defaults to
                the real process environment (`os.environ`); pass a plain
                dict in tests.
            **overrides: Any other `NeverBounceSettings` field (e.g.
                `timeout_seconds=5.0`), for callers who want everything
                else from the environment but one field overridden.

        Returns:
            A NeverBounceSettings with `api_key` read from the
            environment. `validate()` is not called here — call it once
            the provider is constructed, same as every other settings
            object in this codebase.
        """

        source = env if env is not None else os.environ
        api_key = source.get(NEVERBOUNCE_API_KEY_ENV_VAR, "")
        return cls(api_key=api_key, **overrides)  # type: ignore[arg-type]
