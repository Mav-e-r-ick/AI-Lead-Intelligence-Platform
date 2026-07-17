"""Unit tests for NewsProvider, using a mocked httpx transport. No test
here makes a real network call."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SubjectType,
)
from lead_intelligence.infrastructure.search.news.provider import NewsProvider
from lead_intelligence.infrastructure.search.news.settings import NewsProviderSettings


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


def _provider(handler, **settings_overrides: object) -> NewsProvider:
    settings = NewsProviderSettings(
        api_key="key", search_engine_id="cx", **settings_overrides  # type: ignore[arg-type]
    )
    transport = httpx.MockTransport(handler)
    return NewsProvider(
        settings,
        http_client=httpx.Client(transport=transport),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def _payload(url: str = "https://www.reuters.com/business/x") -> dict:
    return {
        "items": [
            {
                "title": "Ada Lovelace named CEO of Acme",
                "link": url,
                "snippet": "Ada Lovelace was named CEO of Acme, Reuters reports.",
                "displayLink": "www.reuters.com",
            }
        ]
    }


def test_provider_id_and_display_name() -> None:
    provider = _provider(lambda request: httpx.Response(200, json={"items": []}))

    assert provider.provider_id == "news_search"
    assert provider.display_name == "News Search"


def test_supports_only_person_subject_type() -> None:
    provider = _provider(lambda request: httpx.Response(200, json={"items": []}))

    assert provider.supported_subject_types == frozenset({SubjectType.PERSON})


def test_every_query_is_restricted_to_trusted_domains() -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.params.get("q", ""))
        return httpx.Response(200, json={"items": []})

    provider = _provider(handler)

    provider.search(_request())

    assert captured
    for query in captured:
        assert "site:reuters.com" in query
        assert "site:bloomberg.com" in query
        assert "site:businesswire.com" in query


def test_no_name_yields_failure_without_any_request() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"items": []})

    provider = _provider(handler)

    response = provider.search(_request(known_attributes={}))

    assert response.status is EnrichmentStatus.FAILURE
    assert calls["count"] == 0


def test_successful_search_returns_results_with_reuters_confidence() -> None:
    provider = _provider(lambda request: httpx.Response(200, json=_payload()))

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.results) > 0
    assert response.results[0].source == "news_search"
    assert response.results[0].confidence == 0.94


def test_businesswire_result_gets_tier_2_confidence() -> None:
    provider = _provider(
        lambda request: httpx.Response(
            200, json=_payload("https://www.businesswire.com/news/home/x")
        )
    )

    response = provider.search(_request())

    assert response.results[0].confidence == 0.92


def test_every_query_failing_yields_failure_status() -> None:
    provider = _provider(lambda request: httpx.Response(500))

    response = provider.search(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert response.results == ()


def test_custom_trusted_domains_are_actually_used_in_the_query() -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.params.get("q", ""))
        return httpx.Response(200, json={"items": []})

    provider = _provider(handler, trusted_domains=("example-news.com",))

    provider.search(_request())

    assert all("site:example-news.com" in query for query in captured)
    assert all("site:reuters.com" not in query for query in captured)


def test_response_carries_request_and_subject_identifiers() -> None:
    provider = _provider(lambda request: httpx.Response(200, json=_payload()))

    response = provider.search(_request())

    assert response.provider_id == "news_search"
    assert response.request_id == "req-1"
    assert response.subject_id == "row:1"
