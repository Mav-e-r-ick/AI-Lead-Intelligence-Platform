#!/usr/bin/env python
"""Run the Executive Processing Orchestrator over a real Excel file and
export a per-executive results workbook plus a JSON processing report.

Usage:
    python run_pipeline.py sample.xlsx \
        [--sheet SHEET_NAME] \
        [--limit N] \
        [--output-dir .] \
        [--results-name results.xlsx] \
        [--report-name processing_report.json]

Outputs (relative to --output-dir, default the current directory):
    results.xlsx            One row per executive, the fields requested for
                             this run (name, company, per-stage yes/no and
                             counts, comparison/inflection/verification
                             outcomes, errors).
    processing_report.json  Batch summary: totals, success/website/search/
                             observation rates, inflection-type counts,
                             processing time, plus the same per-executive
                             detail as results.xlsx for machine consumers.
    logs/                   One timestamped log file for this run.

WHY THIS SCRIPT EXISTS, SEPARATE FROM scripts/run_evaluation.py:
run_evaluation.py already runs the (V1) Executive Processing Pipeline over
an Excel file, but it exports CSV + a differently-shaped JSON summary, and
it predates the orchestrator's Identity Resolution / Search Layer / Search
Extraction stages and process_batch() (Version 2). This script wires the
same already-built modules (Import Engine, Cleaning Engine,
ExecutiveProcessingOrchestrator, and application/evaluation/row_builder.py
for the fields it already knows how to flatten) into the exact
results.xlsx / processing_report.json / logs/ output shape requested for
this run, without changing run_evaluation.py's own contract for anything
that already depends on it. No new provider, no AI, no automation, no
redesign of any existing module — pure wiring plus output formatting.

WHY SEARCH RESULT / PAGE-FETCH COUNTS ARE CAPTURED VIA A WRAPPER, NOT A NEW
ExecutiveProcessingReport FIELD:
ExecutiveProcessingReport intentionally does not carry raw SearchResult
counts (see its own docstring) — only the ObservationCandidates that come
out the other side. Rather than modify that DTO, _CountingSearchExtraction
below wraps the real SearchExtractionEngine (satisfying the same
structural SearchExtractionPort the orchestrator already accepts) purely
to record how many SearchResults came in and how many pages were fetched
successfully, per subject_id, for this script's own report. It changes no
behavior — every call is delegated to the real engine unchanged.

WHY GOOGLE SEARCH, BROWSER SEARCH, AND EMAIL VERIFICATION ARE OPTIONAL HERE:
Each requires operator-supplied configuration (API credentials, or for
Browser Search an authorized search-engine target) that may not be present
in every environment this script runs in. Rather than fail the whole run
for missing configuration, this script logs a warning and proceeds without
that piece, exactly like scripts/run_evaluation.py already does for Google
Search and email verification.

WHY --dev-mode EXISTS, AND EXACTLY WHAT IT CHANGES:
`ProviderHealthTracker` (application/enrichment/provider_health.py,
reused unmodified by the Search Layer) trips a circuit breaker after 3
consecutive provider failures, regardless of *why* they failed — correct
in production, but counterproductive on a developer laptop where a
misconfigured local network (VPN, corporate proxy, firewall) can produce
several connection-level failures in a row that have nothing to do with
whether the target site itself is reachable in general. `--dev-mode`
(or PIPELINE_DEV_MODE=true) injects `_DevModeHealthTracker` — a thin
ProviderHealthTracker subclass, built entirely in this script — into both
EnrichmentCoordinator and SearchCoordinator via their existing, already
publicly injectable `health_tracker` constructor parameter. It overrides
only `record_failure()`: a failure whose message matches
`_is_network_policy_failure()` (an HTTP 403 at the connect/robots stage,
or any connection-level error — see that function's docstring) is a
no-op, so it never advances a provider's consecutive-failure streak. Any
other failure (404, a genuine 500, a timeout after retries) is passed
through to the real ProviderHealthTracker.record_failure() completely
unchanged — Development Mode never touches how a real website failure is
handled. Off by default; CompanyWebsiteProvider/CompanyCrawlerProvider/
PressReleaseProvider themselves are not modified beyond including the
failure reason in their existing error_message strings (see their own
provider.py docstrings).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

from loguru import logger

from lead_intelligence.application.cleaning.config import (
    default_profile as default_cleaning_profile,
)
from lead_intelligence.application.cleaning.pipeline import CleaningPipeline
from lead_intelligence.application.cleaning.rules import ALL_RULES as CLEANING_RULES
from lead_intelligence.application.comparison.config import (
    default_profile as default_comparison_profile,
)
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.comparison.resolvers import (
    resolve_company,
    resolve_title,
)
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
)
from lead_intelligence.application.dto.enrichment_models import (
    ObservationCandidate,
    ProviderHealth,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveIntelligenceReport,
    ExecutiveProcessingReport,
)
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.dto.search_models import SearchResult
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_health import (
    ProviderHealthTracker,
)
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.evaluation.row_builder import build_row
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)
from lead_intelligence.application.identity_resolution.config import (
    default_profile as default_identity_profile,
)
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.application.inflection.config import (
    default_profile as default_inflection_profile,
)
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES as INFLECTION_RULES
from lead_intelligence.application.messaging.message_generator import (
    generate_message_for_report,
)
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.application.search.config import (
    SearchProfile,
    SearchProviderConfiguration,
)
from lead_intelligence.application.search.coordinator import SearchCoordinator
from lead_intelligence.application.search.provider_registry import (
    SearchProviderRegistry,
)
from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.core.config import get_settings
from lead_intelligence.infrastructure.database.executive_repository import (
    ExecutiveRepository,
)
from lead_intelligence.infrastructure.database.session import (
    create_engine_from_settings,
    create_session_factory,
)
from lead_intelligence.infrastructure.database.base import Base
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
from lead_intelligence.infrastructure.importers.excel.excel_reader import (
    ExcelSourceReader,
)
from lead_intelligence.infrastructure.search.company_crawler.provider import (
    CompanyCrawlerProvider,
)
from lead_intelligence.infrastructure.search.extraction.engine import (
    SearchExtractionEngine,
)
from lead_intelligence.infrastructure.search.google.provider import GoogleSearchProvider
from lead_intelligence.infrastructure.search.google.settings import (
    GoogleSearchProviderSettings,
)
from lead_intelligence.infrastructure.search.linkedin.provider import (
    LinkedInSearchProvider,
)
from lead_intelligence.infrastructure.search.linkedin.settings import (
    LinkedInSearchProviderSettings,
)
from lead_intelligence.infrastructure.search.news.provider import NewsProvider
from lead_intelligence.infrastructure.search.news.settings import NewsProviderSettings
from lead_intelligence.infrastructure.search.press_release.provider import (
    PressReleaseProvider,
)

_SEARCH_EXTRACTION_PROVIDER_ID = "search_extraction"
_PAGE_ATTRIBUTE = "web_page"
_COMPANY_CRAWLER_PROVIDER_ID = "company_crawler"
_GOOGLE_WEB_SEARCH_PROVIDER_ID = "google_web_search"
_LINKEDIN_SEARCH_PROVIDER_ID = "linkedin_search"
_PRESS_RELEASE_PROVIDER_ID = "press_release"
_NEWS_SEARCH_PROVIDER_ID = "news_search"

#: Every provider the Federated Search redesign registers with
#: SearchCoordinator, in the fixed order this module reports them —
#: see `_build_search_collaborators`'s own docstring for why all five
#: always run (no fallback_only).
_FEDERATED_SEARCH_PROVIDER_IDS: tuple[str, ...] = (
    _COMPANY_CRAWLER_PROVIDER_ID,
    _GOOGLE_WEB_SEARCH_PROVIDER_ID,
    _LINKEDIN_SEARCH_PROVIDER_ID,
    _PRESS_RELEASE_PROVIDER_ID,
    _NEWS_SEARCH_PROVIDER_ID,
)


class _CountingSearchExtraction:
    """Wraps a real SearchExtractionEngine to record, per subject_id, how
    many SearchResults came in and how many pages were fetched
    successfully — purely observational, delegates every call unchanged.
    See module docstring for why this lives here instead of on
    ExecutiveProcessingReport."""

    def __init__(self, engine: SearchExtractionEngine) -> None:
        self._engine = engine
        self.results_seen: dict[str, int] = {}

    def extract(
        self, subject_id: str, search_results: Sequence[SearchResult]
    ) -> tuple[ObservationCandidate, ...]:
        self.results_seen[subject_id] = self.results_seen.get(subject_id, 0) + len(
            search_results
        )
        return self._engine.extract(subject_id, search_results)


#: Substrings CompanyWebsiteProvider/CompanyCrawlerProvider/PressReleaseProvider
#: now include in their error_message on a connection-level failure or an
#: HTTP 403 (see provider.py's _last_fetch_failure / HomepageUnreachable
#: handling), plus the specific Chromium network-error codes Playwright
#: surfaces for a connection that was never established (observed
#: directly, in this environment, driving a Playwright-based provider
#: through a policy-restricted proxy: net::ERR_TUNNEL_CONNECTION_FAILED).
#: Deliberately excludes generic/ambiguous codes like
#: net::ERR_TIMED_OUT, which can just as easily mean "the real site is
#: slow" as "the network path is blocked" — kept as an explicit,
#: documented list (not a guess at every possible network error) so
#: Development Mode's effect stays predictable.
_NETWORK_POLICY_MARKERS: tuple[str, ...] = (
    "HTTP 403",
    "connection error",
    "net::ERR_TUNNEL_CONNECTION_FAILED",
    "net::ERR_PROXY_CONNECTION_FAILED",
    "net::ERR_CONNECTION_REFUSED",
    "net::ERR_CONNECTION_RESET",
    "net::ERR_CONNECTION_CLOSED",
    "net::ERR_NAME_NOT_RESOLVED",
)


def _is_network_policy_failure(error_message: str | None) -> bool:
    """Whether `error_message` looks like a network/connectivity problem
    (a blocked outbound connection, DNS failure, or an HTTP 403 at the
    connect/robots stage) rather than the destination site itself
    genuinely failing (404, 500, a timeout after retries against a
    reachable host). Deliberately narrow: only the signatures provider.py
    actually emits for those cases (see _NETWORK_POLICY_MARKERS) — a real
    site returning some other 4xx, a 5xx after retries, or a plain
    timeout, is never matched here, so Development Mode cannot
    accidentally mask a genuine content-level failure.
    """

    if not error_message:
        return False
    return any(marker in error_message for marker in _NETWORK_POLICY_MARKERS)


class _DevModeHealthTracker(ProviderHealthTracker):
    """A ProviderHealthTracker that does not let a network-policy failure
    (see `_is_network_policy_failure`) advance a provider's
    consecutive-failure streak, so the circuit breaker in
    application/enrichment/provider_health.py never trips from that class
    of failure alone. Every other failure — and every success — is
    recorded exactly as the real ProviderHealthTracker.record_failure()
    already would. Only ever constructed when --dev-mode/PIPELINE_DEV_MODE
    is enabled; see this module's own docstring for the full rationale.
    """

    def record_failure(
        self, provider_id: str, at: datetime, error: str
    ) -> ProviderHealth:
        if _is_network_policy_failure(error):
            logger.info(
                "Development Mode: not counting a network-policy failure "
                "against '{}''s health: {}",
                provider_id,
                error,
            )
            return self.get(provider_id)
        return super().record_failure(provider_id, at, error)


class ProviderStatus(NamedTuple):
    """One line of the Provider Status Report: whether a given provider
    actually ran in this invocation, and why (or why not). Built at the
    same place each provider is constructed, from whatever configuration
    was actually found in the environment — never guessed or assumed."""

    display_name: str
    enabled: bool
    reason: str


def _build_enrichment_providers() -> tuple[list[EnrichmentProviderPort], list[ProviderStatus]]:
    providers: list[EnrichmentProviderPort] = [CompanyWebsiteProvider()]
    statuses = [
        ProviderStatus(
            "Company Website Provider (enrichment)",
            True,
            "no credentials required",
        )
    ]

    try:
        google_settings = GoogleSearchProviderSettings.from_env()
        google_settings.validate()
    except ValueError:
        logger.warning(
            "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID not configured; "
            "running without the Google Search Provider."
        )
        statuses.append(
            ProviderStatus(
                "Google Search Provider (enrichment)",
                False,
                "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID missing",
            )
        )
    else:
        providers.append(GoogleSearchProvider(settings=google_settings))
        statuses.append(
            ProviderStatus(
                "Google Search Provider (enrichment)",
                True,
                "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID configured",
            )
        )

    return providers, statuses


def _build_verification_coordinator() -> tuple[VerificationCoordinator | None, list[ProviderStatus]]:
    try:
        neverbounce_settings = NeverBounceSettings.from_env()
        neverbounce_settings.validate()
    except ValueError:
        logger.warning(
            "NEVERBOUNCE_API_KEY not configured; running without email verification."
        )
        return None, [
            ProviderStatus(
                "NeverBounce Email Verification", False, "NEVERBOUNCE_API_KEY missing"
            )
        ]

    provider = NeverBounceEmailProvider(settings=neverbounce_settings)
    coordinator = VerificationCoordinator(
        [provider], VerificationProfile(name="run_pipeline")
    )
    return coordinator, [
        ProviderStatus(
            "NeverBounce Email Verification", True, "NEVERBOUNCE_API_KEY configured"
        )
    ]


def _build_search_collaborators(
    dev_mode: bool,
) -> tuple[SearchCoordinator | None, _CountingSearchExtraction | None, list[ProviderStatus]]:
    """The Federated Search redesign's SearchCoordinator wiring: every
    applicable provider runs on *every* request — no `fallback_only`, no
    "first provider wins" (see `application/search/coordinator.py`'s own
    module docstring for why that's now a merge/dedup/confidence-rank
    step instead). CompanyCrawlerProvider and PressReleaseProvider crawl
    the executive's own company website (no authorization decision to
    make, so both always run — same reasoning
    `CompanyCrawlerProviderSettings`'s own docstring already gives).
    GoogleSearchProvider, LinkedInSearchProvider, and NewsProvider all
    share one Google Custom Search API credential
    (`GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` — see
    `infrastructure/search/google/settings.py`'s module docstring for
    why); if it isn't configured, all three are skipped together (one
    missing credential means none of the three can call the API at all),
    and the run proceeds with the two crawler-based providers alone.
    """

    health_tracker = _DevModeHealthTracker() if dev_mode else ProviderHealthTracker()

    providers: list[SearchProviderPort] = [
        CompanyCrawlerProvider(),
        PressReleaseProvider(),
    ]
    provider_configurations: dict[str, SearchProviderConfiguration] = {
        _COMPANY_CRAWLER_PROVIDER_ID: SearchProviderConfiguration(),
        _PRESS_RELEASE_PROVIDER_ID: SearchProviderConfiguration(),
    }
    statuses = [
        ProviderStatus(
            "Company Crawler Provider (search)", True, "no credentials required"
        ),
        ProviderStatus(
            "Press Release Provider (search)", True, "no credentials required"
        ),
    ]

    try:
        google_settings = GoogleSearchProviderSettings.from_env()
        google_settings.validate()
    except ValueError:
        logger.warning(
            "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID not configured; "
            "running without GoogleSearchProvider, LinkedInSearchProvider, "
            "or NewsProvider (all three share this one Google Custom Search "
            "credential). CompanyCrawlerProvider and PressReleaseProvider "
            "still run."
        )
        reason = "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID missing"
        statuses.append(ProviderStatus("Google Search Provider (search)", False, reason))
        statuses.append(ProviderStatus("LinkedIn Search Provider (search)", False, reason))
        statuses.append(ProviderStatus("News Provider (search)", False, reason))
    else:
        providers.append(GoogleSearchProvider(google_settings))
        provider_configurations[_GOOGLE_WEB_SEARCH_PROVIDER_ID] = (
            SearchProviderConfiguration()
        )

        providers.append(
            LinkedInSearchProvider(LinkedInSearchProviderSettings.from_env())
        )
        provider_configurations[_LINKEDIN_SEARCH_PROVIDER_ID] = (
            SearchProviderConfiguration()
        )

        providers.append(NewsProvider(NewsProviderSettings.from_env()))
        provider_configurations[_NEWS_SEARCH_PROVIDER_ID] = SearchProviderConfiguration()

        reason = "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID configured"
        statuses.append(ProviderStatus("Google Search Provider (search)", True, reason))
        statuses.append(ProviderStatus("LinkedIn Search Provider (search)", True, reason))
        statuses.append(ProviderStatus("News Provider (search)", True, reason))

    coordinator = SearchCoordinator(
        SearchProviderRegistry(providers),
        SearchProfile(
            name="run_pipeline",
            provider_configurations=provider_configurations,
        ),
        health_tracker=health_tracker,
    )
    extraction = _CountingSearchExtraction(SearchExtractionEngine())
    return coordinator, extraction, statuses


def _build_executive_repository() -> ExecutiveRepository:
    """The one durable store this run reads/writes: real database
    (whatever DATABASE_URL is configured, defaulting to a local SQLite
    file — see core/config.py's Settings.database_url) so identity
    matching has real previously-known executives to compare against
    across separate runs, and so a detected change actually updates the
    database, per the business requirement."""

    settings = get_settings()
    engine = create_engine_from_settings(settings)
    Base.metadata.create_all(engine)
    return ExecutiveRepository(create_session_factory(engine))


def build_orchestrator(
    dev_mode: bool = False,
    repository: ExecutiveRepository | None = None,
) -> tuple[ExecutiveProcessingOrchestrator, _CountingSearchExtraction | None, list[ProviderStatus]]:
    """Wire real infrastructure into an ExecutiveProcessingOrchestrator.

    Every provider that needs external credentials (Google Custom Search,
    NeverBounce) is only constructed if its settings validate against the
    real environment; otherwise it's left out and the run proceeds with
    whatever providers are actually available (see `_build_enrichment_providers`,
    `_build_search_collaborators`, `_build_verification_coordinator`) — no
    provider being unavailable can fail this function or the run. The
    third return value is the full Provider Status Report: one
    ProviderStatus per provider this call considered, enabled or not.

    Args:
        dev_mode: When True, both EnrichmentCoordinator and
            SearchCoordinator get a _DevModeHealthTracker instead of the
            real ProviderHealthTracker — see this module's own docstring
            ("WHY --dev-mode EXISTS") for exactly what that changes.
        repository: The ExecutiveRepository backing Identity Resolution's
            candidate lookups. Defaults to `_build_executive_repository()`
            (the real, configured database); tests inject an isolated one.
    """

    if dev_mode:
        logger.warning(
            "Development Mode is ON: network-policy failures (see "
            "_is_network_policy_failure) will not mark a provider unhealthy. "
            "Real website failures are unaffected."
        )

    enrichment_health_tracker = (
        _DevModeHealthTracker() if dev_mode else ProviderHealthTracker()
    )
    enrichment_providers, enrichment_statuses = _build_enrichment_providers()
    enrichment_coordinator = EnrichmentCoordinator(
        ProviderRegistry(enrichment_providers),
        EnrichmentProfile(name="run_pipeline"),
        health_tracker=enrichment_health_tracker,
    )
    comparison_engine = ComparisonEngine(default_comparison_profile())
    inflection_engine = InflectionDetectionEngine(
        InflectionRuleRegistry(INFLECTION_RULES), default_inflection_profile()
    )
    search_coordinator, search_extraction, search_statuses = _build_search_collaborators(
        dev_mode
    )
    identity_engine = IdentityResolutionEngine(
        repository or _build_executive_repository(), default_identity_profile()
    )
    verification_coordinator, verification_statuses = _build_verification_coordinator()

    orchestrator = ExecutiveProcessingOrchestrator(
        enrichment_coordinator=enrichment_coordinator,
        comparison_engine=comparison_engine,
        inflection_engine=inflection_engine,
        verification_coordinator=verification_coordinator,
        identity_resolution_engine=identity_engine,
        search_coordinator=search_coordinator,
        search_extraction_engine=search_extraction,
    )
    provider_statuses = enrichment_statuses + search_statuses + verification_statuses
    return orchestrator, search_extraction, provider_statuses


def _pages_fetched(report: ExecutiveProcessingReport) -> int:
    return sum(
        1
        for observation in report.observations_collected
        if observation.provider_id == _SEARCH_EXTRACTION_PROVIDER_ID
        and observation.attribute == _PAGE_ATTRIBUTE
    )


def _current_field_value(
    comparison_result: ComparisonResult | None, field_name: str, fallback: str | None
) -> str | None:
    """The most up-to-date value for `field_name`: the newly observed
    value if Comparison found one (CHANGED/NEW), otherwise `fallback`
    (the existing record's own value).

    WHY THIS EXISTS: an outreach message must describe the executive's
    *current* situation, not the one being replaced. Building it from the
    existing record's own cleaned_values alone (ignoring what Comparison
    just detected) would draft a promotion message that names the
    executive's *old* title — technically true a moment ago, actively
    wrong and confusing once sent.
    """

    if comparison_result is None:
        return fallback
    for comparison in comparison_result.field_comparisons:
        if comparison.field_name != field_name:
            continue
        if comparison.status in (ComparisonStatus.CHANGED, ComparisonStatus.NEW):
            return comparison.new_value or fallback
    return fallback


def _build_result_row(
    report: ExecutiveProcessingReport,
    cleaned_values: Mapping[str, Any],
    search_results_found: int,
) -> dict:
    row = build_row(report, cleaned_values)
    # Which of the five federated Search Layer providers actually ran for
    # this executive (see _build_search_collaborators) — replaces the old
    # single-provider "Browser Search Performed (Yes/No)" column, since
    # there is no longer one primary provider to report on.
    executed_search_providers = ", ".join(
        provider_id
        for provider_id in _FEDERATED_SEARCH_PROVIDER_IDS
        if provider_id in report.providers_executed
    )
    outreach_message = generate_message_for_report(
        report.inflection_report,
        row.executive_name or "",
        _current_field_value(
            report.comparison_result, "company", resolve_company(cleaned_values)
        ),
        _current_field_value(
            report.comparison_result, "title", resolve_title(cleaned_values)
        ),
    )
    return {
        "Executive Name": row.executive_name,
        "Company": row.company,
        "Company Website Found (Yes/No)": (
            "Yes" if row.company_website_results_found > 0 else "No"
        ),
        "Search Providers Executed": executed_search_providers,
        "Search Results Found": search_results_found,
        "Pages Successfully Fetched": _pages_fetched(report),
        "ObservationCandidates Extracted": row.observations_collected,
        "Comparison Result": row.comparison_summary,
        "Inflection Detected": row.inflections_detected,
        "Outreach Message": outreach_message or "",
        "Contact Verification Status": row.verification_status,
        "Errors (if any)": row.errors or "",
    }


def _summary(
    intelligence_report: ExecutiveIntelligenceReport,
    rows: list[dict],
    database_fields_updated: int,
) -> dict:
    total = intelligence_report.statistics.total_executives
    website_found = sum(
        1 for row in rows if row["Company Website Found (Yes/No)"] == "Yes"
    )
    search_performed = sum(
        1 for row in rows if row["Search Providers Executed"]
    )
    observations_extracted = sum(
        1 for row in rows if row["ObservationCandidates Extracted"] > 0
    )
    inflection_counts: Counter[str] = Counter()
    for report in intelligence_report.executive_reports:
        if report.inflection_report is None:
            continue
        for inflection_type in report.inflection_report.detected_types:
            inflection_counts[inflection_type.value] += 1

    identity_matched = sum(
        1
        for report in intelligence_report.executive_reports
        if report.identity_resolution_outcome is not None
        and report.identity_resolution_outcome.decision.value == "auto_merge"
    )
    identity_new = sum(
        1
        for report in intelligence_report.executive_reports
        if report.identity_resolution_outcome is not None
        and report.identity_resolution_outcome.decision.value == "new_identity"
    )

    def _rate(numerator: int) -> float:
        return round((numerator / total) * 100, 1) if total else 0.0

    return {
        "Total Executives Processed": total,
        "Success Rate": _rate(intelligence_report.statistics.succeeded),
        "Website Success Rate": _rate(website_found),
        "Search Success Rate": _rate(search_performed),
        "Observation Extraction Rate": _rate(observations_extracted),
        "Identity Matched (existing executive)": identity_matched,
        "Identity New (first time seen)": identity_new,
        "Number of Promotions": inflection_counts[InflectionType.PROMOTION.value],
        "Number of Company Changes": inflection_counts[
            InflectionType.COMPANY_CHANGE.value
        ],
        "Number of Possible Resignations": inflection_counts[
            InflectionType.POSSIBLE_RESIGNATION.value
        ],
        "Number of Contact Changes": inflection_counts[
            InflectionType.CONTACT_INFO_CHANGED.value
        ],
        "Outreach Messages Generated": sum(
            1 for row in rows if row["Outreach Message"]
        ),
        "Database Fields Updated": database_fields_updated,
        "Processing Time (ms)": round(intelligence_report.duration_ms, 1),
    }


def _write_results_xlsx(rows: list[dict], path: Path) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Results"
    if rows:
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row[header] for header in headers])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _write_processing_report_json(
    summary: dict,
    rows: list[dict],
    source_path: str,
    sheet_name: str | None,
    provider_statuses: list[ProviderStatus],
    path: Path,
) -> None:
    payload = {
        "source_file": source_path,
        "sheet": sheet_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "provider_status": [status._asdict() for status in provider_statuses],
        "executives": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def _configure_run_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(
        log_dir / "run_pipeline_{time:YYYYMMDD_HHMMSS}.log",
        level="INFO",
        rotation=None,
    )


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _print_provider_status_report(statuses: list[ProviderStatus]) -> None:
    """Log the Provider Status Report: every provider this run considered,
    whether it actually ran, and why — so it's obvious at a glance which
    optional API keys are missing and which providers picked up the slack.
    """

    enabled = [status for status in statuses if status.enabled]
    disabled = [status for status in statuses if not status.enabled]

    lines = ["", "=" * 60, "Provider Status Report", "=" * 60]
    lines.append(f"Enabled ({len(enabled)}):")
    for status in enabled:
        lines.append(f"  [ENABLED]  {status.display_name} — {status.reason}")
    lines.append(f"Disabled ({len(disabled)}):")
    for status in disabled:
        lines.append(f"  [DISABLED] {status.display_name} — {status.reason}")
    lines.append("=" * 60)

    logger.info("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel_path", help="Path to the .xlsx file of executives.")
    parser.add_argument(
        "--sheet", default=None, help="Sheet name to read (default: auto-selected)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N cleaned records (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("PIPELINE_OUTPUT_DIR", "."),
        help=(
            "Directory to write results.xlsx / processing_report.json / logs/ "
            "into. Defaults to the PIPELINE_OUTPUT_DIR environment variable, "
            "or the current directory."
        ),
    )
    parser.add_argument("--results-name", default="results.xlsx")
    parser.add_argument("--report-name", default="processing_report.json")
    parser.add_argument(
        "--dev-mode",
        action="store_true",
        default=_env_flag("PIPELINE_DEV_MODE"),
        help=(
            "Development Mode: a network-policy failure (see "
            "_is_network_policy_failure) does not mark a provider unhealthy. "
            "Real website failures are unaffected. Defaults to the "
            "PIPELINE_DEV_MODE environment variable."
        ),
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir)
    _configure_run_logging(output_dir / "logs")

    logger.info("Importing {} (sheet={})", args.excel_path, args.sheet or "auto")
    source_reader = ExcelSourceReader(args.excel_path, sheet_name=args.sheet)
    dataset = ImportDatasetUseCase(source_reader).execute(args.sheet)
    logger.info("Imported {} raw record(s).", len(dataset.records))

    cleaning_pipeline = CleaningPipeline(CLEANING_RULES, default_cleaning_profile())
    cleaning_result = CleanDatasetUseCase(cleaning_pipeline).execute(dataset)
    cleaned_records: list[CleanedLeadRecord] = list(
        cleaning_result.cleaned_dataset.cleaned_records
    )
    logger.info("Cleaned {} record(s).", len(cleaned_records))

    if args.limit is not None:
        cleaned_records = cleaned_records[: args.limit]
    logger.info(
        "Processing {} record(s) through the orchestrator.", len(cleaned_records)
    )

    repository = _build_executive_repository()
    orchestrator, search_extraction, provider_statuses = build_orchestrator(
        dev_mode=args.dev_mode, repository=repository
    )
    batch = [
        (record, f"row:{record.raw_record.row_number}") for record in cleaned_records
    ]
    intelligence_report = orchestrator.process_batch(batch)

    rows = []
    database_updates = 0
    for record, (existing_record, subject_id) in zip(cleaned_records, batch):
        report = next(
            r
            for r in intelligence_report.executive_reports
            if r.subject_id == subject_id
        )
        search_results_found = (
            search_extraction.results_seen.get(subject_id, 0)
            if search_extraction is not None
            else 0
        )
        rows.append(
            _build_result_row(report, record.cleaned_values, search_results_found)
        )

        # Persistence: write back whatever Comparison detected as
        # CHANGED/NEW, and stamp the strongest detected inflection, onto
        # this executive's existing database row (a no-op if this
        # executive has never been seen before — there's nothing to
        # update yet). Only *after* that does this executive's own
        # baseline get recorded/confirmed, so Identity Resolution (which
        # already ran, inside process_batch above) was matched against
        # whatever the database looked like *before* this run started,
        # never against a row this same run just inserted for itself.
        database_updates += repository.apply_changes(
            subject_id, report.comparison_result, report.inflection_report
        )
        repository.ensure_baseline(subject_id, record.cleaned_values)

    summary = _summary(intelligence_report, rows, database_updates)

    results_path = output_dir / args.results_name
    report_path = output_dir / args.report_name
    _write_results_xlsx(rows, results_path)
    _write_processing_report_json(
        summary, rows, args.excel_path, args.sheet, provider_statuses, report_path
    )

    logger.info(
        "Run complete: {} executive(s), {:.1f}% success rate. " "results={} report={}",
        summary["Total Executives Processed"],
        summary["Success Rate"],
        results_path,
        report_path,
    )
    _print_provider_status_report(provider_statuses)
    return 0


if __name__ == "__main__":
    sys.exit(main())
