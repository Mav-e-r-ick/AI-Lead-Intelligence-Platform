"""Computes EvaluationSummary from a sequence of ExecutiveEvaluationRows.

WHY "FAILED SEARCHES" MEANS A TECHNICAL FAILURE, NOT "FOUND NOTHING":
An enrichment provider that ran successfully and simply found no evidence
is a normal, honest outcome (the same distinction the Enrichment Provider
Framework itself draws between a `SUCCESS`/`PARTIAL` response with zero
observations and an actual `FAILURE`). "Failed searches" here counts rows
where the pipeline's own enrichment stage recorded an error — i.e. an
`ExecutiveProcessingReport.stage_errors` entry beginning with
`"Enrichment ("` (see `executive_pipeline/orchestrator.py`) — never rows
that merely collected zero results.

WHY VERIFICATION SUCCESS RATE EXCLUDES "no_email"/"not_configured"/"error"
FROM THE DENOMINATOR:
Those three outcomes mean verification never actually ran (no known email,
no VerificationCoordinator configured, or the stage itself failed) — they
are not verification *attempts* that came back negative. Dividing by only
the rows that received a real VerificationStatus answer keeps this rate
meaningful: "of the emails we actually checked, how many came back valid?"
"""

from __future__ import annotations

from typing import Sequence

from lead_intelligence.application.dto.evaluation_models import (
    EvaluationSummary,
    ExecutiveEvaluationRow,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.dto.verification_models import VerificationStatus

#: verification_status values that mean "verification did not actually run"
#: — excluded from the verification success rate's denominator.
_NOT_VERIFIED_STATUSES = frozenset({"no_email", "not_configured", "error"})


def compute_summary(rows: Sequence[ExecutiveEvaluationRow]) -> EvaluationSummary:
    """Compute aggregate metrics across every row in one evaluation run.

    Args:
        rows: Every ExecutiveEvaluationRow produced for this run, in any
            order.

    Returns:
        An EvaluationSummary. All rates are 0.0 if `rows` is empty (no
        division by zero — there is nothing to report a rate over).
    """

    total = len(rows)
    if total == 0:
        return EvaluationSummary(
            total_executives_processed=0,
            success_rate=0.0,
            failed_searches=0,
            company_websites_found=0,
            google_searches_completed=0,
            promotions_detected=0,
            company_changes_detected=0,
            missing_executives=0,
            verification_success_rate=0.0,
        )

    successes = sum(
        1 for row in rows if row.status is ExecutiveProcessingStatus.SUCCESS
    )
    failed_searches = sum(1 for row in rows if "Enrichment (" in row.errors)
    company_websites_found = sum(
        1 for row in rows if row.company_website_results_found > 0
    )
    google_searches_completed = sum(
        1 for row in rows if "google_search" in row.providers_executed.split(",")
    )
    promotions_detected = sum(
        1 for row in rows if InflectionType.PROMOTION.value in _detected_types(row)
    )
    company_changes_detected = sum(
        1 for row in rows if InflectionType.COMPANY_CHANGE.value in _detected_types(row)
    )
    missing_executives = sum(
        1
        for row in rows
        if InflectionType.EXECUTIVE_NO_LONGER_FOUND.value in _detected_types(row)
    )

    verified_rows = [
        row for row in rows if row.verification_status not in _NOT_VERIFIED_STATUSES
    ]
    verified_valid = sum(
        1
        for row in verified_rows
        if VerificationStatus.VALID.value in row.verification_status.split(",")
    )
    verification_success_rate = (
        (verified_valid / len(verified_rows)) * 100 if verified_rows else 0.0
    )

    return EvaluationSummary(
        total_executives_processed=total,
        success_rate=(successes / total) * 100,
        failed_searches=failed_searches,
        company_websites_found=company_websites_found,
        google_searches_completed=google_searches_completed,
        promotions_detected=promotions_detected,
        company_changes_detected=company_changes_detected,
        missing_executives=missing_executives,
        verification_success_rate=verification_success_rate,
    )


def _detected_types(row: ExecutiveEvaluationRow) -> set[str]:
    if row.inflections_detected in ("none", "not_detected"):
        return set()
    return set(row.inflections_detected.split(","))
