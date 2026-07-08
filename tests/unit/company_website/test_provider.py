"""End-to-end unit tests for CompanyWebsiteProvider.fetch(), using
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
from lead_intelligence.infrastructure.enrichment.company_website.provider import (
    CompanyWebsiteProvider,
)
from lead_intelligence.infrastructure.enrichment.company_website.settings import (
    CompanyWebsiteProviderSettings,
)
from tests.unit.company_website.fixtures import (
    HOMEPAGE_WITH_LEADERSHIP_LINK,
    HOMEPAGE_WITH_NO_LEADERSHIP_LINK,
    LEADERSHIP_PAGE_ONE_EXECUTIVE,
    LEADERSHIP_PAGE_TWO_EXECUTIVES,
    ROBOTS_DISALLOW_ALL,
    ROBOTS_DISALLOW_LEADERSHIP,
    build_client,
    path_router,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _request(
    url: str = "https://acme.com", company_name: str = "Acme"
) -> EnrichmentRequest:
    return EnrichmentRequest(
        request_id="req-1",
        subject_type=SubjectType.COMPANY,
        subject_id="company-1",
        known_attributes={fc.URL: url, fc.COMPANY_NAME: company_name},
        requested_at=_fixed_clock(),
    )


def _provider(
    handler,
    settings: CompanyWebsiteProviderSettings | None = None,
) -> CompanyWebsiteProvider:
    return CompanyWebsiteProvider(
        http_client=build_client(handler),
        settings=settings,
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )


def test_missing_url_returns_failure_without_any_http_call() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, text="")

    provider = _provider(handler)
    request = EnrichmentRequest(
        request_id="req-1",
        subject_type=SubjectType.COMPANY,
        subject_id="company-1",
        known_attributes={},
        requested_at=_fixed_clock(),
    )

    response = provider.fetch(request)

    assert response.status is EnrichmentStatus.FAILURE
    assert "known_attributes" in (response.error_message or "")
    assert calls == []


def test_successful_fetch_returns_observations_for_the_found_executive() -> None:
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE),
        }
    )
    provider = _provider(handler)

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    values = {(o.attribute, o.value) for o in response.observations}
    assert ("full_name", "Ada Lovelace") in values
    assert ("title", "Chief Executive Officer") in values
    assert ("leadership_page_url", "https://acme.com/leadership") in values
    assert all(o.provider_id == "company_website" for o in response.observations)
    assert all(o.subject_id == "company-1" for o in response.observations)


def test_observations_for_the_same_person_share_a_person_ref() -> None:
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE),
        }
    )
    provider = _provider(handler)

    response = provider.fetch(_request())

    person_refs = {o.raw_context["person_ref"] for o in response.observations}
    assert person_refs == {"leadership-0"}


def test_multiple_executives_get_distinct_person_refs() -> None:
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_TWO_EXECUTIVES),
        }
    )
    provider = _provider(handler)

    response = provider.fetch(_request())

    names_by_ref = {
        o.raw_context["person_ref"]: o.value
        for o in response.observations
        if o.attribute == "full_name"
    }
    assert names_by_ref == {
        "leadership-0": "Ada Lovelace",
        "leadership-1": "Grace Hopper",
    }


def test_no_leadership_link_found_returns_success_with_no_observations() -> None:
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_NO_LEADERSHIP_LINK),
        }
    )
    provider = _provider(handler)

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert response.observations == ()


def test_homepage_fetch_failure_returns_failure_status() -> None:
    handler = path_router(
        {"/robots.txt": httpx.Response(404), "/": httpx.Response(404)}
    )
    provider = _provider(handler)

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert response.error_message is not None
    assert response.observations == ()


def test_leadership_page_fetch_failure_returns_partial_status() -> None:
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(500),
        }
    )
    provider = _provider(
        handler, settings=CompanyWebsiteProviderSettings(max_retries=0)
    )

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.PARTIAL
    assert response.observations == ()


def test_robots_disallow_all_blocks_homepage_and_reports_success_with_no_calls_to_homepage() -> (
    None
):
    homepage_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_DISALLOW_ALL)
        homepage_calls.append(request.url.path)
        return httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK)

    provider = _provider(handler)

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert response.observations == ()
    assert homepage_calls == []


def test_robots_disallow_specific_page_skips_only_that_page() -> None:
    fetched_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched_paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_DISALLOW_LEADERSHIP)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK)
        return httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE)

    provider = _provider(handler)

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert response.observations == ()
    assert "/leadership" not in fetched_paths


def test_missing_robots_txt_defaults_to_allowed() -> None:
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE),
        }
    )
    provider = _provider(handler)

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert len(response.observations) > 0


def test_server_error_is_retried_and_succeeds_on_a_later_attempt() -> None:
    attempts = {"count": 0}

    def leadership_handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(500)
        return httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK)
        return leadership_handler(request)

    provider = _provider(
        handler, settings=CompanyWebsiteProviderSettings(max_retries=2)
    )

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.SUCCESS
    assert attempts["count"] == 2
    assert len(response.observations) > 0


def test_retries_are_exhausted_and_page_is_reported_as_failed() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK)
        attempts["count"] += 1
        return httpx.Response(500)

    provider = _provider(
        handler, settings=CompanyWebsiteProviderSettings(max_retries=2)
    )

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.PARTIAL
    assert attempts["count"] == 3  # 1 initial attempt + 2 retries


def test_client_error_is_not_retried() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK)
        attempts["count"] += 1
        return httpx.Response(404)

    provider = _provider(
        handler, settings=CompanyWebsiteProviderSettings(max_retries=3)
    )

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.PARTIAL
    assert attempts["count"] == 1


def test_timeout_is_retried_then_gives_up() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            attempts["count"] += 1
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, text="")

    provider = _provider(
        handler, settings=CompanyWebsiteProviderSettings(max_retries=1)
    )

    response = provider.fetch(_request())

    assert response.status is EnrichmentStatus.FAILURE
    assert attempts["count"] == 2  # 1 initial attempt + 1 retry


def test_cache_avoids_a_second_http_call_for_the_same_url() -> None:
    call_counts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        call_counts[request.url.path] = call_counts.get(request.url.path, 0) + 1
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK)
        return httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE)

    provider = _provider(handler)

    provider.fetch(_request())
    provider.fetch(_request())

    assert call_counts["/"] == 1
    assert call_counts["/leadership"] == 1


def test_bare_domain_known_attribute_is_normalized_to_https() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=HOMEPAGE_WITH_NO_LEADERSHIP_LINK)

    provider = _provider(handler)

    response = provider.fetch(_request(url="acme.com"))

    assert response.status is EnrichmentStatus.SUCCESS
    assert any(url.startswith("https://acme.com") for url in requested_urls)


def test_max_leadership_pages_setting_bounds_pages_fetched() -> None:
    homepage_with_many_links = """
    <html><body>
      <a href="/leadership-a">Leadership A</a>
      <a href="/leadership-b">Leadership B</a>
      <a href="/leadership-c">Leadership C</a>
    </body></html>
    """
    fetched_leadership_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, text=homepage_with_many_links)
        fetched_leadership_paths.append(request.url.path)
        return httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE)

    provider = _provider(
        handler, settings=CompanyWebsiteProviderSettings(max_leadership_pages=1)
    )

    provider.fetch(_request())

    assert len(fetched_leadership_paths) == 1


def test_invalid_settings_raise_at_construction() -> None:
    with pytest.raises(ValueError):
        CompanyWebsiteProvider(
            settings=CompanyWebsiteProviderSettings(timeout_seconds=0)
        )


def test_provider_metadata() -> None:
    provider = CompanyWebsiteProvider()

    assert provider.provider_id == "company_website"
    assert provider.display_name == "Company Website"
    assert provider.supported_subject_types == frozenset({SubjectType.COMPANY})
