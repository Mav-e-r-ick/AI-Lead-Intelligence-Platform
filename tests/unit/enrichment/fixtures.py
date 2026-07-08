"""Shared test fixtures for the Enrichment Provider Framework's tests."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ObservationCandidate,
    SubjectType,
)
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)

ALL_SUBJECT_TYPES: frozenset[SubjectType] = frozenset(
    {SubjectType.PERSON, SubjectType.COMPANY}
)


class FakeEnrichmentProvider(EnrichmentProviderPort):
    """A fully scripted, in-memory EnrichmentProviderPort — stands in for
    a real provider (Company Website, News, D&B, ...), none of which exist
    yet in Version 1.
    """

    def __init__(
        self,
        provider_id: str,
        display_name: str = "",
        supported_subject_types: frozenset[SubjectType] = ALL_SUBJECT_TYPES,
        handler: Callable[[EnrichmentRequest], EnrichmentResponse] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name or provider_id
        self._supported_subject_types = supported_subject_types
        self._handler = handler
        self._raises = raises
        self.calls: list[EnrichmentRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return self._supported_subject_types

    def fetch(self, request: EnrichmentRequest) -> EnrichmentResponse:
        self.calls.append(request)
        if self._raises is not None:
            raise self._raises
        if self._handler is not None:
            return self._handler(request)
        return default_success_response(self._provider_id, request)


def default_success_response(
    provider_id: str, request: EnrichmentRequest
) -> EnrichmentResponse:
    return EnrichmentResponse(
        provider_id=provider_id,
        request_id=request.request_id,
        subject_id=request.subject_id,
        status=EnrichmentStatus.SUCCESS,
        observations=(),
        error_message=None,
        started_at=request.requested_at,
        completed_at=request.requested_at,
    )


def make_observation(
    subject_id: str,
    attribute: str,
    value: str,
    provider_id: str,
    observed_at: datetime,
) -> ObservationCandidate:
    return ObservationCandidate(
        subject_id=subject_id,
        attribute=attribute,
        value=value,
        provider_id=provider_id,
        observed_at=observed_at,
    )
