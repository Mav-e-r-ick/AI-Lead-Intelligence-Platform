"""Plain data shapes produced by the Evaluation & Validation module.

WHY THIS FILE EXISTS (SEPARATE FROM executive_pipeline_models.py etc.):
Same reasoning as every other stage's own DTO file's docstring: each
pipeline stage gets one cohesive vocabulary file, so none of them grows
into an unrelated grab-bag as more stages are added.

WHY THIS IS A SEPARATE VOCABULARY FROM ExecutiveProcessingReport, NOT A
REUSE OF IT:
ExecutiveProcessingReport is built for one executive, and embeds each
underlying engine's own rich result type (ComparisonResult,
InflectionReport, VerificationReport) — exactly right for that engine's
own callers. A CSV row, by contrast, needs flat, printable values (a
string summary, a count, a joined list) suitable for a spreadsheet cell,
and the aggregate EvaluationSummary needs numbers computed *across* many
reports. Neither shape belongs on ExecutiveProcessingReport itself — this
task's scope explicitly excludes redesigning that (or any other) existing
module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)

__all__ = [
    "ExecutiveEvaluationRow",
    "EvaluationSummary",
    "EvaluationRun",
]


@dataclass(frozen=True)
class ExecutiveEvaluationRow:
    """One executive's flattened, CSV-ready evaluation result.

    Attributes:
        subject_id: The opaque id this executive was processed under —
            the same id `ExecutiveProcessingOrchestrator.process()` used,
            carried through for traceability back to the source row.
        executive_name: The executive's full name, or None if it could not
            be resolved (a FAILED run).
        company: The executive's company, resolved via the same
            `resolve_company` the Executive Comparison Engine itself uses.
        website_searched: The company website URL given to the pipeline
            for this executive (whether or not the Company Website
            Provider actually found anything there), or None if no URL
            was known.
        providers_executed: Every enrichment provider_id that actually ran
            for this executive, comma-joined (e.g. "company_website,
            google_search"), or "" if none did.
        company_website_results_found: Number of observations collected
            by the Company Website Provider for this executive.
        google_results_found: Number of `web_mention` observations
            collected by the Google Search Provider for this executive.
        observations_collected: Total ObservationCandidates collected
            across every enrichment provider that ran.
        comparison_summary: A short, human-readable digest of the
            Executive Comparison Engine's ComparisonSummary (e.g.
            "matched=2 changed=1 missing=0 new=0 conflict=0 unknown=1
            confidence=0.83"), or "not_compared" if the comparison stage
            did not run.
        inflections_detected: Every detected InflectionType's value,
            comma-joined in sorted order (e.g. "company_change,promotion"),
            or "none" if inflection detection ran and found nothing, or
            "not_detected" if the stage did not run.
        verification_status: One of the real VerificationStatus values (if
            verification ran and returned a result), "no_email" (no known
            email to verify), "not_configured" (no VerificationCoordinator
            was wired into this run), or "error" (the verification stage
            itself raised).
        processing_duration_ms: This executive's total pipeline duration,
            from `ExecutiveProcessingReport.duration_ms`.
        errors: Every stage error encountered, semicolon-joined, or "" if
            none.
        status: The originating ExecutiveProcessingReport's overall status.
    """

    subject_id: str
    executive_name: str | None
    company: str | None
    website_searched: str | None
    providers_executed: str
    company_website_results_found: int
    google_results_found: int
    observations_collected: int
    comparison_summary: str
    inflections_detected: str
    verification_status: str
    processing_duration_ms: float
    errors: str
    status: ExecutiveProcessingStatus


@dataclass(frozen=True)
class EvaluationSummary:
    """Aggregate metrics computed across every ExecutiveEvaluationRow in
    one evaluation run.

    Attributes:
        total_executives_processed: Total rows produced (one per input
            executive record).
        success_rate: Percentage (0-100) of rows whose `status` is
            `ExecutiveProcessingStatus.SUCCESS`.
        failed_searches: Number of rows where at least one enrichment
            call (Company Website or Google Search) raised an unexpected
            error — a technical failure, not merely "found nothing."
        company_websites_found: Number of rows with at least one
            observation collected from the Company Website Provider.
        google_searches_completed: Number of rows where the Google Search
            Provider executed successfully (regardless of how many, if
            any, results it found).
        promotions_detected: Number of rows whose detected inflections
            include Promotion.
        company_changes_detected: Number of rows whose detected
            inflections include Company Change.
        missing_executives: Number of rows whose detected inflections
            include Executive No Longer Found.
        verification_success_rate: Percentage (0-100) of rows that were
            actually verified (i.e. `verification_status` is a real
            VerificationStatus value, not "no_email"/"not_configured"/
            "error") whose result was VALID. 0.0 if none were verified.
    """

    total_executives_processed: int
    success_rate: float
    failed_searches: int
    company_websites_found: int
    google_searches_completed: int
    promotions_detected: int
    company_changes_detected: int
    missing_executives: int
    verification_success_rate: float


@dataclass(frozen=True)
class EvaluationRun:
    """The Evaluation & Validation module's single output type for one
    run of the Executive Processing Pipeline over a dataset.

    Attributes:
        source_description: A human-readable description of what was
            evaluated (e.g. the source file path and sheet name), for
            traceability in the exported report.
        rows: One ExecutiveEvaluationRow per processed executive, in
            input order.
        summary: Aggregate metrics computed from `rows`.
        started_at: When this evaluation run began.
        completed_at: When this evaluation run finished.
    """

    source_description: str
    rows: tuple[ExecutiveEvaluationRow, ...]
    summary: EvaluationSummary
    started_at: datetime
    completed_at: datetime

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the whole evaluation run, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000
