"""Unit tests for ExecutiveProcessingOrchestrator, using fake enrichment/
verification providers and deliberately-invalid sub-profiles to exercise
the orchestrator's own per-stage error handling."""

from __future__ import annotations

from typing import Callable

from lead_intelligence.application.comparison.config import (
    ComparisonFieldRule,
    ComparisonProfile,
    ComparisonStrategy,
)
from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ObservationCandidate,
    SubjectType,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.dto.verification_models import (
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from lead_intelligence.application.enrichment.config import (
    EnrichmentProfile,
    ProviderConfiguration,
)
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)
from lead_intelligence.application.inflection.config import (
    InflectionProfile,
    InflectionRuleOverride,
)
from lead_intelligence.application.verification.config import (
    VerificationProfile,
    VerificationProviderConfiguration,
)
from tests.unit.enrichment.fixtures import FakeEnrichmentProvider
from tests.unit.executive_pipeline.fixtures import (
    build_orchestrator,
    executive_record,
    fixed_clock,
)
from tests.unit.verification.fixtures import FakeVerificationProvider


def _promotion_response(
    provider_id: str,
) -> Callable[[EnrichmentRequest], EnrichmentResponse]:
    def handler(request: EnrichmentRequest) -> EnrichmentResponse:
        return EnrichmentResponse(
            provider_id=provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=EnrichmentStatus.SUCCESS,
            observations=(
                ObservationCandidate(
                    subject_id=request.subject_id,
                    attribute="title",
                    value="Chief Executive Officer",
                    provider_id=provider_id,
                    observed_at=fixed_clock(),
                ),
            ),
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )

    return handler


def _person_scoped_provider(
    provider_id: str, handler: Callable[[EnrichmentRequest], EnrichmentResponse]
) -> FakeEnrichmentProvider:
    """A FakeEnrichmentProvider scoped to SubjectType.PERSON only, mirroring
    the real GoogleSearchProvider's own scope — so it fires exactly once
    per pipeline run (during the PERSON enrichment call), not once per
    subject type the orchestrator queries."""

    return FakeEnrichmentProvider(
        provider_id,
        supported_subject_types=frozenset({SubjectType.PERSON}),
        handler=handler,
    )


def _valid_verification_handler(
    request: VerificationRequest,
) -> VerificationResult:
    return VerificationResult(
        provider_id="fake_email",
        request_id=request.request_id,
        subject_id=request.subject_id,
        contact_type=request.contact_type,
        value=request.value,
        status=VerificationStatus.VALID,
        confidence=None,
        reason=None,
        error_message=None,
        started_at=request.requested_at,
        completed_at=request.requested_at,
    )


class TestMissingExecutiveName:
    def test_missing_name_returns_failed_without_running_any_stage(self) -> None:
        record = executive_record(first_name="", last_name="")
        orchestrator = build_orchestrator()

        report = orchestrator.process(record, "person-1")

        assert report.status is ExecutiveProcessingStatus.FAILED
        assert report.executive_name is None
        assert report.providers_executed == ()
        assert report.observations_collected == ()
        assert report.comparison_result is None
        assert report.inflection_report is None
        assert report.verification_report is None
        assert len(report.stage_errors) == 1


class TestHappyPath:
    def test_all_stages_succeed(self) -> None:
        provider = _person_scoped_provider(
            "company_website", _promotion_response("company_website")
        )
        verifier = FakeVerificationProvider(
            "fake_email", handler=_valid_verification_handler
        )
        orchestrator = build_orchestrator(
            enrichment_providers=[provider], verification_providers=[verifier]
        )
        record = executive_record(title="Manager")

        report = orchestrator.process(record, "person-1")

        assert report.status is ExecutiveProcessingStatus.SUCCESS
        assert report.executive_name == "Ada Lovelace"
        assert report.providers_executed == ("company_website",)
        assert len(report.observations_collected) == 1
        assert report.comparison_result is not None
        assert report.comparison_result.record_reference == "person-1"
        assert report.inflection_report is not None
        assert report.verification_report is not None
        assert report.verification_report.provider_results[0].status is (
            VerificationStatus.VALID
        )
        assert report.stage_errors == ()
        assert report.duration_ms >= 0.0

    def test_promotion_is_detected_end_to_end(self) -> None:
        provider = _person_scoped_provider(
            "company_website", _promotion_response("company_website")
        )
        orchestrator = build_orchestrator(enrichment_providers=[provider])
        record = executive_record(title="Manager")

        report = orchestrator.process(record, "person-1")

        assert report.inflection_report is not None
        assert InflectionType.PROMOTION in report.inflection_report.detected_types


