"""Integration test proving the Executive Processing Pipeline works
end-to-end through real, unmodified modules: CompanyWebsiteProvider and
GoogleSearchProvider (both HTTP-mocked, never touching the real network),
a real EnrichmentCoordinator, ComparisonEngine, InflectionDetectionEngine,
VerificationCoordinator, and NeverBounceEmailProvider (also HTTP-mocked) —
all wired through the real ExecutiveProcessingOrchestrator, with no fakes
standing in for the orchestrator's own collaborators.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison import config as comparison_config
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.dto.models import RawRecord
from lead_intelligence.application.dto.verification_models import VerificationStatus
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)
from lead_intelligence.application.inflection import config as inflection_config
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.infrastructure.enrichment.company_website.provider import (
    CompanyWebsiteProvider,
)
from lead_intelligence.infrastructure.enrichment.google_search.provider import (
    GoogleSearchProvider,
)
from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    GoogleSearchProviderSettings,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.provider import (
    NeverBounceEmailProvider,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NeverBounceSettings,
)
from tests.unit.company_website.fixtures import (
    HOMEPAGE_WITH_LEADERSHIP_LINK,
    LEADERSHIP_PAGE_ONE_EXECUTIVE,
)
from tests.unit.company_website.fixtures import build_client as build_website_client
from tests.unit.company_website.fixtures import path_router
from tests.unit.google_search.fixtures import build_client as build_search_client
from tests.unit.google_search.fixtures import (
    json_query_router,
    search_item,
    search_response_body,
)
from tests.unit.neverbounce.fixtures import build_client as build_neverbounce_client
from tests.unit.neverbounce.fixtures import json_router as neverbounce_json_router
from tests.unit.neverbounce.fixtures import success_body as neverbounce_success_body


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _existing_record() -> CleanedLeadRecord:
    raw_record = RawRecord(row_number=1, sheet_name="Sheet1", values={})
    return CleanedLeadRecord(
        raw_record=raw_record,
        cleaned_values={
            fc.FIRST_NAME: "Ada",
            fc.LAST_NAME: "Lovelace",
            fc.TITLE: "Manager",
            fc.COMPANY_NAME: "Acme",
            fc.URL: "https://acme.com",
            fc.EMAIL: "ada@acme.com",
        },
        field_changes=(),
        warnings=(),
        execution_failures=(),
    )


def _build_orchestrator() -> ExecutiveProcessingOrchestrator:
    website_handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE),
        }
    )
    company_website_provider = CompanyWebsiteProvider(
        http_client=build_website_client(website_handler),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )

    search_handler = json_query_router(
        {
            '"Ada Lovelace" "Acme"': (
                200,
                search_response_body(
                    search_item(
                        "Ada Lovelace named CEO of Acme",
                        "https://news.example.com/ada",
                        snippet="Acme announced today that Ada Lovelace...",
                        display_link="news.example.com",
                    )
                ),
            ),
        }
    )
    google_search_provider = GoogleSearchProvider(
        settings=GoogleSearchProviderSettings(
            api_key="k",
            search_engine_id="cx",
            query_templates=('"{name}" "{company}"',),
        ),
        http_client=build_search_client(search_handler),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )

    enrichment_coordinator = EnrichmentCoordinator(
        ProviderRegistry([company_website_provider, google_search_provider]),
        EnrichmentProfile(name="integration-test"),
        clock=_fixed_clock,
    )

    comparison_engine = ComparisonEngine(
        comparison_config.default_profile(), clock=_fixed_clock
    )
    inflection_engine = InflectionDetectionEngine(
        InflectionRuleRegistry(ALL_RULES),
        inflection_config.default_profile(),
        clock=_fixed_clock,
    )

    neverbounce_handler = neverbounce_json_router(
        {"ada@acme.com": (200, neverbounce_success_body("valid"))}
    )
    neverbounce_provider = NeverBounceEmailProvider(
        settings=NeverBounceSettings(api_key="test-key"),
        http_client=build_neverbounce_client(neverbounce_handler),
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )
    verification_coordinator = VerificationCoordinator(
        [neverbounce_provider],
        VerificationProfile(name="integration-test"),
        clock=_fixed_clock,
    )

    return ExecutiveProcessingOrchestrator(
        enrichment_coordinator=enrichment_coordinator,
        comparison_engine=comparison_engine,
        inflection_engine=inflection_engine,
        verification_coordinator=verification_coordinator,
        clock=_fixed_clock,
    )


def test_full_pipeline_processes_one_executive_end_to_end() -> None:
    orchestrator = _build_orchestrator()

    report = orchestrator.process(_existing_record(), "person-1")

    assert report.status is ExecutiveProcessingStatus.SUCCESS
    assert report.executive_name == "Ada Lovelace"
    assert set(report.providers_executed) == {"company_website", "google_search"}
    assert len(report.observations_collected) >= 2

    assert report.comparison_result is not None
    title_comparison = next(
        fc_
        for fc_ in report.comparison_result.field_comparisons
        if fc_.field_name == "title"
    )
    assert title_comparison.new_value == "Chief Executive Officer"

    assert report.inflection_report is not None
    assert InflectionType.PROMOTION in report.inflection_report.detected_types

    assert report.verification_report is not None
    assert report.verification_report.provider_results[0].status is (
        VerificationStatus.VALID
    )

    assert report.stage_errors == ()
    assert report.duration_ms >= 0.0
