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

WHY IDENTITY RESOLUTION IS NOT WIRED IN HERE:
No concrete IdentityCandidatePort infrastructure adapter exists yet (no
identity persistence) — the orchestrator's identity_resolution_engine
parameter is optional for exactly this reason. This script leaves it
unset, the same as every other caller until that adapter exists.

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
handled. Off by default; CompanyWebsiteProvider/BrowserSearchProvider
themselves are not modified beyond including the failure reason in their
existing error_message strings (see their own provider.py docstrings).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
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
from lead_intelligence.application.inflection.config import (
    default_profile as default_inflection_profile,
)
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES as INFLECTION_RULES
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.application.search.config import (
    default_profile as default_search_profile,
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
from lead_intelligence.infrastructure.search.browser.provider import (
    BrowserSearchProvider,
)
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)
from lead_intelligence.infrastructure.search.extraction.engine import (
    SearchExtractionEngine,
)

_SEARCH_EXTRACTION_PROVIDER_ID = "search_extraction"
_PAGE_ATTRIBUTE = "web_page"
_BROWSER_SEARCH_PROVIDER_ID = "browser_search"


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


#: Substrings CompanyWebsiteProvider/BrowserSearchProvider now include in
#: their error_message on a connection-level failure or an HTTP 403 (see
#: provider.py's _last_fetch_failure / _last_query_failure), plus the
#: specific Chromium network-error codes Playwright surfaces for a
#: connection that was never established (observed directly, in this
#: environment, driving BrowserSearchProvider against a real search
#: engine through a policy-restricted proxy: net::ERR_TUNNEL_CONNECTION_
#: FAILED). Deliberately excludes generic/ambiguous codes like
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


def _build_enrichment_providers() -> list[EnrichmentProviderPort]:
    providers: list[EnrichmentProviderPort] = [CompanyWebsiteProvider()]

    try:
        google_settings = GoogleSearchProviderSettings.from_env()
        google_settings.validate()
    except ValueError:
        logger.warning(
            "GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID not configured; "
            "running without the Google Search Provider."
        )
    else:
        providers.append(GoogleSearchProvider(settings=google_settings))

    return providers


def _build_verification_coordinator() -> VerificationCoordinator | None:
    try:
        neverbounce_settings = NeverBounceSettings.from_env()
        neverbounce_settings.validate()
    except ValueError:
        logger.warning(
            "NEVERBOUNCE_API_KEY not configured; running without email verification."
        )
        return None

    provider = NeverBounceEmailProvider(settings=neverbounce_settings)
    return VerificationCoordinator([provider], VerificationProfile(name="run_pipeline"))


def _build_search_collaborators(
    dev_mode: bool,
) -> tuple[SearchCoordinator | None, _CountingSearchExtraction | None]:
    try:
        browser_settings = BrowserSearchProviderSettings.from_env()
        browser_settings.validate()
    except ValueError:
        logger.warning(
            "BROWSER_SEARCH_URL_TEMPLATE and friends not configured; running "
            "without the Search Layer (Browser Search + Search Extraction)."
        )
        return None, None

    provider = BrowserSearchProvider(browser_settings)
    health_tracker = _DevModeHealthTracker() if dev_mode else ProviderHealthTracker()
    coordinator = SearchCoordinator(
        SearchProviderRegistry([provider]),
        default_search_profile(),
        health_tracker=health_tracker,
    )
    extraction = _CountingSearchExtraction(SearchExtractionEngine())
    return coordinator, extraction


