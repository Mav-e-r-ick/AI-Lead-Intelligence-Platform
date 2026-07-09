"""Unit tests for the ExecutiveProcessingOrchestrator's identity
resolution, search, and search extraction stages, plus batch processing —
all against in-memory fakes, never a real browser or network."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import pytest

from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveIntelligenceReport,
    ExecutiveProcessingReport,
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityRecord,
    ResolutionDecision,
)
from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from lead_intelligence.application.identity_resolution import (
    config as identity_config,
)
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.application.ports.identity_candidate_port import (
    IdentityCandidatePort,
)
from lead_intelligence.application.search.config import (
    SearchProfile,
    SearchProviderConfiguration,
)
from tests.unit.executive_pipeline.fixtures import (
    build_orchestrator,
    executive_record,
    fixed_clock,
)
from tests.unit.identity_resolution.fixtures import FakeIdentityCandidatePort
from tests.unit.search.fixtures import FakeSearchProvider


def _search_result(url: str = "https://news.example.com/ada") -> SearchResult:
    return SearchResult(
        title="Ada Lovelace named CTO of Acme Corp",
        url=url,
        snippet="Acme Corp announced...",
        source="browser_search",
        rank=1,
    )


def _search_provider_with_results(
    results: tuple[SearchResult, ...] = (_search_result(),),
) -> FakeSearchProvider:
    def handler(request: SearchRequest) -> SearchResponse:
        return SearchResponse(
            provider_id="browser_search",
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=EnrichmentStatus.SUCCESS,
            results=results,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )

    return FakeSearchProvider("browser_search", handler=handler)


class FakeSearchExtraction:
    """A SearchExtractionPort stand-in: fully scripted, no fetching."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[tuple[str, tuple[SearchResult, ...]]] = []

    def extract(
        self, subject_id: str, search_results: Sequence[SearchResult]
    ) -> tuple[ObservationCandidate, ...]:
        self.calls.append((subject_id, tuple(search_results)))
        if self._raises is not None:
            raise self._raises
        return tuple(
            ObservationCandidate(
                subject_id=subject_id,
                attribute="title",
                value="CTO",
                provider_id="search_extraction",
                observed_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
                source_url=result.url,
            )
            for result in search_results
        )


class BrokenCandidatePort(IdentityCandidatePort):
    def find_by_signal(self, signal_type: str, value: str) -> Sequence[IdentityRecord]:
        raise RuntimeError("candidate store unavailable")


def _identity_engine(
    port: IdentityCandidatePort | None = None,
) -> IdentityResolutionEngine:
    return IdentityResolutionEngine(
        port if port is not None else FakeIdentityCandidatePort(),
        identity_config.default_profile(),
        id_factory=lambda: "id-1",
        clock=fixed_clock,
    )


class TestIdentityResolutionStage:
    def test_outcome_is_recorded_on_the_report(self) -> None:
        orchestrator = build_orchestrator(identity_resolution_engine=_identity_engine())

        report = orchestrator.process(executive_record(), "row:1")

        assert report.identity_resolution_outcome is not None
        assert (
            report.identity_resolution_outcome.decision
            is ResolutionDecision.NEW_IDENTITY
        )
        assert report.status is ExecutiveProcessingStatus.SUCCESS

    def test_outcome_is_none_when_no_engine_is_configured(self) -> None:
        orchestrator = build_orchestrator()

        report = orchestrator.process(executive_record(), "row:1")

        assert report.identity_resolution_outcome is None
        assert report.status is ExecutiveProcessingStatus.SUCCESS

    def test_identity_stage_failure_is_recorded_and_pipeline_continues(self) -> None:
        orchestrator = build_orchestrator(
            identity_resolution_engine=_identity_engine(BrokenCandidatePort())
        )

        report = orchestrator.process(executive_record(), "row:1")

        assert report.identity_resolution_outcome is None
        assert any(
            error.startswith("Identity resolution failed:")
            for error in report.stage_errors
        )
        # The backbone (comparison) still ran — PARTIAL, not FAILED.
        assert report.status is ExecutiveProcessingStatus.PARTIAL
        assert report.comparison_result is not None


