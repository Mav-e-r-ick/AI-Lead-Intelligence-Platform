"""Builds one ExecutiveEvaluationRow from one ExecutiveProcessingReport.

WHY THIS LOGIC LIVES HERE, NOT ON ExecutiveProcessingReport ITSELF:
Flattening a report into printable, CSV-ready values is an evaluation
concern, not something every caller of the Executive Processing Pipeline
needs — adding it to ExecutiveProcessingReport would be exactly the kind
of "redesign an existing module" this task excludes. This module reads
`ExecutiveProcessingReport` and the original `CleanedLeadRecord` (for
`company`/`website_searched`, which the report itself doesn't carry) and
produces a new, separate value.
"""

from __future__ import annotations

from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison.resolvers import (
    resolve_company,
    resolve_email,
)
from lead_intelligence.application.dto.evaluation_models import ExecutiveEvaluationRow
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingReport,
)

#: provider_id used by the Google Search Provider (infrastructure/enrichment/google_search/).
_GOOGLE_SEARCH_PROVIDER_ID = "google_search"

#: provider_id used by the Company Website Provider (infrastructure/enrichment/company_website/).
_COMPANY_WEBSITE_PROVIDER_ID = "company_website"


def build_row(
    report: ExecutiveProcessingReport, cleaned_values: Mapping[str, Any]
) -> ExecutiveEvaluationRow:
    """Flatten `report` (plus the original record's `cleaned_values`) into
    one CSV-ready ExecutiveEvaluationRow.

    Args:
        report: The ExecutiveProcessingReport produced for this executive.
        cleaned_values: The same existing record's `cleaned_values` that
            was passed into `ExecutiveProcessingOrchestrator.process()` —
            used only for `company`/`website_searched`, which the report
            itself does not carry.
    """

    google_results_found = _count_by_provider(report, _GOOGLE_SEARCH_PROVIDER_ID)
    company_website_results_found = _count_by_provider(
        report, _COMPANY_WEBSITE_PROVIDER_ID
    )

    return ExecutiveEvaluationRow(
        subject_id=report.subject_id,
        executive_name=report.executive_name,
        company=resolve_company(cleaned_values),
        website_searched=_blank_to_none(cleaned_values.get(fc.URL)),
        providers_executed=",".join(report.providers_executed),
        company_website_results_found=company_website_results_found,
        google_results_found=google_results_found,
        observations_collected=len(report.observations_collected),
        comparison_summary=_comparison_summary(report),
        inflections_detected=_inflections_detected(report),
        verification_status=_verification_status(report, cleaned_values),
        processing_duration_ms=report.duration_ms,
        errors="; ".join(report.stage_errors),
        status=report.status,
    )


def _count_by_provider(report: ExecutiveProcessingReport, provider_id: str) -> int:
    return sum(
        1
        for observation in report.observations_collected
        if observation.provider_id == provider_id
    )


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _comparison_summary(report: ExecutiveProcessingReport) -> str:
    if report.comparison_result is None:
        return "not_compared"
    summary = report.comparison_result.summary
    return (
        f"matched={summary.fields_matched} changed={summary.fields_changed} "
        f"missing={summary.fields_missing} new={summary.fields_new} "
        f"conflict={summary.fields_conflict} unknown={summary.fields_unknown} "
        f"confidence={summary.confidence:.2f}"
    )


def _inflections_detected(report: ExecutiveProcessingReport) -> str:
    if report.inflection_report is None:
        return "not_detected"
    detected = sorted(t.value for t in report.inflection_report.detected_types)
    return ",".join(detected) if detected else "none"


def _verification_status(
    report: ExecutiveProcessingReport, cleaned_values: Mapping[str, Any]
) -> str:
    if report.verification_report is not None:
        results = report.verification_report.provider_results
        if results:
            return ",".join(sorted({result.status.value for result in results}))
        return "no_provider_result"

    if not resolve_email(cleaned_values):
        return "no_email"
    if any("Verification failed" in error for error in report.stage_errors):
        return "error"
    return "not_configured"
