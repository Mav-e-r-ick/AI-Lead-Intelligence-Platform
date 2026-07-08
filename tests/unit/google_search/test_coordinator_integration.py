"""Integration test proving GoogleSearchProvider works through the real
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
from lead_intelligence.infrastructure.enrichment.google_search.provider import (
    GoogleSearchProvider,
)
from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    GoogleSearchProviderSettings,
)
from tests.unit.google_search.fixtures import (
    build_client,
    search_item,
    search_response_body,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_coordinator_runs_the_google_search_provider_and_collects_its_observations() -> (
    None
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=search_response_body(
                search_item("Ada Lovelace joins Acme", "https://example.com/a")
            ),
        )

    provider = GoogleSearchProvider(
        settings=GoogleSearchProviderSettings(
            api_key="k",
            search_engine_id="cx",
            query_templates=('"{name}" promotion',),
        ),
        http_client=build_client(handler),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )
    coordinator = EnrichmentCoordinator(
        ProviderRegistry([provider]), EnrichmentProfile(name="t"), clock=_fixed_clock
    )

    result = coordinator.enrich(
        SubjectType.PERSON,
        "person-1",
        known_attributes={
            fc.FIRST_NAME: "Ada",
            fc.LAST_NAME: "Lovelace",
            fc.COMPANY_NAME: "Acme Corp",
        },
    )

    assert result.metrics.providers_executed == 1
    assert result.metrics.providers_succeeded == 1
    titles = {o.value for o in result.observations if o.attribute == "web_mention"}
    assert titles == {"Ada Lovelace joins Acme"}


def test_coordinator_never_routes_a_company_request_to_the_google_search_provider() -> (
    None
):
    def unreachable_handler(request: object) -> object:
        raise AssertionError(
            "GoogleSearchProvider should never be called for a company request"
        )

    provider = GoogleSearchProvider(
        settings=GoogleSearchProviderSettings(api_key="k", search_engine_id="cx"),
        http_client=build_client(unreachable_handler),  # type: ignore[arg-type]
    )
    coordinator = EnrichmentCoordinator(
        ProviderRegistry([provider]), EnrichmentProfile(name="t"), clock=_fixed_clock
    )

    result = coordinator.enrich(SubjectType.COMPANY, "company-1", known_attributes={})

    assert result.metrics.providers_considered == 0
    assert result.observations == ()
