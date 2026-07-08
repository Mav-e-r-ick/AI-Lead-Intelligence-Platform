"""Shared test fixtures for the Contact Verification Framework's tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from lead_intelligence.application.ports.verification_provider_port import (
    VerificationProviderPort,
)

ALL_CONTACT_TYPES: frozenset[ContactType] = frozenset(
    {ContactType.EMAIL, ContactType.PHONE}
)


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


class FakeVerificationProvider(VerificationProviderPort):
    """A fully scripted, in-memory VerificationProviderPort — stands in for
    a real provider (NeverBounce, ZeroBounce, Twilio Lookup, ...), none of
    which exist yet in Version 1.
    """

    def __init__(
        self,
        provider_id: str,
        display_name: str = "",
        supported_contact_types: frozenset[ContactType] = ALL_CONTACT_TYPES,
        handler: Callable[[VerificationRequest], VerificationResult] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name or provider_id
        self._supported_contact_types = supported_contact_types
        self._handler = handler
        self._raises = raises
        self.calls: list[VerificationRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def supported_contact_types(self) -> frozenset[ContactType]:
        return self._supported_contact_types

    def verify(self, request: VerificationRequest) -> VerificationResult:
        self.calls.append(request)
        if self._raises is not None:
            raise self._raises
        if self._handler is not None:
            return self._handler(request)
        return default_valid_result(self._provider_id, request)


def default_valid_result(
    provider_id: str, request: VerificationRequest
) -> VerificationResult:
    return VerificationResult(
        provider_id=provider_id,
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