class TestSearchStages:
    def test_search_results_flow_through_extraction_into_observations(self) -> None:
        extraction = FakeSearchExtraction()
        orchestrator = build_orchestrator(
            search_providers=[_search_provider_with_results()],
            search_extraction_engine=extraction,
        )

        report = orchestrator.process(executive_record(), "row:1")

        assert "browser_search" in report.providers_executed
        assert len(extraction.calls) == 1
        assert extraction.calls[0][0] == "row:1"
        extracted = [
            o
            for o in report.observations_collected
            if o.provider_id == "search_extraction"
        ]
        assert len(extracted) == 1
        assert report.status is ExecutiveProcessingStatus.SUCCESS

    def test_no_search_coordinator_means_no_search_stage(self) -> None:
        extraction = FakeSearchExtraction()
        orchestrator = build_orchestrator(search_extraction_engine=extraction)

        report = orchestrator.process(executive_record(), "row:1")

        assert extraction.calls == []
        assert report.providers_executed == ()

    def test_search_without_extraction_engine_records_providers_only(self) -> None:
        orchestrator = build_orchestrator(
            search_providers=[_search_provider_with_results()]
        )

        report = orchestrator.process(executive_record(), "row:1")

        assert "browser_search" in report.providers_executed
        assert report.observations_collected == ()
        # A missing extraction engine is a configuration choice, not a
        # stage failure.
        assert report.stage_errors == ()

    def test_no_search_results_skips_extraction_entirely(self) -> None:
        extraction = FakeSearchExtraction()
        orchestrator = build_orchestrator(
            search_providers=[_search_provider_with_results(results=())],
            search_extraction_engine=extraction,
        )

        report = orchestrator.process(executive_record(), "row:1")

        assert extraction.calls == []
        assert report.status is ExecutiveProcessingStatus.SUCCESS

    def test_search_stage_failure_is_recorded_and_pipeline_continues(self) -> None:
        invalid_profile = SearchProfile(
            name="broken",
            default_configuration=SearchProviderConfiguration(timeout_seconds=0),
        )
        orchestrator = build_orchestrator(
            search_providers=[_search_provider_with_results()],
            search_profile=invalid_profile,
            search_extraction_engine=FakeSearchExtraction(),
        )

        report = orchestrator.process(executive_record(), "row:1")

        assert any(error.startswith("Search failed:") for error in report.stage_errors)
        assert report.status is ExecutiveProcessingStatus.PARTIAL
        assert report.comparison_result is not None

    def test_extraction_stage_failure_keeps_search_providers_recorded(self) -> None:
        orchestrator = build_orchestrator(
            search_providers=[_search_provider_with_results()],
            search_extraction_engine=FakeSearchExtraction(raises=RuntimeError("boom")),
        )

        report = orchestrator.process(executive_record(), "row:1")

        assert "browser_search" in report.providers_executed
        assert any(
            error.startswith("Search extraction failed:")
            for error in report.stage_errors
        )
        assert report.status is ExecutiveProcessingStatus.PARTIAL


class TestProcessBatch:
    def test_batch_produces_one_report_per_record_in_input_order(self) -> None:
        orchestrator = build_orchestrator()
        records = [
            (executive_record(first_name="Ada", last_name="Lovelace"), "row:1"),
            (executive_record(first_name="Grace", last_name="Hopper"), "row:2"),
        ]

        report = orchestrator.process_batch(records)

        assert isinstance(report, ExecutiveIntelligenceReport)
        assert [r.subject_id for r in report.executive_reports] == ["row:1", "row:2"]
        assert [r.executive_name for r in report.executive_reports] == [
            "Ada Lovelace",
            "Grace Hopper",
        ]

    def test_batch_continues_past_a_failed_executive(self) -> None:
        no_name = executive_record(first_name="", last_name="")
        orchestrator = build_orchestrator()
        records = [
            (executive_record(), "row:1"),
            (no_name, "row:2"),
            (executive_record(first_name="Grace", last_name="Hopper"), "row:3"),
        ]

        report = orchestrator.process_batch(records)

        statuses = [r.status for r in report.executive_reports]
        assert statuses == [
            ExecutiveProcessingStatus.SUCCESS,
            ExecutiveProcessingStatus.FAILED,
            ExecutiveProcessingStatus.SUCCESS,
        ]

    def test_batch_statistics_reflect_every_report(self) -> None:
        no_name = executive_record(first_name="", last_name="")
        orchestrator = build_orchestrator()

        report = orchestrator.process_batch(
            [(executive_record(), "row:1"), (no_name, "row:2")]
        )

        statistics = report.statistics
        assert statistics.total_executives == 2
        assert statistics.succeeded == 1
        assert statistics.partial == 0
        assert statistics.failed == 1
        assert statistics.executives_with_errors == 1
        assert statistics.stage_errors_total == 1
        assert statistics.execution_time_total_ms >= 0.0
        assert report.duration_ms >= 0.0

    def test_unexpected_exception_for_one_record_yields_a_failed_report(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        orchestrator = build_orchestrator()
        original_process = orchestrator.process

        def exploding_process(
            existing_record: CleanedLeadRecord, subject_id: str
        ) -> ExecutiveProcessingReport:
            if subject_id == "row:2":
                raise RuntimeError("boom")
            return original_process(existing_record, subject_id)

        monkeypatch.setattr(orchestrator, "process", exploding_process)

        report = orchestrator.process_batch(
            [
                (executive_record(), "row:1"),
                (executive_record(first_name="Grace", last_name="Hopper"), "row:2"),
                (executive_record(first_name="Alan", last_name="Turing"), "row:3"),
            ]
        )

        assert len(report.executive_reports) == 3
        failed = report.executive_reports[1]
        assert failed.subject_id == "row:2"
        assert failed.status is ExecutiveProcessingStatus.FAILED
        assert "Unexpected error: boom" in failed.stage_errors
        assert failed.executive_name == "Grace Hopper"
        assert report.executive_reports[2].status is ExecutiveProcessingStatus.SUCCESS
        assert report.statistics.failed == 1
        assert report.statistics.succeeded == 2

    def test_empty_batch_yields_an_empty_report_with_zero_statistics(self) -> None:
        orchestrator = build_orchestrator()

        report = orchestrator.process_batch([])

        assert report.executive_reports == ()
        assert report.statistics.total_executives == 0
        assert report.statistics.succeeded == 0
