"""Tests for row_builder.build_row."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.dto.verification_models import VerificationStatus
from lead_intelligence.application.evaluation.row_builder import build_row
from tests.unit.evaluation.fixtures import (
    make_inflection_report,
    make_report,
    make_verification_report,
)


def _observation(
    provider_id: str, attribute: str = "web_mention"
) -> ObservationCandidate:
    return ObservationCandidate(
        subject_id="row:1",
        attribute=attribute,
        value="something",
        provider_id=provider_id,
        observed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )


class TestBasicFields:
    def test_carries_subject_id_and_executive_name(self) -> None:
        report = make_report(subject_id="row:42", executive_name="Ada Lovelace")

        row = build_row(report, {})

        assert row.subject_id == "row:42"
        assert row.executive_name == "Ada Lovelace"

    def test_company_resolved_from_cleaned_values(self) -> None:
        report = make_report()

        row = build_row(report, {fc.COMPANY_NAME: "Acme Corp"})

        assert row.company == "Acme Corp"

    def test_website_searched_from_cleaned_values(self) -> None:
        report = make_report()

        row = build_row(report, {fc.URL: "https://acme.com"})

        assert row.website_searched == "https://acme.com"

    def test_website_searched_is_none_when_blank(self) -> None:
        report = make_report()

        row = build_row(report, {fc.URL: "   "})

        assert row.website_searched is None

    def test_processing_duration_and_status_carried_through(self) -> None:
        report = make_report(status=ExecutiveProcessingStatus.PARTIAL)

        row = build_row(report, {})

        assert row.status is ExecutiveProcessingStatus.PARTIAL
        assert row.processing_duration_ms >= 0.0


class TestProviderCounts:
    def test_google_results_found_counts_only_google_search_observations(self) -> None:
        report = make_report(
            observations_collected=(
                _observation("google_search"),
                _observation("google_search"),
                _observation("company_website"),
            )
        )

        row = build_row(report, {})

        assert row.google_results_found == 2
        assert row.company_website_results_found == 1
        assert row.observations_collected == 3

    def test_providers_executed_is_comma_joined(self) -> None:
        report = make_report(providers_executed=("company_website", "google_search"))

        row = build_row(report, {})

        assert row.providers_executed == "company_website,google_search"


class TestComparisonSummary:
    def test_not_compared_when_no_comparison_result(self) -> None:
        report = make_report(executive_name=None, comparison_result=None)

        row = build_row(report, {})

        assert row.comparison_summary == "not_compared"

    def test_formats_summary_from_comparison_result(self) -> None:
        report = make_report()

        row = build_row(report, {})

        assert "matched=" in row.comparison_summary
        assert "confidence=" in row.comparison_summary


class TestInflectionsDetected:
    def test_not_detected_when_no_inflection_report(self) -> None:
        report = make_report(inflection_report=None)

        row = build_row(report, {})

        assert row.inflections_detected == "not_detected"

    def test_none_when_inflection_report_has_no_detections(self) -> None:
        report = make_report(inflection_report=make_inflection_report(()))

        row = build_row(report, {})

        assert row.inflections_detected == "none"

    def test_lists_detected_types_sorted_and_comma_joined(self) -> None:
        report = make_report(
            inflection_report=make_inflection_report(
                (InflectionType.PROMOTION, InflectionType.COMPANY_CHANGE)
            )
        )

        row = build_row(report, {})

        assert row.inflections_detected == "company_change,promotion"


class TestVerificationStatus:
    def test_no_email_when_no_email_known_and_no_report(self) -> None:
        report = make_report(verification_report=None)

        row = build_row(report, {})

        assert row.verification_status == "no_email"

    def test_not_configured_when_email_known_but_no_report_or_error(self) -> None:
        report = make_report(verification_report=None)

        row = build_row(report, {fc.EMAIL: "ada@acme.com"})

        assert row.verification_status == "not_configured"

    def test_error_when_verification_stage_failed(self) -> None:
        report = make_report(
            verification_report=None, stage_errors=("Verification failed: boom",)
        )

        row = build_row(report, {fc.EMAIL: "ada@acme.com"})

        assert row.verification_status == "error"

    def test_reports_real_status_when_verification_ran(self) -> None:
        report = make_report(
            verification_report=make_verification_report(VerificationStatus.VALID)
        )

        row = build_row(report, {fc.EMAIL: "ada@acme.com"})

        assert row.verification_status == "valid"


class TestErrors:
    def test_empty_string_when_no_stage_errors(self) -> None:
        report = make_report(stage_errors=())

        row = build_row(report, {})

        assert row.errors == ""

    def test_semicolon_joins_multiple_stage_errors(self) -> None:
        report = make_report(
            stage_errors=("Enrichment (person) failed: boom", "Comparison failed: oops")
        )

        row = build_row(report, {})

        assert row.errors == "Enrichment (person) failed: boom; Comparison failed: oops"
