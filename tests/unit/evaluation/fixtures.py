"""Shared test fixtures for the Evaluation & Validation module's tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from lead_intelligence.application.dto.comparison_models import ComparisonResult
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingReport,
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.inflection_models import (
    Inflection,
    InflectionReport,
    InflectionType,
)
from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationCoordinationMetrics,
    VerificationReport,
    VerificationResult,
    VerificationStatus,
)
from tests.unit.inflection.fixtures import (
    make_all_match_comparisons,
    make_comparison_result,
)


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def make_inflection_report(
    detected_types: Sequence[InflectionType] = (),
    record_reference: str = "row:1",
) -> InflectionReport:
    inflections = tuple(
        Inflection(
            type=inflection_type,
            confidence=0.9,
            supporting_comparisons=(),
            explanation="test",
            detected_at=fixed_clock(),
            rule_id="INF-000",
        )
        for inflection_type in detected_types
    )
    return InflectionReport(
        record_reference=record_reference,
        inflections=inflections,
        generated_at=fixed_clock(),
    )


def make_verification_report(
    status: VerificationStatus = VerificationStatus.VALID,
    subject_id: str = "row:1",
    value: str = "ada@acme.com",
) -> VerificationReport:
    result = VerificationResult(
        provider_id="neverbounce",
        request_id="req-1",
        subject_id=subject_id,
        contact_type=ContactType.EMAIL,
        value=value,
        status=status,
        confidence=None,
        reason=None,
        error_message=None,
        started_at=fixed_clock(),
        completed_at=fixed_clock(),
    )
    return VerificationReport(
        request_id="req-1",
        subject_id=subject_id,
        contact_type=ContactType.EMAIL,
        value=value,
        provider_results=(result,),
        skipped_providers=(),
        started_at=fixed_clock(),
        completed_at=fixed_clock(),
        metrics=VerificationCoordinationMetrics(
            providers_considered=1,
            providers_executed=1,
            providers_succeeded=1,
            providers_failed=0,
            providers_skipped=0,
            execution_time_total_ms=1.0,
        ),
    )


def make_report(
    subject_id: str = "row:1",
    executive_name: str | None = "Ada Lovelace",
    providers_executed: tuple[str, ...] = ("company_website", "google_search"),
    observations_collected: tuple[ObservationCandidate, ...] = (),
    comparison_result: ComparisonResult | None = None,
    inflection_report: InflectionReport | None = None,
    verification_report: VerificationReport | None = None,
    status: ExecutiveProcessingStatus = ExecutiveProcessingStatus.SUCCESS,
    stage_errors: tuple[str, ...] = (),
) -> ExecutiveProcessingReport:
    if comparison_result is None and executive_name is not None:
        comparison_result = make_comparison_result(
            make_all_match_comparisons(), record_reference=subject_id
        )

    return ExecutiveProcessingReport(
        subject_id=subject_id,
        executive_name=executive_name,
        providers_executed=providers_executed,
        observations_collected=observations_collected,
        comparison_result=comparison_result,
        inflection_report=inflection_report,
        verification_report=verification_report,
        status=status,
        stage_errors=stage_errors,
        started_at=fixed_clock(),
        completed_at=fixed_clock(),
    )
