#!/usr/bin/env python
"""Run the Executive Processing Pipeline over a real Excel file and
export a CSV per-executive report plus a JSON processing summary.

Usage:
    python scripts/run_evaluation.py path/to/executives.xlsx \
        [--sheet SHEET_NAME] \
        [--output-dir reports] \
        [--csv-name executive_report.csv] \
        [--summary-name processing_summary.json]

WHY THIS SCRIPT LIVES IN scripts/, NOT interfaces/cli/:
Per scripts/README.md, this folder is for standalone operational tools
that support development/operations but aren't part of the importable
application — exactly this evaluation run. All actual business logic
(importing, cleaning, running the pipeline, computing metrics, exporting)
lives in `application/evaluation/`, fully unit-tested there; this script
only wires concrete infrastructure (a real Excel file, real enrichment
providers if credentials are configured, a real verification provider if
configured) and calls `PipelineRunner`.

WHY GOOGLE SEARCH AND EMAIL VERIFICATION ARE OPTIONAL HERE:
Both require real credentials (GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_ENGINE_ID,
NEVERBOUNCE_API_KEY) that may not be configured in every environment this
script runs in. Rather than fail the whole evaluation run for missing
credentials, this script logs a warning and proceeds without that piece —
the Enrichment Provider Framework and Verification Coordinator already
tolerate a provider being entirely absent (see their own READMEs); this
script simply chooses not to register one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.evaluation.export import write_evaluation_run
from lead_intelligence.application.evaluation.runner import PipelineRunner
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
from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase
from lead_intelligence.application.use_cases.process_executive import (
    ProcessExecutiveUseCase,
)
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.core.logging import configure_logging
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
    return VerificationCoordinator([provider], VerificationProfile(name="evaluation"))


def build_runner(excel_path: str | Path, sheet_name: str | None) -> PipelineRunner:
    """Wire real infrastructure into a PipelineRunner for `excel_path`."""

    source_reader = ExcelSourceReader(excel_path, sheet_name=sheet_name)
    import_use_case = ImportDatasetUseCase(source_reader)

    cleaning_pipeline = CleaningPipeline(CLEANING_RULES, default_cleaning_profile())
    clean_use_case = CleanDatasetUseCase(cleaning_pipeline)

    enrichment_coordinator = EnrichmentCoordinator(
        ProviderRegistry(_build_enrichment_providers()),
        EnrichmentProfile(name="evaluation"),
    )
    comparison_engine = ComparisonEngine(default_comparison_profile())
    inflection_engine = InflectionDetectionEngine(
        InflectionRuleRegistry(INFLECTION_RULES), default_inflection_profile()
    )
    orchestrator = ExecutiveProcessingOrchestrator(
        enrichment_coordinator=enrichment_coordinator,
        comparison_engine=comparison_engine,
        inflection_engine=inflection_engine,
        verification_coordinator=_build_verification_coordinator(),
    )
    process_executive_use_case = ProcessExecutiveUseCase(orchestrator)

    return PipelineRunner(import_use_case, clean_use_case, process_executive_use_case)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel_path", help="Path to the .xlsx file of executives.")
    parser.add_argument(
        "--sheet", default=None, help="Sheet name to read (default: auto-selected)."
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory to write the CSV/JSON reports into (default: reports).",
    )
    parser.add_argument(
        "--csv-name",
        default="executive_report.csv",
        help="Filename for the per-executive CSV report.",
    )
    parser.add_argument(
        "--summary-name",
        default="processing_summary.json",
        help="Filename for the JSON processing summary.",
    )
    args = parser.parse_args(argv)

    configure_logging()

    runner = build_runner(args.excel_path, args.sheet)
    run = runner.run(sheet_name=args.sheet, source_description=str(args.excel_path))

    output_dir = Path(args.output_dir)
    write_evaluation_run(
        run, output_dir / args.csv_name, output_dir / args.summary_name
    )

    logger.info(
        "Evaluation complete: {} executive(s), {:.1f}% success rate. "
        "Reports written to {}",
        run.summary.total_executives_processed,
        run.summary.success_rate,
        output_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
