"""Shared test fixtures for the Search Layer's tests."""

from __future__ import annotations

from typing import Callable

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SearchResponse,
    SubjectType,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort

ALL_SUBJECT_TYPES: frozenset[SubjectType] = frozenset(
    {SubjectType.PERSON, SubjectType.COMPANY}
)


class FakeSearchProvider(SearchProviderPort):
    """A fully scripted, in-memory SearchProviderPort — stands in for a
    real provider (BrowserSearchProvider, a future Bing/Brave/SerpAPI/...
    provider) in tests that only care about coordination behavior.
    """

    def __init__(
        self,
        provider_id: str,
        display_name: str = "",
        supported_subject_types: frozenset[SubjectType] = ALL_SUBJECT_TYPES,
        handler: Callable[[SearchRequest], SearchResponse] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name or provider_id
        self._supported_subject_types = supported_subject_types
        self._handler = handler
        self._raises = raises
        self.calls: list[SearchRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return self._supported_subject_types

    def search(self, request: SearchRequest) -> SearchResponse:
        self.calls.append(request)
        if self._raises is not None:
            raise self._raises
        if self._handler is not None:
            return self._handler(request)
        return default_success_response(self._provider_id, request)


def default_success_response(
    provider_id: str, request: SearchRequest
) -> SearchResponse:
    return SearchResponse(
        provider_id=provider_id,
        request_id=request.request_id,
        subject_id=request.subject_id,
        status=EnrichmentStatus.SUCCESS,
        results=(),
        error_message=None,
        started_at=request.requested_at,
        completed_at=request.requested_at,
    )
