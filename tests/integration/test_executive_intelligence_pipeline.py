"""Integration test proving the FULL Executive Intelligence pipeline works
end-to-end through real, unmodified modules:

    Executive Record -> Identity Resolution -> Company Website Provider
    -> Browser Search Provider -> Search Extraction Engine
    -> combined ObservationCandidates -> Comparison -> Inflection
    -> Verification -> Final Executive Intelligence Report

Every module here is the real class — IdentityResolutionEngine (with an
in-memory candidate port, the only piece with no infrastructure adapter
yet), CompanyWebsiteProvider (HTTP-mocked), BrowserSearchProvider (with a
fake browser — never a real Chromium process), SearchExtractionEngine
(HTTP-mocked), ComparisonEngine, InflectionDetectionEngine,
VerificationCoordinator + NeverBounceEmailProvider (HTTP-mocked) — all
wired through the real ExecutiveProcessingOrchestrator. No test here
touches the real network or launches a real browser.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison import config as comparison_config
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveIntelligenceReport,
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.identity_resolution_models import (
    ResolutionDecision,
)
from lead_intelligence.application.dto.models import RawRecord
from lead_intelligence.application.dto.verification_models import VerificationStatus
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)
from lead_intelligence.application.identity_resolution import (
    config as identity_config,
)
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.application.inflection import config as inflection_config
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES
from lead_intelligence.application.search.config import SearchProfile
from lead_intelligence.application.search.coordinator import SearchCoordinator
from lead_intelligence.application.search.provider_registry import (
    SearchProviderRegistry,
)
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.infrastructure.enrichment.company_website.provider import (
    CompanyWebsiteProvider,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.provider import (
    NeverBounceEmailProvider,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NeverBounceSettings,
)
from lead_intelligence.infrastructure.search.browser.provider import (
    BrowserSearchProvider,
)
from lead_intelligence.infrastructure.search.extraction.engine import (
    SearchExtractionEngine,
)
from lead_intelligence.infrastructure.search.extraction.settings import (
    SearchExtractionSettings,
)
from tests.unit.browser_search.fixtures import (
    FakeBrowser,
    FakePage,
    build_settings as build_browser_settings,
)
from tests.unit.browser_search.fixtures import (
    build_http_client as build_robots_client,
)
from tests.unit.browser_search.fixtures import (
    result_container,
    robots_not_found_transport,
)
from tests.unit.company_website.fixtures import (
    HOMEPAGE_WITH_LEADERSHIP_LINK,
    LEADERSHIP_PAGE_ONE_EXECUTIVE,
)
from tests.unit.company_website.fixtures import build_client as build_website_client
from tests.unit.company_website.fixtures import path_router
from tests.unit.identity_resolution.fixtures import FakeIdentityCandidatePort
from tests.unit.neverbounce.fixtures import build_client as build_neverbounce_client
from tests.unit.neverbounce.fixtures import json_router as neverbounce_json_router
from tests.unit.neverbounce.fixtures import success_body as neverbounce_success_body
from tests.unit.search_extraction.fixtures import announcement_page
from tests.unit.search_extraction.fixtures import (
    build_http_client as build_extraction_client,
)
from tests.unit.search_extraction.fixtures import html_response

_NEWS_URL = "https://news.example.com/ada-promoted"


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _executive_record(
    first_name: str = "Ada", last_name: str = "Lovelace"
) -> CleanedLeadRecord:
    raw_record = RawRecord(row_number=1, sheet_name="Sheet1", values={})
    return CleanedLeadRecord(
        raw_record=raw_record,
        cleaned_values={
            fc.FIRST_NAME: first_name,
            fc.LAST_NAME: last_name,
            fc.TITLE: "Manager",
            fc.COMPANY_NAME: "Acme",
            fc.URL: "https://acme.com",
            fc.EMAIL: "ada@acme.com",
        },
        field_changes=(),
        warnings=(),
        execution_failures=(),
    )


def _build_full_orchestrator() -> ExecutiveProcessingOrchestrator:
    # Stage 1: Identity Resolution — real engine, in-memory candidate port
    # (the one collaborator with no infrastructure adapter yet).
    identity_engine = IdentityResolutionEngine(
        FakeIdentityCandidatePort(),
        identity_config.default_profile(),
        clock=_fixed_clock,
    )

    # Stage 2: Company Website Provider through the real
    # EnrichmentCoordinator, HTTP-mocked.
    website_handler = path_router(
        {
            "/robots.txt": httpx.Response(404),
            "/": httpx.Response(200, text=HOMEPAGE_WITH_LEADERSHIP_LINK),
            "/leadership": httpx.Response(200, text=LEADERSHIP_PAGE_ONE_EXECUTIVE),
        }
    )
    enrichment_coordinator = EnrichmentCoordinator(
        ProviderRegistry(
            [
                CompanyWebsiteProvider(
                    http_client=build_website_client(website_handler),
                    clock=_fixed_clock,
                    sleep_fn=lambda seconds: None,
                )
            ]
        ),
        EnrichmentProfile(name="integration"),
        clock=_fixed_clock,
    )

    # Stage 3: Browser Search Provider through the real SearchCoordinator —
    # a real BrowserSearchProvider driving a fake browser whose results
    # page links to the announcement article below.
    browser = FakeBrowser(
        page_factory=lambda: FakePage(
            containers=[
                result_container(
                    "Ada Lovelace named CTO of Acme Corp",
                    _NEWS_URL,
                    "Acme Corp announced today...",
                )
            ]
        )
    )
    browser_search_provider = BrowserSearchProvider(
        build_browser_settings(query_templates=('"{name}"',)),
        http_client=build_robots_client(robots_not_found_transport),
        browser_factory=lambda: browser,
        clock=_fixed_clock,
        sleep_fn=lambda seconds: None,
    )
    search_coordinator = SearchCoordinator(
        SearchProviderRegistry([browser_search_provider]),
        SearchProfile(name="integration"),
        clock=_fixed_clock,
    )

    # Stage 4: the real Search Extraction Engine, HTTP-mocked to serve the
    # announcement article the search "found."
    extraction_engine = SearchExtractionEngine(
        settings=SearchExtractionSettings(retry_backoff_seconds=0),
        http_client=build_extraction_client(
            pages={
                "/ada-promoted": html_response(
                    announcement_page(
                        headline="Ada Lovelace named CTO of Acme Corp",
                        body=(
                            "Acme Corp announced today that Ada Lovelace has "
                            "been appointed Chief Technology Officer of Acme."
                        ),
                    )
                )
            }
        ),
        clock=_fixed_clock,
    )

    # Stage 8: real VerificationCoordinator + NeverBounce, HTTP-mocked.
    neverbounce_handler = neverbounce_json_router(
        {"ada@acme.com": (200, neverbounce_success_body("valid"))}
    )
    verification_coordinator = VerificationCoordinator(
        [
            NeverBounceEmailProvider(
                settings=NeverBounceSettings(api_key="test-key"),
                http_client=build_neverbounce_client(neverbounce_handler),
                clock=_fixed_clock,
                sleep_fn=lambda seconds: None,
            )
        ],
        VerificationProfile(name="integration"),
        clock=_fixed_clock,
    )

    return ExecutiveProcessingOrchestrator(
        enrichment_coordinator=enrichment_coordinator,
        comparison_engine=ComparisonEngine(
            comparison_config.default_profile(), clock=_fixed_clock
        ),
        inflection_engine=InflectionDetectionEngine(
            InflectionRuleRegistry(ALL_RULES),
            inflection_config.default_profile(),
            clock=_fixed_clock,
        ),
        verification_coordinator=verification_coordinator,
        identity_resolution_engine=identity_engine,
        search_coordinator=search_coordinator,
        search_extraction_engine=extraction_engine,
        clock=_fixed_clock,
    )


class TestSingleExecutiveEndToEnd:
    def test_every_stage_contributes_to_the_report(self) -> None:
        orchestrator = _build_full_orchestrator()

        report = orchestrator.process(_executive_record(), "row:1")

        # Identity Resolution ran and decided (empty store -> new identity).
        assert report.identity_resolution_outcome is not None
        assert (
            report.identity_resolution_outcome.decision
            is ResolutionDecision.NEW_IDENTITY
        )

        # Both evidence paths executed.
        assert "company_website" in report.providers_executed
        assert "browser_search" in report.providers_executed

        # Observations were combined from BOTH sources: the company's own
        # leadership page and the extracted news article.
        provider_ids = {o.provider_id for o in report.observations_collected}
        assert "company_website" in provider_ids
        assert "search_extraction" in provider_ids

        # The extraction engine read the real announcement page's facts.
        extracted_titles = [
            o.value
            for o in report.observations_collected
            if o.provider_id == "search_extraction" and o.attribute == "title"
        ]
        assert extracted_titles == ["CTO"]

        # Comparison, Inflection, and Verification all ran on the combined
        # evidence.
        assert report.comparison_result is not None
        assert report.inflection_report is not None
        assert report.verification_report is not None
        assert (
            report.verification_report.provider_results[0].status
            is VerificationStatus.VALID
        )

        assert report.status is ExecutiveProcessingStatus.SUCCESS
        assert report.stage_errors == ()
        assert report.duration_ms >= 0.0


class TestBatchEndToEnd:
    def test_batch_produces_one_final_intelligence_report(self) -> None:
        orchestrator = _build_full_orchestrator()
        records = [
            (_executive_record(), "row:1"),
            (_executive_record(first_name="", last_name=""), "row:2"),  # no name
            (_executive_record(first_name="Grace", last_name="Hopper"), "row:3"),
        ]

        report = orchestrator.process_batch(records)

        assert isinstance(report, ExecutiveIntelligenceReport)
        assert len(report.executive_reports) == 3
        assert [r.subject_id for r in report.executive_reports] == [
            "row:1",
            "row:2",
            "row:3",
        ]

        # The nameless record failed; the batch continued past it.
        assert report.executive_reports[1].status is ExecutiveProcessingStatus.FAILED
        assert (
            report.executive_reports[2].status is not ExecutiveProcessingStatus.FAILED
        )

        statistics = report.statistics
        assert statistics.total_executives == 3
        assert statistics.failed == 1
        assert statistics.succeeded + statistics.partial == 2
        assert statistics.executives_with_errors >= 1
        assert statistics.execution_time_total_ms >= 0.0
        assert report.duration_ms >= 0.0
