"""Unit tests for PipelineRunner, using a real Import Engine + Cleaning
Engine (via a tiny in-memory workbook) and a fake ProcessExecutiveUseCase
(so no real enrichment/comparison/inflection/verification I/O runs here —
those are already covered by their own engines' test suites and by
tests/integration/test_executive_pipeline.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from lead_intelligence.application.cleaning.config import default_profile
from lead_intelligence.application.cleaning.pipeline import CleaningPipeline
from lead_intelligence.application.cleaning.rules import ALL_RULES
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingReport,
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.evaluation.runner import PipelineRunner
from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase
from lead_intelligence.infrastructure.importers.excel.excel_reader import (
    ExcelSourceReader,
)
from tests.fixtures.excel_builder import build_workbook
from tests.unit.evaluation.fixtures import fixed_clock, make_report


class FakeProcessExecutiveUseCase:
    """A ProcessExecutiveUseCase stand-in — same `.execute()` shape,
    fully scripted, no real pipeline stages involved."""

    def __init__(
        self,
        handler: (
            Callable[[CleanedLeadRecord, str], ExecutiveProcessingReport] | None
        ) = None,
    ) -> None:
        self._handler = handler
        self.calls: list[tuple[CleanedLeadRecord, str]] = []

    def execute(
        self, existing_record: CleanedLeadRecord, subject_id: str
    ) -> ExecutiveProcessingReport:
        self.calls.append((existing_record, subject_id))
        if self._handler is not None:
            return self._handler(existing_record, subject_id)
        return make_report(subject_id=subject_id)


def _build_workbook(tmp_path: Path) -> Path:
    return build_workbook(
        tmp_path,
        {
            "Sheet1": [
                ["First Name", "Last Name", "Company Name", "URL", "Email"],
                ["Ada", "Lovelace", "Acme Corp", "https://acme.com", "ada@acme.com"],
                [
                    "Grace",
                    "Hopper",
                    "Contoso",
                    "https://contoso.com",
                    "grace@contoso.com",
                ],
            ]
        },
    )


def _runner(
    tmp_path: Path, process_use_case: FakeProcessExecutiveUseCase
) -> PipelineRunner:
    workbook_path = _build_workbook(tmp_path)
    import_use_case = ImportDatasetUseCase(ExcelSourceReader(workbook_path))
    clean_use_case = CleanDatasetUseCase(CleaningPipeline(ALL_RULES, default_profile()))
    return PipelineRunner(
        import_use_case,
        clean_use_case,
        process_use_case,  # type: ignore[arg-type]
        clock=fixed_clock,
    )


class TestPipelineRunner:
    def test_processes_every_record_in_the_workbook(self, tmp_path: Path) -> None:
        process_use_case = FakeProcessExecutiveUseCase()
        runner = _runner(tmp_path, process_use_case)

        run = runner.run()

        assert len(run.rows) == 2
        assert len(process_use_case.calls) == 2

    def test_subject_id_is_derived_from_row_number(self, tmp_path: Path) -> None:
        process_use_case = FakeProcessExecutiveUseCase()
        runner = _runner(tmp_path, process_use_case)

        runner.run()

        subject_ids = {subject_id for _, subject_id in process_use_case.calls}
        assert subject_ids == {"row:2", "row:3"}

    def test_summary_reflects_all_processed_rows(self, tmp_path: Path) -> None:
        process_use_case = FakeProcessExecutiveUseCase()
        runner = _runner(tmp_path, process_use_case)

        run = runner.run()

        assert run.summary.total_executives_processed == 2
        assert run.summary.success_rate == 100.0

    def test_source_description_defaults_to_sheet_name(self, tmp_path: Path) -> None:
        process_use_case = FakeProcessExecutiveUseCase()
        runner = _runner(tmp_path, process_use_case)

        run = runner.run()

        assert run.source_description == "Sheet1"

    def test_source_description_can_be_overridden(self, tmp_path: Path) -> None:
        process_use_case = FakeProcessExecutiveUseCase()
        runner = _runner(tmp_path, process_use_case)

        run = runner.run(source_description="executives.xlsx")

        assert run.source_description == "executives.xlsx"

    def test_unexpected_exception_for_one_record_is_caught_and_reported(
        self, tmp_path: Path
    ) -> None:
        def handler(
            record: CleanedLeadRecord, subject_id: str
        ) -> ExecutiveProcessingReport:
            if subject_id == "row:3":
                raise RuntimeError("boom")
            return make_report(subject_id=subject_id)

        process_use_case = FakeProcessExecutiveUseCase(handler)
        runner = _runner(tmp_path, process_use_case)

        run = runner.run()

        assert len(run.rows) == 2
        failing_row = next(row for row in run.rows if row.subject_id == "row:3")
        assert failing_row.status is ExecutiveProcessingStatus.FAILED
        assert "Unexpected error: boom" in failing_row.errors
        succeeding_row = next(row for row in run.rows if row.subject_id == "row:2")
        assert succeeding_row.status is ExecutiveProcessingStatus.SUCCESS

    def test_duration_is_non_negative(self, tmp_path: Path) -> None:
        process_use_case = FakeProcessExecutiveUseCase()
        runner = _runner(tmp_path, process_use_case)

        run = runner.run()

        assert run.duration_ms >= 0.0
