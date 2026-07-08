"""Tests for EmailVerificationPort / PhoneVerificationPort's fixed
`supported_contact_types`."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from lead_intelligence.application.ports.verification_provider_port import (
    EmailVerificationPort,
    PhoneVerificationPort,
)


class _FakeEmailProvider(EmailVerificationPort):
    @property
    def provider_id(self) -> str:
        return "fake_email"

    @property
    def display_name(self) -> str:
        return "Fake Email Provider"

    def verify(self, request: VerificationRequest) -> VerificationResult:
        return VerificationResult(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=VerificationStatus.VALID,
            confidence=None,
            reason=None,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )


class _FakePhoneProvider(PhoneVerificationPort):
    @property
    def provider_id(self) -> str:
        return "fake_phone"

    @property
    def display_name(self) -> str:
        return "Fake Phone Provider"

    def verify(self, request: VerificationRequest) -> VerificationResult:
        return VerificationResult(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=VerificationStatus.VALID,
            confidence=None,
            reason=None,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )


class TestEmailVerificationPort:
    def test_supports_only_email(self) -> None:
        provider = _FakeEmailProvider()

        assert provider.supported_contact_types == frozenset({ContactType.EMAIL})

    def test_verify_returns_a_result(self) -> None:
        provider = _FakeEmailProvider()
        request = VerificationRequest(
            request_id="req-1",
            contact_type=ContactType.EMAIL,
            value="ada@example.com",
            subject_id="twin-1",
            requested_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )

        result = provider.verify(request)

        assert result.status is VerificationStatus.VALID
        assert result.provider_id == "fake_email"


class TestPhoneVerificationPort:
    def test_supports_only_phone(self) -> None:
        provider = _FakePhoneProvider()

        assert provider.supported_contact_types == frozenset({ContactType.PHONE})

    def test_verify_returns_a_result(self) -> None:
        provider = _FakePhoneProvider()
        request = VerificationRequest(
            request_id="req-1",
            contact_type=ContactType.PHONE,
            value="+15550100",
            subject_id="twin-1",
            requested_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )

        result = provider.verify(request)

        assert result.status is VerificationStatus.VALID
        assert result.provider_id == "fake_phone"
