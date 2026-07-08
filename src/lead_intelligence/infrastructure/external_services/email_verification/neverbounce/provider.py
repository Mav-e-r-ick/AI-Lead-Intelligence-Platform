"""NeverBounceEmailProvider: the Contact Verification Framework's first
concrete provider — verifies one email address via NeverBounce's v4
"single check" REST API (`GET /v4/single/check`).

WHY disposable AND catchall BOTH MAP TO VerificationStatus.RISKY:
The framework's VerificationStatus (application/dto/verification_models.py)
is fixed Version 1 scope — this task must not redesign it. RISKY already
means "deliverable/reachable but flagged as uncertain (e.g. a catch-all
domain, a role-based mailbox)," which is exactly what a catch-all domain
is, and disposable addresses are the same kind of "neither a clean pass
nor a clean fail" signal (technically valid syntax and often accepted by
the mail server, but unsuitable for real outreach). NeverBounce's own,
more specific classification is never lost — it is preserved verbatim in
`VerificationResult.reason` and the full API payload in `raw_response`.

WHY throttle_triggered AND temp_unavail ARE HANDLED DIFFERENTLY:
NeverBounce reports both with HTTP 200 and a body-level `status` field,
not an HTTP error code, so this provider inspects the JSON body itself
rather than trusting the HTTP status code alone. `throttle_triggered` is
this vendor's specific rate-limit signal -> retried, then RATE_LIMITED.
`temp_unavail` is a transient service outage -> retried, then ERROR (there
is no dedicated "service unavailable" VerificationStatus; ERROR is the
correct bucket for "the provider call itself failed"). `auth_failure`,
`general_failure`, and `bad_referrer` are configuration problems that a
retry cannot fix -> ERROR immediately, never retried.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import httpx
from loguru import logger

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from lead_intelligence.application.ports.verification_provider_port import (
    EmailVerificationPort,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NeverBounceSettings,
)

PROVIDER_ID = "neverbounce"

_CHECK_PATH = "/single/check"

#: NeverBounce's own `result` values (on a "success" response), mapped onto
#: this framework's fixed VerificationStatus vocabulary.
_RESULT_STATUS_MAP: Mapping[str, VerificationStatus] = {
    "valid": VerificationStatus.VALID,
    "invalid": VerificationStatus.INVALID,
    "disposable": VerificationStatus.RISKY,
    "catchall": VerificationStatus.RISKY,
    "unknown": VerificationStatus.UNKNOWN,
}

_RESULT_REASONS: Mapping[str, str] = {
    "valid": "NeverBounce confirmed this address is deliverable.",
    "invalid": "NeverBounce confirmed this address is not deliverable.",
    "disposable": "NeverBounce flagged this address as a disposable/temporary mailbox.",
    "catchall": (
        "NeverBounce found the domain accepts all addresses (catch-all); "
        "deliverability of this specific address is unconfirmed."
    ),
    "unknown": "NeverBounce could not determine deliverability for this address.",
}

#: Body-level `status` values that represent a transient condition worth
#: retrying, mapped to the terminal VerificationStatus reported if every
#: retry is exhausted.
_RETRYABLE_API_STATUSES: Mapping[str, VerificationStatus] = {
    "throttle_triggered": VerificationStatus.RATE_LIMITED,
    "temp_unavail": VerificationStatus.ERROR,
}


class _CheckOutcome:
    """Internal, unstamped result of one NeverBounce API call — the
    provider's `verify()` stamps this into a full VerificationResult with
    request/subject/timing context. Mirrors the Draft pattern used
    elsewhere in this platform (e.g. InflectionDraft): a helper method
    should not need to know request-level bookkeeping."""

    __slots__ = ("status", "reason", "error_message", "raw_response")

    def __init__(
        self,
        status: VerificationStatus,
        reason: str | None = None,
        error_message: str | None = None,
        raw_response: Mapping[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.reason = reason
        self.error_message = error_message
        self.raw_response = raw_response or {}


class NeverBounceEmailProvider(EmailVerificationPort):
    """Verifies email addresses via NeverBounce (Version 1 — see module
    docstring and README.md)."""

    def __init__(
        self,
        settings: NeverBounceSettings,
        http_client: httpx.Client | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            settings: This provider's own configuration (API key, base URL,
                timeout, retry policy). Typically built via
                `NeverBounceSettings.from_env()`.
            http_client: The httpx.Client used for every request. Defaults
                to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
            sleep_fn: Called between retry attempts. Override with a no-op
                in tests to avoid real delays.
        """

        settings.validate()
        self._settings = settings
        self._http_client = http_client or httpx.Client()
        self._clock = clock
        self._sleep = sleep_fn

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "NeverBounce"

    def verify(self, request: VerificationRequest) -> VerificationResult:
        """Verify `request.value` (an email address) via NeverBounce.

        Never raises for ordinary failure modes (timeout, rate limiting,
        an API error) — those are reported via
        `VerificationResult.status`/`error_message`, per
        VerificationProviderPort's contract. Only genuinely unexpected
        programming errors propagate, and even those are caught safely one
        layer up by VerificationCoordinator.
        """

        started_at = self._clock()
        logger.info(
            "NeverBounce verification starting: subject_id={}, email={}",
            request.subject_id,
            _mask_email(request.value),
        )

        outcome = self._check(request.value)
        completed_at = self._clock()

        logger.info(
            "NeverBounce verification finished: subject_id={}, status={}",
            request.subject_id,
            outcome.status.value,
        )

        return VerificationResult(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=ContactType.EMAIL,
            value=request.value,
            status=outcome.status,
            confidence=None,
            reason=outcome.reason,
            error_message=outcome.error_message,
            started_at=started_at,
            completed_at=completed_at,
            raw_response=outcome.raw_response,
        )

    def _check(self, email: str) -> _CheckOutcome:
        """Call NeverBounce's single-check endpoint, retrying transient
        failures (timeouts, connection errors, 5xx responses,
        `throttle_triggered`, `temp_unavail`) up to
        `settings.max_retries` additional times.
        """

        url = f"{self._settings.base_url}{_CHECK_PATH}"
        params = {"key": self._settings.api_key, "email": email}
        attempts = self._settings.max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                response = self._http_client.get(
                    url, params=params, timeout=self._settings.timeout_seconds
                )
            except httpx.TimeoutException as exc:
                logger.warning(
                    "NeverBounce request timed out (attempt {}/{}): {}",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    return _CheckOutcome(
                        VerificationStatus.TIMEOUT, error_message=str(exc)
                    )
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue
            except httpx.RequestError as exc:
                logger.warning(
                    "NeverBounce request error (attempt {}/{}): {}",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    return _CheckOutcome(
                        VerificationStatus.ERROR, error_message=str(exc)
                    )
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code == 429:
                logger.warning(
                    "NeverBounce returned HTTP 429 (attempt {}/{})", attempt, attempts
                )
                if attempt == attempts:
                    return _CheckOutcome(
                        VerificationStatus.RATE_LIMITED,
                        error_message="HTTP 429 Too Many Requests",
                    )
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 500:
                logger.warning(
                    "NeverBounce returned HTTP {} (attempt {}/{})",
                    response.status_code,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    return _CheckOutcome(
                        VerificationStatus.ERROR,
                        error_message=f"HTTP {response.status_code}",
                    )
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 400:
                logger.info(
                    "NeverBounce returned HTTP {}; not retrying.",
                    response.status_code,
                )
                return _CheckOutcome(
                    VerificationStatus.ERROR,
                    error_message=f"HTTP {response.status_code}",
                )

            outcome = self._parse_body(response, attempt, attempts)
            if outcome is None:
                # A retryable body-level status (throttle_triggered/temp_unavail)
                # was seen but retries remain — loop again.
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue
            return outcome

        # Unreachable in practice (the loop always returns on its final
        # iteration), but keeps this method's return type honest.
        return _CheckOutcome(
            VerificationStatus.ERROR, error_message="Exhausted retries."
        )

    def _parse_body(
        self, response: httpx.Response, attempt: int, attempts: int
    ) -> _CheckOutcome | None:
        """Interpret one HTTP-200 NeverBounce response body.

        Returns:
            A terminal _CheckOutcome, or None if the body reports a
            retryable condition (`throttle_triggered`/`temp_unavail`) and
            attempts remain — the caller is responsible for sleeping and
            retrying in that case.
        """

        try:
            payload = response.json()
        except ValueError:
            return _CheckOutcome(
                VerificationStatus.ERROR,
                error_message="NeverBounce returned a non-JSON response body.",
            )

        api_status = payload.get("status")

        if api_status == "success":
            result = payload.get("result", "unknown")
            status = _RESULT_STATUS_MAP.get(result, VerificationStatus.UNKNOWN)
            reason = _RESULT_REASONS.get(
                result, f"NeverBounce reported an unrecognized result '{result}'."
            )
            return _CheckOutcome(status, reason=reason, raw_response=payload)

        if api_status in _RETRYABLE_API_STATUSES:
            logger.warning(
                "NeverBounce reported status='{}' (attempt {}/{})",
                api_status,
                attempt,
                attempts,
            )
            if attempt < attempts:
                return None
            return _CheckOutcome(
                _RETRYABLE_API_STATUSES[api_status],
                error_message=payload.get("message") or f"status={api_status}",
                raw_response=payload,
            )

        # auth_failure, general_failure, bad_referrer, or any other
        # unrecognized body-level status: a configuration/API problem a
        # retry cannot fix.
        logger.error("NeverBounce API error: status='{}'", api_status)
        return _CheckOutcome(
            VerificationStatus.ERROR,
            error_message=payload.get("message")
            or f"NeverBounce API error: {api_status}",
            raw_response=payload,
        )


def _mask_email(email: str) -> str:
    """A partially-masked form of `email`, safe to write to logs (e.g.
    "a***@example.com") without exposing the full address in plaintext log
    output."""

    local, _, domain = email.partition("@")
    if not domain or not local:
        return "***"
    return f"{local[0]}***@{domain}"
