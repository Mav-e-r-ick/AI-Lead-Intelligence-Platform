"""Shared HTTP fixtures for the NeverBounce provider's tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import httpx

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationRequest,
)


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def build_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """An httpx.Client whose requests are answered entirely by `handler`,
    never touching the real network."""

    return httpx.Client(transport=httpx.MockTransport(handler))


def success_body(result: str, **extra: Any) -> dict[str, Any]:
    """A NeverBounce `status: success` response body."""

    body: dict[str, Any] = {
        "status": "success",
        "result": result,
        "flags": [],
        "suggested_correction": "",
        "execution_time": 42,
    }
    body.update(extra)
    return body


def api_error_body(status: str, message: str = "an error occurred") -> dict[str, Any]:
    """A NeverBounce non-success response body (auth_failure,
    general_failure, bad_referrer, throttle_triggered, temp_unavail)."""

    return {"status": status, "message": message}


def make_request(
    value: str = "ada@example.com",
    subject_id: str = "twin-1",
    request_id: str = "req-1",
) -> VerificationRequest:
    return VerificationRequest(
        request_id=request_id,
        contact_type=ContactType.EMAIL,
        value=value,
        subject_id=subject_id,
        requested_at=fixed_clock(),
    )


def json_router(
    responses: Mapping[str, tuple[int, dict[str, Any]]]
) -> Callable[[httpx.Request], httpx.Response]:
    """A handler keyed by the request's `email` query parameter, returning
    the configured (status_code, json_body) pair, or a 404 for anything
    unlisted."""

    def handler(request: httpx.Request) -> httpx.Response:
        email = request.url.params.get("email", "")
        if email not in responses:
            return httpx.Response(404)
        status_code, body = responses[email]
        return httpx.Response(status_code, json=body)

    return handler