class TestProviderRouting:
    def test_pipeline_queries_both_person_and_company_subject_types(self) -> None:
        """Mirrors the real framework: GoogleSearchProvider supports only
        PERSON, CompanyWebsiteProvider supports only COMPANY. The
        orchestrator must query both subject types so each still runs for
        the same pipeline execution."""

        google_search_like = FakeEnrichmentProvider(
            "google_search", supported_subject_types=frozenset({SubjectType.PERSON})
        )
        company_website_like = FakeEnrichmentProvider(
            "company_website",
            supported_subject_types=frozenset({SubjectType.COMPANY}),
        )
        orchestrator = build_orchestrator(
            enrichment_providers=[google_search_like, company_website_like]
        )

        report = orchestrator.process(executive_record(), "person-1")

        assert set(report.providers_executed) == {"google_search", "company_website"}

    def test_provider_supporting_neither_subject_type_never_runs(self) -> None:
        supports_neither = FakeEnrichmentProvider(
            "unsupported", supported_subject_types=frozenset()
        )
        orchestrator = build_orchestrator(enrichment_providers=[supports_neither])

        report = orchestrator.process(executive_record(), "person-1")

        assert report.providers_executed == ()

    def test_observations_are_aggregated_across_providers(self) -> None:
        a = _person_scoped_provider("a", _promotion_response("a"))
        b = _person_scoped_provider("b", _promotion_response("b"))
        orchestrator = build_orchestrator(enrichment_providers=[a, b])

        report = orchestrator.process(executive_record(), "person-1")

        assert len(report.observations_collected) == 2
        assert report.providers_executed == ("a", "b")


class TestVerificationScope:
    def test_verification_skipped_when_not_configured(self) -> None:
        orchestrator = build_orchestrator()

        report = orchestrator.process(executive_record(), "person-1")

        assert report.verification_report is None
        assert report.stage_errors == ()

    def test_verification_skipped_when_no_email_known(self) -> None:
        verifier = FakeVerificationProvider(
            "fake_email", handler=_valid_verification_handler
        )
        orchestrator = build_orchestrator(verification_providers=[verifier])
        record = executive_record(email=None)

        report = orchestrator.process(record, "person-1")

        assert report.verification_report is None
        assert report.stage_errors == ()

    def test_verification_receives_the_existing_records_email(self) -> None:
        captured: list[str] = []

        def handler(request: VerificationRequest) -> VerificationResult:
            captured.append(request.value)
            return _valid_verification_handler(request)

        verifier = FakeVerificationProvider("fake_email", handler=handler)
        orchestrator = build_orchestrator(verification_providers=[verifier])
        record = executive_record(email="ada@acme.com")

        orchestrator.process(record, "person-1")

        assert captured == ["ada@acme.com"]


class TestStageErrorHandling:
    def test_enrichment_stage_error_is_recorded_and_pipeline_continues(self) -> None:
        broken_enrichment_profile = EnrichmentProfile(
            name="broken",
            default_configuration=ProviderConfiguration(timeout_seconds=0),
        )
        orchestrator = build_orchestrator(enrichment_profile=broken_enrichment_profile)

        report = orchestrator.process(executive_record(), "person-1")

        assert report.providers_executed == ()
        assert report.observations_collected == ()
        assert any(error.startswith("Enrichment (") for error in report.stage_errors)
        # Both subject-type enrichment calls fail independently.
        assert len(report.stage_errors) == 2
        # Comparison and inflection still run against zero observations.
        assert report.comparison_result is not None
        assert report.inflection_report is not None
        assert report.status is ExecutiveProcessingStatus.PARTIAL

    def test_comparison_stage_error_yields_failed_status(self) -> None:
        broken_comparison_profile = ComparisonProfile(
            name="broken",
            field_rules=(
                ComparisonFieldRule("name", ("full_name",), ComparisonStrategy.FUZZY),
                ComparisonFieldRule("name", ("full_name",), ComparisonStrategy.FUZZY),
            ),
        )
        orchestrator = build_orchestrator(comparison_profile=broken_comparison_profile)

        report = orchestrator.process(executive_record(), "person-1")

        assert report.comparison_result is None
        assert report.inflection_report is None
        assert any("Comparison failed" in error for error in report.stage_errors)
        assert report.status is ExecutiveProcessingStatus.FAILED

    def test_inflection_stage_error_yields_partial_status(self) -> None:
        broken_inflection_profile = InflectionProfile(
            name="broken",
            rule_overrides={"INF-001": InflectionRuleOverride(base_confidence=2.0)},
        )
        orchestrator = build_orchestrator(inflection_profile=broken_inflection_profile)

        report = orchestrator.process(executive_record(), "person-1")

        assert report.comparison_result is not None
        assert report.inflection_report is None
        assert any(
            "Inflection detection failed" in error for error in report.stage_errors
        )
        assert report.status is ExecutiveProcessingStatus.PARTIAL

    def test_verification_stage_error_yields_partial_status(self) -> None:
        verifier = FakeVerificationProvider(
            "fake_email", handler=_valid_verification_handler
        )
        broken_verification_profile = VerificationProfile(
            name="broken",
            default_configuration=VerificationProviderConfiguration(timeout_seconds=0),
        )
        orchestrator = build_orchestrator(
            verification_providers=[verifier],
            verification_profile=broken_verification_profile,
        )

        report = orchestrator.process(executive_record(), "person-1")

        assert report.comparison_result is not None
        assert report.verification_report is None
        assert any("Verification failed" in error for error in report.stage_errors)
        assert report.status is ExecutiveProcessingStatus.PARTIAL


class TestDeterminism:
    def test_repeated_runs_produce_equal_reports(self) -> None:
        provider = _person_scoped_provider(
            "company_website", _promotion_response("company_website")
        )

        def build() -> ExecutiveProcessingOrchestrator:
            return build_orchestrator(enrichment_providers=[provider])

        report_a = build().process(executive_record(title="Manager"), "person-1")
        report_b = build().process(executive_record(title="Manager"), "person-1")

        assert report_a == report_b
