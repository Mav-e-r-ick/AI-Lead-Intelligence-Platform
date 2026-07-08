"""Exports one EvaluationRun to disk: a per-executive CSV report, plus a
JSON summary/processing report.

WHY TWO FILES, NOT ONE:
The per-executive rows (`ExecutiveEvaluationRow`) are naturally tabular —
a CSV, opened directly in a spreadsheet, is the right shape for "look at
executive #214's result." The aggregate metrics (`EvaluationSummary`) are
a handful of numbers meant to be read at a glance or consumed by another
tool — a small JSON processing report is the right shape for that, and
keeping it separate means the CSV's column set never has to accommodate
run-level metadata that doesn't vary per row.
"""

from __future__ import annotations

import csv
import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Sequence

from loguru import logger

from lead_intelligence.application.dto.evaluation_models import (
    EvaluationRun,
    ExecutiveEvaluationRow,
)

#: CSV column order, taken directly from ExecutiveEvaluationRow's own
#: field order — one column per field, so the exported CSV can never
#: silently drift out of sync with the dataclass it's built from.
_CSV_FIELDNAMES: tuple[str, ...] = tuple(
    field.name for field in fields(ExecutiveEvaluationRow)
)


def write_csv_report(rows: Sequence[ExecutiveEvaluationRow], path: str | Path) -> None:
    """Write one CSV row per ExecutiveEvaluationRow to `path`.

    Args:
        rows: Every row to export, in the order they should appear.
        path: Destination file path. Parent directories are created if
            they don't already exist.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(_row_to_csv_dict(row))

    logger.info("Wrote {} row(s) to CSV report: {}", len(rows), destination)


def write_summary_report(run: EvaluationRun, path: str | Path) -> None:
    """Write `run`'s metadata and EvaluationSummary as a JSON processing
    report to `path`.

    Args:
        run: The EvaluationRun to export (only its summary and
            run-level metadata are written here — see module docstring
            for why the per-executive rows are a separate CSV export).
        path: Destination file path. Parent directories are created if
            they don't already exist.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "source_description": run.source_description,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat(),
        "duration_ms": run.duration_ms,
        "row_count": len(run.rows),
        "summary": {
            "total_executives_processed": run.summary.total_executives_processed,
            "success_rate": run.summary.success_rate,
            "failed_searches": run.summary.failed_searches,
            "company_websites_found": run.summary.company_websites_found,
            "google_searches_completed": run.summary.google_searches_completed,
            "promotions_detected": run.summary.promotions_detected,
            "company_changes_detected": run.summary.company_changes_detected,
            "missing_executives": run.summary.missing_executives,
            "verification_success_rate": run.summary.verification_success_rate,
        },
    }

    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    logger.info("Wrote processing summary report: {}", destination)


def write_evaluation_run(
    run: EvaluationRun, csv_path: str | Path, summary_path: str | Path
) -> None:
    """Convenience wrapper: export `run`'s rows to `csv_path` and its
    summary to `summary_path`."""

    write_csv_report(run.rows, csv_path)
    write_summary_report(run, summary_path)


def _row_to_csv_dict(row: ExecutiveEvaluationRow) -> dict[str, Any]:
    return {
        "subject_id": row.subject_id,
        "executive_name": row.executive_name or "",
        "company": row.company or "",
        "website_searched": row.website_searched or "",
        "providers_executed": row.providers_executed,
        "company_website_results_found": row.company_website_results_found,
        "google_results_found": row.google_results_found,
        "observations_collected": row.observations_collected,
        "comparison_summary": row.comparison_summary,
        "inflections_detected": row.inflections_detected,
        "verification_status": row.verification_status,
        "processing_duration_ms": row.processing_duration_ms,
        "errors": row.errors,
        "status": row.status.value,
    }
