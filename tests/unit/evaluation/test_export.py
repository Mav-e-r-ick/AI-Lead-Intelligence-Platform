"""Tests for export.write_csv_report / write_summary_report / write_evaluation_run."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from lead_intelligence.application.dto.evaluation_models import (
    EvaluationRun,
    EvaluationSummary,
    ExecutiveEvaluationRow,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.evaluation.export import (
    write_csv_report,
    write_evaluation_run,
    write_summary_report,
)


def _row(subject_id: str = "row:1") -> ExecutiveEvaluationRow:
    return ExecutiveEvaluationRow(
        subject_id=subject_id,
        executive_name="Ada Lovelace",
        company="Acme Corp",
        website_searched="https://acme.com",
        providers_executed="company_website,google_search",
        company_website_results_found=1,
        google_results_found=2,
        observations_collected=3,
        comparison_summary="matched=5 changed=0 missing=0 new=0 conflict=0 unknown=0 confidence=1.00",
        inflections_detected="none",
        verification_status="valid",
        processing_duration_ms=12.5,
        errors="",
        status=ExecutiveProcessingStatus.SUCCESS,
    )


def _run(rows: tuple[ExecutiveEvaluationRow, ...]) -> EvaluationRun:
    summary = EvaluationSummary(
        total_executives_processed=len(rows),
        success_rate=100.0,
        failed_searches=0,
        company_websites_found=1,
        google_searches_completed=1,
        promotions_detected=0,
        company_changes_detected=0,
        missing_executives=0,
        verification_success_rate=100.0,
    )
    return EvaluationRun(
        source_description="executives.xlsx",
        rows=rows,
        summary=summary,
        started_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        completed_at=datetime(2024, 6, 1, 0, 0, 1, tzinfo=timezone.utc),
    )


class TestWriteCsvReport:
    def test_writes_header_and_one_row_per_executive(self, tmp_path: Path) -> None:
        rows = (_row("row:1"), _row("row:2"))
        destination = tmp_path / "report.csv"

        write_csv_report(rows, destination)

        with destination.open(newline="", encoding="utf-8") as handle:
            reader = list(csv.DictReader(handle))

        assert len(reader) == 2
        assert reader[0]["subject_id"] == "row:1"
        assert reader[0]["executive_name"] == "Ada Lovelace"
        assert reader[0]["status"] == "success"

    def test_none_fields_become_blank_strings(self, tmp_path: Path) -> None:
        row = ExecutiveEvaluationRow(
            subject_id="row:1",
            executive_name=None,
            company=None,
            website_searched=None,
            providers_executed="",
            company_website_results_found=0,
            google_results_found=0,
            observations_collected=0,
            comparison_summary="not_compared",
            inflections_detected="not_detected",
            verification_status="no_email",
            processing_duration_ms=0.0,
            errors="",
            status=ExecutiveProcessingStatus.FAILED,
        )
        destination = tmp_path / "report.csv"

        write_csv_report((row,), destination)

        with destination.open(newline="", encoding="utf-8") as handle:
            reader = list(csv.DictReader(handle))

        assert reader[0]["executive_name"] == ""
        assert reader[0]["company"] == ""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        destination = tmp_path / "nested" / "dir" / "report.csv"

        write_csv_report((_row(),), destination)

        assert destination.exists()


class TestWriteSummaryReport:
    def test_writes_valid_json_with_summary_fields(self, tmp_path: Path) -> None:
        run = _run((_row(),))
        destination = tmp_path / "summary.json"

        write_summary_report(run, destination)

        payload = json.loads(destination.read_text(encoding="utf-8"))

        assert payload["source_description"] == "executives.xlsx"
        assert payload["row_count"] == 1
        assert payload["summary"]["total_executives_processed"] == 1
        assert payload["summary"]["success_rate"] == 100.0

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        run = _run((_row(),))
        destination = tmp_path / "nested" / "summary.json"

        write_summary_report(run, destination)

        assert destination.exists()


class TestWriteEvaluationRun:
    def test_writes_both_files(self, tmp_path: Path) -> None:
        run = _run((_row("row:1"), _row("row:2")))
        csv_path = tmp_path / "report.csv"
        summary_path = tmp_path / "summary.json"

        write_evaluation_run(run, csv_path, summary_path)

        assert csv_path.exists()
        assert summary_path.exists()
        with csv_path.open(newline="", encoding="utf-8") as handle:
            assert len(list(csv.DictReader(handle))) == 2
