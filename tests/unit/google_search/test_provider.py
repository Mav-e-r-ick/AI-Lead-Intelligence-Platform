"""End-to-end unit tests for GoogleSearchProvider.fetch(), using
httpx.MockTransport instead of any real network call."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentStatus,
    SubjectType,
)
from lead_intelligence.infrastructure.enrichment.google_search.provider import (
    GoogleSearchProvider,
)
from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    GoogleSearchProviderSettings,
)
from tests.unit.google_search.fixtures import (
    build_client,
    json_query_router,
    search_item,
    search_response_body,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _request(
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    company_name: str | None = "Acme Corp",
    title: str | None = None,
) -> EnrichmentRequest:
    known_attributes = {fc.FIRST_NAME: first_name, fc.LAST_NAME: last_name}
    if company_name is not None:
        known_attributes[fc.COMPANY_NAME] = company_name
    if title is not None:
        known_attributes[fc.TITLE] = title
    return EnrichmentRequest(
        request_id="req-1",
        subject_type=SubjectType.PERSON,
        subject_id="person-1",
        known_attributes=known_attributes,
        requested_at=_fixed_clock(),
    )


def _provider(
    handler, settings: GoogleSearchProviderSettings | None = None
) -> GoogleSearchProvider:
    return GoogleSearchProvider(
        settings=settings
        or GoogleSearchProviderSettings(api_key="k", search_engine_id="cx"),
        http_client=build_client(handler),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )


class TestProviderIdentity:
    def test_provider_id(self) -> None:
        provider = _provider(lambda request: httpx.Response(404))
        assert provider.provider_id == "google_search"

    def test_display_name(self) -> None:
        provider = _provider(lambda request: httpx.Response(404))
        assert provider.display_name == "Google Search"

    def test_supports_only_person(self) -> None:
        provider = _provider(lambda request: httpx.Response(404))
        assert provider.supported_subject_types == frozenset({SubjectType.PERSON})

    def test_invalid_settings_raise_at_construction(self) -> None:
        with pytest.raises(ValueError):
            GoogleSearchProvider(
                settings=GoogleSearchProviderSettings(api_key="", search_engine_id="cx")
            )


class TestMissingInputs:
    def test_missing_name_returns_failure_without_any_http_call(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(200, json=search_response_body())

        provider = _provider(handler)
        request = EnrichmentRequest(
            request_id="req-1",
            subject_type=SubjectType.PERSON,
            subject_id="person-1",
            known_attributes={},
            requested_at=_fixed_clock(),
        )

        response = provider.fetch(request)

        assert response.status is EnrichmentStatus.FAILURE
        assert response.observations == ()
        assert calls == []

    def test_blank_name_returns_failure(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, json=search_response_body())
        )

        response = provider.fetch(_request(first_name="  ", last_name="  "))

        assert response.status is EnrichmentStatus.FAILURE


class TestSuccessfulSearch:
    def test_executes_one_query_per_default_template_with_company_known(self) -> None:
        queries_seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            queries_seen.append(request.url.params.get("q", ""))
            return httpx.Response(200, json=search_response_body())

        provider = _provider(handler)

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.SUCCESS
        assert len(queries_seen) == 6  # all 6 default templates apply (company known)

    def test_executes_fewer_queries_when_company_unknown(self) -> None:
        queries_seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            queries_seen.append(request.url.params.get("q", ""))
            return httpx.Response(200, json=search_response_body())

        provider = _provider(handler)

        response = provider.fetch(_request(company_name=None))

        assert response.status is EnrichmentStatus.SUCCESS
        assert len(queries_seen) == 5  # the "name + company" template is skipped

    def test_results_become_web_mention_observations(self) -> None:
        handler = json_query_router(
            {
                '"Ada Lovelace" "Acme Corp"': (
                    200,
                    search_response_body(
                        search_item(
                            "Ada Lovelace promoted to CTO",
                            "https://news.example.com/ada",
                            snippet="Acme Corp announced...",
                            display_link="news.example.com",
                            published_time="2024-05-01T00:00:00Z",
                        )
                    ),
                ),
                '"Ada Lovelace" promotion': (200, search_response_body()),
                '"Ada Lovelace" appointed': (200, search_response_body()),
                '"Ada Lovelace" joins': (200, search_response_body()),
                '"Ada Lovelace" resigned': (200, search_response_body()),
                '"Ada Lovelace" leadership': (200, search_response_body()),
            }
        )
        provider = _provider(handler)

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.SUCCESS
        assert len(response.observations) == 1
        observation = response.observations[0]
        assert observation.attribute == "web_mention"
        assert observation.value == "Ada Lovelace promoted to CTO"
        assert observation.source_url == "https://news.example.com/ada"
        assert observation.subject_id == "person-1"
        assert observation.provider_id == "google_search"
        assert observation.raw_context["snippet"] == "Acme Corp announced..."
        assert observation.raw_context["source_domain"] == "news.example.com"
        assert observation.raw_context["published_at"] == "2024-05-01T00:00:00Z"
        assert observation.raw_context["query"] == '"Ada Lovelace" "Acme Corp"'

    def test_no_results_across_all_queries_is_still_success(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, json=search_response_body())
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.SUCCESS
        assert response.observations == ()

    def test_multiple_results_per_query_all_become_observations(self) -> None:
        handler = json_query_router(
            {
                query: (
                    200,
                    search_response_body(
                        search_item(f"Result A for {query}", "https://a.example.com"),
                        search_item(f"Result B for {query}", "https://b.example.com"),
                    ),
                )
                for query in [
                    '"Ada Lovelace" "Acme Corp"',
                    '"Ada Lovelace" promotion',
                    '"Ada Lovelace" appointed',
                    '"Ada Lovelace" joins',
                    '"Ada Lovelace" resigned',
                    '"Ada Lovelace" leadership',
                ]
            }
        )
        provider = _provider(handler)

        response = provider.fetch(_request())

        assert len(response.observations) == 12


class TestRetryAndFailureHandling:
    def test_server_error_is_retried_and_succeeds(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                return httpx.Response(500)
            return httpx.Response(200, json=search_response_body())

        provider = _provider(
            handler,
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_retries=2,
                query_templates=('"{name}" promotion',),
            ),
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.SUCCESS
        assert attempts["count"] == 2

    def test_retries_exhausted_for_one_query_yields_partial(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.params.get("q", "")
            if query == '"Ada Lovelace" promotion':
                return httpx.Response(500)
            return httpx.Response(200, json=search_response_body())

        provider = _provider(
            handler,
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_retries=1,
                query_templates=('"{name}" promotion', '"{name}" joins'),
            ),
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.PARTIAL

    def test_every_query_failing_yields_failure(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(500),
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_retries=0,
                query_templates=('"{name}" promotion',),
            ),
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.FAILURE

    def test_client_error_is_not_retried(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(404)

        provider = _provider(
            handler,
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_retries=3,
                query_templates=('"{name}" promotion',),
            ),
        )

        provider.fetch(_request())

        assert attempts["count"] == 1

    def test_rate_limit_is_retried_then_gives_up(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(429)

        provider = _provider(
            handler,
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_retries=1,
                query_templates=('"{name}" promotion',),
            ),
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.FAILURE
        assert attempts["count"] == 2  # 1 initial + 1 retry

    def test_timeout_is_retried_then_gives_up(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            raise httpx.ConnectTimeout("timed out", request=request)

        provider = _provider(
            handler,
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_retries=1,
                query_templates=('"{name}" promotion',),
            ),
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.FAILURE
        assert attempts["count"] == 2

    def test_non_json_response_yields_failure(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(200, text="not json"),
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                query_templates=('"{name}" promotion',),
            ),
        )

        response = provider.fetch(_request())

        assert response.status is EnrichmentStatus.FAILURE


class TestCaching:
    def test_cache_avoids_a_second_http_call_for_the_same_query(self) -> None:
        call_counts: dict[str, int] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            query = request.url.params.get("q", "")
            call_counts[query] = call_counts.get(query, 0) + 1
            return httpx.Response(200, json=search_response_body())

        settings = GoogleSearchProviderSettings(
            api_key="k",
            search_engine_id="cx",
            query_templates=('"{name}" promotion',),
        )
        provider = _provider(handler, settings=settings)

        provider.fetch(_request())
        provider.fetch(_request())

        assert call_counts['"Ada Lovelace" promotion'] == 1

    def test_max_results_is_sent_as_num_param(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["num"] = request.url.params.get("num")
            return httpx.Response(200, json=search_response_body())

        provider = _provider(
            handler,
            settings=GoogleSearchProviderSettings(
                api_key="k",
                search_engine_id="cx",
                max_results=3,
                query_templates=('"{name}" promotion',),
            ),
        )

        provider.fetch(_request())

        assert captured["num"] == "3"
