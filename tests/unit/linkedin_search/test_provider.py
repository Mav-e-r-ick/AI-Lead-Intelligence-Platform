"""Unit tests for LinkedInSearchProvider, using a mocked httpx transport.
No test here makes a real network call or touches linkedin.com."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
from lead_intelligence.infrastructure.search.linkedin.provider import (
    LinkedInSearchProvider,
)
from lead_intelligence.infrastructure.search.linkedin.settings import (
    LinkedInSearchProviderSettings,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _request(known_attributes: dict[str, str] | None = None) -> SearchRequest:
    return SearchRequest(
        request_id="req-1",
        subject_type=SubjectType.PERSON,
        subject_id="row:1",
        known_attributes=(
            known_attributes
            if known_attributes is not None
            else {"first_name": "Ada", "last_name": "Lovelace", "company_name": "Acme"}
        ),
        requested_at=_fixed_clock(),
    )


def _provider(handler) -> LinkedInSearchProvider:
    settings = LinkedInSearchProviderSettings(api_key="key", search_engine_id="cx")
    transport = httpx.MockTransport(handler)
    return LinkedInSearchProvider(
        settings,
        http_client=httpx.Client(transport=transport),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def _payload() -> dict:
    return {
        "items": [
            {
                "title": "Ada Lovelace - CEO - Acme | LinkedIn",
                "link": "https://www.linkedin.com/in/ada-lovelace",
                "snippet": "Ada Lovelace's profile on LinkedIn.",
                "displayLink": "www.linkedin.com",
            }
        ]
    }


def test_provider_id_and_display_name() -> None:
    provider = _provider(lambda request: httpx.Response(200, json={"items": []}))

    assert provider.provider_id == "linkedin_search"
    assert provider.display_name == "LinkedIn Search"


def test_supports_only_person_subject_type() -> None:
    provider = _provider(lambda request: httpx.Response(200, json={"items": []}))

    assert provider.supported_subject_types == frozenset({SubjectType.PERSON})


def test_every_request_is_restricted_to_linkedin_domain() -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(request.url.params))
        return httpx.Response(200, json={"items": []})

    provider = _provider(handler)

    provider.search(_request())

    assert captured  # at least one query was sent
    assert all(params.get("siteSearch") == "linkedin.com" for params in captured)


def test_no_name_yields_failure_without_any_request() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"items": []})

    provider = _provider(handler)

    response = provider.search(_request(known_attributes={}))

    assert response.status is EnrichmentStatus.FAILURE
    assert calls["count"] == 0


def test_successful_search_returns_results_with_linkedin_confidence() -> None:
    provider = _provider(lambda request: httpx.Response(200, json=_payload()))

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) > 0
    assert response.results[0].source == "linkedin_search"
    assert response.results[0].confidence == 0.98


def test_every_query_failing_yields_failure_status() -> None:
    provider = _provider(lambda request: httpx.Response(500))

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert response.results == ()


def test_response_carries_request_and_subject_identifiers() -> None:
    provider = _provider(lambda request: httpx.Response(200, json=_payload()))

    response = provider.search(_request())

    assert response.provider_id == "linkedin_search"
    assert response.request_id == "req-1"
    assert response.subject_id == "row:1"
