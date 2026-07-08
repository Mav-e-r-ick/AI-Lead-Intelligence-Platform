"""Integration test proving CompanyWebsiteProvider works through the real
Enrichment Provider Framework (ProviderRegistry + EnrichmentCoordinator),
not just in isolation."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.enrichment_models import SubjectType
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.infrastructure.enrichment.company_website.provider import (
    CompanyWebsiteProvider,
)
from tests.unit.company_website.fixtures import (
    HOMEPAGE_WITH_LEADERSHIP_LINK,
    LEADERSHIP_PAGE_ONE_EXECUTIVE,
    build_client,
    path_router,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_coordinator_runs_the_company_website_provider_and_collects_its_observations() -> (
    None
):
    handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE),
        }
    )
    provider = CompanyWebsiteProvider(
        http_client=build_client(handler),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )
    coordinator = EnrichmentCoordinator(
        ProviderRegistry([provider]), EnrichmentProfile(name="t"), clock=_fixed_clock
    )

    result = coordinator.enrich(
        SubjectType.COMPANY,
        "company-1",
        known_attributes={fc.URL: "https://acme.com", fc.COMPANY_NAME: "Acme"},
    )

    assert result.metrics.providers_executed == 1
    assert result.metrics.providers_succeeded == 1
    names = {o.value for o in result.observations if o.attribute == "full_name"}
    assert names == {"Ada Lovelace"}


def test_coordinator_never_routes_a_person_request_to_the_company_website_provider() -> (
    None
):
    handler = path_router({})
    provider = CompanyWebsiteProvider(http_client=build_client(handler))
    coordinator = EnrichmentCoordinator(
        ProviderRegistry([provider]), EnrichmentProfile(name="t"), clock=_fixed_clock
    )

    result = coordinator.enrich(SubjectType.PERSON, "person-1", known_attributes={})

    assert result.metrics.providers_considered == 0
    assert result.observations == ()