def build_orchestrator(
    dev_mode: bool = False,
) -> tuple[ExecutiveProcessingOrchestrator, _CountingSearchExtraction | None]:
    """Wire real infrastructure into an ExecutiveProcessingOrchestrator.

    Args:
        dev_mode: When True, both EnrichmentCoordinator and
            SearchCoordinator get a _DevModeHealthTracker instead of the
            real ProviderHealthTracker — see this module's own docstring
            ("WHY --dev-mode EXISTS") for exactly what that changes.
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
    enrichment_coordinator = EnrichmentCoordinator(
        ProviderRegistry(_build_enrichment_providers()),
        EnrichmentProfile(name="run_pipeline"),
        health_tracker=enrichment_health_tracker,
    )
    comparison_engine = ComparisonEngine(default_comparison_profile())
    inflection_engine = InflectionDetectionEngine(
        InflectionRuleRegistry(INFLECTION_RULES), default_inflection_profile()
    )
    search_coordinator, search_extraction = _build_search_collaborators(dev_mode)

    orchestrator = ExecutiveProcessingOrchestrator(
        enrichment_coordinator=enrichment_coordinator,
        comparison_engine=comparison_engine,
        inflection_engine=inflection_engine,
        verification_coordinator=_build_verification_coordinator(),
        search_coordinator=search_coordinator,
        search_extraction_engine=search_extraction,
    )
    return orchestrator, search_extraction


def _pages_fetched(report: ExecutiveProcessingReport) -> int:
    return sum(
        1
        for observation in report.observations_collected
        if observation.provider_id == _SEARCH_EXTRACTION_PROVIDER_ID
        and observation.attribute == _PAGE_ATTRIBUTE
    )


def _build_result_row(
    report: ExecutiveProcessingReport,
    cleaned_values: Mapping[str, Any],
    search_results_found: int,
) -> dict:
    row = build_row(report, cleaned_values)
    browser_search_performed = _BROWSER_SEARCH_PROVIDER_ID in report.providers_executed
    return {
        "Executive Name": row.executive_name,
        "Company": row.company,
        "Company Website Found (Yes/No)": (
            "Yes" if row.company_website_results_found > 0 else "No"
        ),
        "Browser Search Performed (Yes/No)": (
            "Yes" if browser_search_performed else "No"
        ),
        "Search Results Found": search_results_found,
        "Pages Successfully Fetched": _pages_fetched(report),
        "ObservationCandidates Extracted": row.observations_collected,
        "Comparison Result": row.comparison_summary,
        "Inflection Detected": row.inflections_detected,
        "Contact Verification Status": row.verification_status,
        "Errors (if any)": row.errors or "",
    }


def _summary(
    intelligence_report: ExecutiveIntelligenceReport, rows: list[dict]
) -> dict:
    total = intelligence_report.statistics.total_executives
    website_found = sum(
        1 for row in rows if row["Company Website Found (Yes/No)"] == "Yes"
    )
    search_performed = sum(
        1 for row in rows if row["Browser Search Performed (Yes/No)"] == "Yes"
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

    def _rate(numerator: int) -> float:
        return round((numerator / total) * 100, 1) if total else 0.0

    return {
        "Total Executives Processed": total,
        "Success Rate": _rate(intelligence_report.statistics.succeeded),
        "Website Success Rate": _rate(website_found),
        "Search Success Rate": _rate(search_performed),
        "Observation Extraction Rate": _rate(observations_extracted),
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
    path: Path,
) -> None:
    payload = {
        "source_file": source_path,
        "sheet": sheet_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
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

    orchestrator, search_extraction = build_orchestrator(dev_mode=args.dev_mode)
    batch = [
        (record, f"row:{record.raw_record.row_number}") for record in cleaned_records
    ]
    intelligence_report = orchestrator.process_batch(batch)

    rows = []
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

    summary = _summary(intelligence_report, rows)

    results_path = output_dir / args.results_name
    report_path = output_dir / args.report_name
    _write_results_xlsx(rows, results_path)
    _write_processing_report_json(
        summary, rows, args.excel_path, args.sheet, report_path
    )

    logger.info(
        "Run complete: {} executive(s), {:.1f}% success rate. " "results={} report={}",
        summary["Total Executives Processed"],
        summary["Success Rate"],
        results_path,
        report_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
