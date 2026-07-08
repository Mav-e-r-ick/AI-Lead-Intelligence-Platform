"""End-to-end unit tests for NeverBounceEmailProvider.verify(), using
httpx.MockTransport instead of any real network call."""

from __future__ import annotations

import httpx
import pytest

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationStatus,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.provider import (
    NeverBounceEmailProvider,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NeverBounceSettings,
)
from tests.unit.neverbounce.fixtures import (
    api_error_body,
    build_client,
    fixed_clock,
    json_router,
    make_request,
    success_body,
)


def _provider(
    handler, settings: NeverBounceSettings | None = None
) -> NeverBounceEmailProvider:
    return NeverBounceEmailProvider(
        settings=settings or NeverBounceSettings(api_key="test-key"),
        http_client=build_client(handler),
        clock=fixed_clock,
        sleep_fn=lambda seconds: None,
    )


class TestProviderIdentity:
    def test_provider_id(self) -> None:
        provider = _provider(lambda request: httpx.Response(404))
        assert provider.provider_id == "neverbounce"

    def test_display_name(self) -> None:
        provider = _provider(lambda request: httpx.Response(404))
        assert provider.display_name == "NeverBounce"

    def test_supports_only_email(self) -> None:
        provider = _provider(lambda request: httpx.Response(404))
        assert provider.supported_contact_types == frozenset({ContactType.EMAIL})

    def test_invalid_settings_raise_at_construction(self) -> None:
        with pytest.raises(ValueError):
            NeverBounceEmailProvider(settings=NeverBounceSettings(api_key=""))


class TestResultMapping:
    def test_valid_result_maps_to_valid_status(self) -> None:
        handler = json_router({"ada@example.com": (200, success_body("valid"))})
        provider = _provider(handler)

        result = provider.verify(make_request("ada@example.com"))

        assert result.status is VerificationStatus.VALID
        assert result.provider_id == "neverbounce"
        assert result.contact_type is ContactType.EMAIL
        assert result.value == "ada@example.com"
        assert result.error_message is None
        assert result.reason is not None

    def test_invalid_result_maps_to_invalid_status(self) -> None:
        handler = json_router({"bad@example.com": (200, success_body("invalid"))})
        provider = _provider(handler)

        result = provider.verify(make_request("bad@example.com"))

        assert result.status is VerificationStatus.INVALID

    def test_disposable_result_maps_to_risky_status(self) -> None:
        handler = json_router(
            {"temp@mailinator.com": (200, success_body("disposable"))}
        )
        provider = _provider(handler)

        result = provider.verify(make_request("temp@mailinator.com"))

        assert result.status is VerificationStatus.RISKY
        assert "disposable" in (result.reason or "").lower()

    def test_catchall_result_maps_to_risky_status(self) -> None:
        handler = json_router({"someone@catchall.com": (200, success_body("catchall"))})
        provider = _provider(handler)

        result = provider.verify(make_request("someone@catchall.com"))

        assert result.status is VerificationStatus.RISKY
        assert "catch-all" in (result.reason or "").lower()

    def test_unknown_result_maps_to_unknown_status(self) -> None:
        handler = json_router({"mystery@example.com": (200, success_body("unknown"))})
        provider = _provider(handler)

        result = provider.verify(make_request("mystery@example.com"))

        assert result.status is VerificationStatus.UNKNOWN

    def test_unrecognized_result_value_falls_back_to_unknown(self) -> None:
        handler = json_router(
            {"weird@example.com": (200, success_body("something_new"))}
        )
        provider = _provider(handler)

        result = provider.verify(make_request("weird@example.com"))

        assert result.status is VerificationStatus.UNKNOWN

    def test_raw_response_carries_full_payload(self) -> None:
        body = success_body("valid")
        handler = json_router({"ada@example.com": (200, body)})
        provider = _provider(handler)

        result = provider.verify(make_request("ada@example.com"))

        assert dict(result.raw_response) == body


