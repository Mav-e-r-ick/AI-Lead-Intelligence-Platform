"""Tests for metrics.compute_summary."""

from __future__ import annotations

from lead_intelligence.application.dto.evaluation_models import ExecutiveEvaluationRow
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.evaluation.metrics import compute_summary


def _row(
    status: ExecutiveProcessingStatus = ExecutiveProcessingStatus.SUCCESS,
    providers_executed: str = "company_website,google_search",
    company_website_results_found: int = 0,
    google_results_found: int = 0,
    inflections_detected: str = "none",
    verification_status: str = "not_configured",
    errors: str = "",
) -> ExecutiveEvaluationRow:
    return ExecutiveEvaluationRow(
        subject_id="row:1",
        executive_name="Ada Lovelace",
        company="Acme Corp",
        website_searched="https://acme.com",
        providers_executed=providers_executed,
        company_website_results_found=company_website_results_found,
        google_results_found=google_results_found,
        observations_collected=company_website_results_found + google_results_found,
        comparison_summary="matched=5",
        inflections_detected=inflections_detected,
        verification_status=verification_status,
        processing_duration_ms=1.0,
        errors=errors,
        status=status,
    )


class TestEmptyInput:
    def test_returns_all_zero_metrics_for_no_rows(self) -> None:
        summary = compute_summary([])

        assert summary.total_executives_processed == 0
        assert summary.success_rate == 0.0
        assert summary.failed_searches == 0
        assert summary.company_websites_found == 0
        assert summary.google_searches_completed == 0
        assert summary.promotions_detected == 0
        assert summary.company_changes_detected == 0
        assert summary.missing_executives == 0
        assert summary.verification_success_rate == 0.0


class TestSuccessRate:
    def test_all_success(self) -> None:
        rows = [_row(status=ExecutiveProcessingStatus.SUCCESS) for _ in range(4)]

        summary = compute_summary(rows)

        assert summary.total_executives_processed == 4
        assert summary.success_rate == 100.0

    def test_mixed_statuses(self) -> None:
        rows = [
            _row(status=ExecutiveProcessingStatus.SUCCESS),
            _row(status=ExecutiveProcessingStatus.SUCCESS),
            _row(status=ExecutiveProcessingStatus.PARTIAL),
            _row(status=ExecutiveProcessingStatus.FAILED),
        ]

        summary = compute_summary(rows)

        assert summary.success_rate == 50.0


class TestFailedSearches:
    def test_counts_rows_with_enrichment_stage_errors(self) -> None:
        rows = [
            _row(errors="Enrichment (person) failed: boom"),
            _row(errors="Enrichment (company) failed: boom"),
            _row(errors="Comparison failed: oops"),
            _row(errors=""),
        ]

        summary = compute_summary(rows)

        assert summary.failed_searches == 2

    def test_zero_results_is_not_a_failed_search(self) -> None:
        rows = [_row(google_results_found=0, company_website_results_found=0)]

        summary = compute_summary(rows)

        assert summary.failed_searches == 0


class TestProviderMetrics:
    def test_company_websites_found_requires_at_least_one_result(self) -> None:
        rows = [
            _row(company_website_results_found=1),
            _row(company_website_results_found=0),
        ]

        summary = compute_summary(rows)

        assert summary.company_websites_found == 1

    def test_google_searches_completed_counts_execution_not_results(self) -> None:
        rows = [
            _row(providers_executed="google_search", google_results_found=0),
            _row(providers_executed="company_website", google_results_found=0),
        ]

        summary = compute_summary(rows)

        assert summary.google_searches_completed == 1


class TestInflectionMetrics:
    def test_promotions_detected(self) -> None:
        rows = [
            _row(inflections_detected="promotion"),
            _row(inflections_detected="company_change,promotion"),
            _row(inflections_detected="none"),
        ]

        summary = compute_summary(rows)

        assert summary.promotions_detected == 2

    def test_company_changes_detected(self) -> None:
        rows = [
            _row(inflections_detected="company_change"),
            _row(inflections_detected="promotion"),
        ]

        summary = compute_summary(rows)

        assert summary.company_changes_detected == 1

    def test_missing_executives(self) -> None:
        rows = [
            _row(inflections_detected="executive_no_longer_found"),
            _row(inflections_detected="promotion"),
            _row(inflections_detected="not_detected"),
        ]

        summary = compute_summary(rows)

        assert summary.missing_executives == 1


class TestVerificationSuccessRate:
    def test_excludes_unverified_rows_from_denominator(self) -> None:
        rows = [
            _row(verification_status="valid"),
            _row(verification_status="invalid"),
            _row(verification_status="no_email"),
            _row(verification_status="not_configured"),
        ]

        summary = compute_summary(rows)

        # Only 2 rows were actually verified (valid/invalid); 1 of 2 is valid.
        assert summary.verification_success_rate == 50.0

    def test_zero_when_nothing_was_verified(self) -> None:
        rows = [_row(verification_status="not_configured")]

        summary = compute_summary(rows)

        assert summary.verification_success_rate == 0.0

    def test_hundred_when_all_verified_are_valid(self) -> None:
        rows = [_row(verification_status="valid"), _row(verification_status="valid")]

        summary = compute_summary(rows)

        assert summary.verification_success_rate == 100.0