class TestApiErrorMapping:
    def test_auth_failure_maps_to_error_and_is_not_retried(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                200, json=api_error_body("auth_failure", "Invalid API key")
            )

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="bad-key", max_retries=2)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.ERROR
        assert result.error_message == "Invalid API key"
        assert attempts["count"] == 1

    def test_general_failure_maps_to_error(self) -> None:
        handler = json_router(
            {"ada@example.com": (200, api_error_body("general_failure", "oops"))}
        )
        provider = _provider(handler)

        result = provider.verify(make_request("ada@example.com"))

        assert result.status is VerificationStatus.ERROR
        assert result.error_message == "oops"

    def test_bad_referrer_maps_to_error(self) -> None:
        handler = json_router(
            {"ada@example.com": (200, api_error_body("bad_referrer", "bad referrer"))}
        )
        provider = _provider(handler)

        result = provider.verify(make_request("ada@example.com"))

        assert result.status is VerificationStatus.ERROR

    def test_non_json_body_maps_to_error(self) -> None:
        provider = _provider(lambda request: httpx.Response(200, text="not json"))

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.ERROR


class TestThrottleAndTempUnavailable:
    def test_throttle_triggered_retried_then_rate_limited(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                200, json=api_error_body("throttle_triggered", "slow down")
            )

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=2)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.RATE_LIMITED
        assert attempts["count"] == 3  # 1 initial + 2 retries

    def test_throttle_triggered_succeeds_on_a_later_attempt(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                return httpx.Response(
                    200, json=api_error_body("throttle_triggered", "slow down")
                )
            return httpx.Response(200, json=success_body("valid"))

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=2)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.VALID
        assert attempts["count"] == 2

    def test_temp_unavail_retried_then_error(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                200, json=api_error_body("temp_unavail", "come back later")
            )

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=1)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.ERROR
        assert attempts["count"] == 2  # 1 initial + 1 retry


class TestHttpLevelFailures:
    def test_http_429_retried_then_rate_limited(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(429)

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=1)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.RATE_LIMITED
        assert attempts["count"] == 2

    def test_server_error_is_retried_and_succeeds(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                return httpx.Response(500)
            return httpx.Response(200, json=success_body("valid"))

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=2)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.VALID
        assert attempts["count"] == 2

    def test_server_error_exhausts_retries_then_error(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(503)

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=2)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.ERROR
        assert attempts["count"] == 3  # 1 initial + 2 retries

    def test_client_error_is_not_retried(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(400)

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=3)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.ERROR
        assert attempts["count"] == 1

    def test_timeout_is_retried_then_gives_up(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            raise httpx.ConnectTimeout("timed out", request=request)

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=1)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.TIMEOUT
        assert attempts["count"] == 2  # 1 initial + 1 retry

    def test_timeout_succeeds_on_a_later_attempt(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise httpx.ConnectTimeout("timed out", request=request)
            return httpx.Response(200, json=success_body("valid"))

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=2)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.VALID
        assert attempts["count"] == 2

    def test_connection_error_is_retried_then_error(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            raise httpx.ConnectError("connection refused", request=request)

        provider = _provider(
            handler, settings=NeverBounceSettings(api_key="k", max_retries=1)
        )

        result = provider.verify(make_request())

        assert result.status is VerificationStatus.ERROR
        assert attempts["count"] == 2


class TestResultTimestampsAndIdentity:
    def test_request_id_and_subject_id_are_carried_through(self) -> None:
        handler = json_router({"ada@example.com": (200, success_body("valid"))})
        provider = _provider(handler)

        result = provider.verify(
            make_request("ada@example.com", subject_id="twin-42", request_id="req-99")
        )

        assert result.request_id == "req-99"
        assert result.subject_id == "twin-42"

    def test_started_and_completed_at_use_injected_clock(self) -> None:
        handler = json_router({"ada@example.com": (200, success_body("valid"))})
        provider = _provider(handler)

        result = provider.verify(make_request("ada@example.com"))

        assert result.started_at == fixed_clock()
        assert result.completed_at == fixed_clock()

    def test_confidence_is_none(self) -> None:
        handler = json_router({"ada@example.com": (200, success_body("valid"))})
        provider = _provider(handler)

        result = provider.verify(make_request("ada@example.com"))

        assert result.confidence is None
