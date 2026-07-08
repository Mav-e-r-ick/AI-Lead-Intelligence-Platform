"""PipelineRunner: the Evaluation & Validation module's single
orchestration point.

Given an already-configured Import Engine, Cleaning Engine, and Executive
Processing Pipeline (via their existing use cases — nothing here
constructs or configures any of them), runs every executive in one Excel
file through the full pipeline and returns one EvaluationRun: a row per
executive plus aggregate summary metrics.

WHY THIS CLASS ONLY CALLS EXISTING USE CASES, NEVER AN ENGINE DIRECTLY:
This task's explicit scope is "measure the current platform," not extend
it — no new provider, no AI, no automation, no redesign of any existing
module. `ImportDatasetUseCase`, `CleanDatasetUseCase`, and
`ProcessExecutiveUseCase` are the exact same stable seams every other
caller of this platform uses; PipelineRunner is simply a new caller that
happens to run all three, once per row, and export what came back.

WHY EACH EXECUTIVE IS WRAPPED IN ITS OWN try/except, EVEN THOUGH
ExecutiveProcessingOrchestrator ALREADY NEVER RAISES FOR AN ORDINARY
FAILURE:
Evaluation runs are meant to survive real, messy datasets unattended —
one truly unexpected bug on row 400 of 500 must not discard the 399 rows
already evaluated. This mirrors the same "one bad record never sinks the
whole run" philosophy used by every coordinator in this platform, applied
once more at the batch level.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison.resolvers import (
    resolve_company,
    resolve_name,
)
from lead_intelligence.application.dto.evaluation_models import (
    EvaluationRun,
    ExecutiveEvaluationRow,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.evaluation.metrics import compute_summary
from lead_intelligence.application.evaluation.row_builder import build_row
from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase
from lead_intelligence.application.use_cases.process_executive import (
    ProcessExecutiveUseCase,
)


class PipelineRunner:
    """Runs the Executive Processing Pipeline over every executive in one
    imported, cleaned dataset and returns one EvaluationRun."""

    def __init__(
        self,
        import_use_case: ImportDatasetUseCase,
        clean_use_case: CleanDatasetUseCase,
        process_executive_use_case: ProcessExecutiveUseCase,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure a runner bound to already-configured use cases.

        Args:
            import_use_case: An ImportDatasetUseCase already bound to a
                source reader pointed at one Excel file.
            clean_use_case: A CleanDatasetUseCase already constructed with
                its CleaningPipeline.
            process_executive_use_case: A ProcessExecutiveUseCase already
                constructed with its ExecutiveProcessingOrchestrator.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._import_use_case = import_use_case
        self._clean_use_case = clean_use_case
        self._process_executive_use_case = process_executive_use_case
        self._clock = clock

    def run(
        self,
        sheet_name: str | None = None,
        source_description: str | None = None,
    ) -> EvaluationRun:
        """Import, clean, and process every executive, and return one
        EvaluationRun.

        Args:
            sheet_name: Optional explicit sheet/table to import. If
                omitted, the configured source reader selects one
                automatically.
            source_description: A human-readable description of what was
                evaluated (e.g. the source file path), carried onto the
                returned EvaluationRun for traceability. Defaults to the
                resolved sheet name if omitted.

        Returns:
            One EvaluationRun containing a row per executive and the
            aggregate EvaluationSummary computed from them.
        """

        started_at = self._clock()
        logger.info("Pipeline evaluation run starting (sheet={})", sheet_name or "auto")

        dataset = self._import_use_case.execute(sheet_name)
        cleaning_result = self._clean_use_case.execute(dataset)
        records = cleaning_result.cleaned_dataset.cleaned_records

        rows: list[ExecutiveEvaluationRow] = []
        for record in records:
            subject_id = f"row:{record.raw_record.row_number}"
            try:
                report = self._process_executive_use_case.execute(record, subject_id)
                rows.append(build_row(report, record.cleaned_values))
            except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
                logger.error(
                    "Evaluation: unexpected error processing subject_id={}: {}",
                    subject_id,
                    exc,
                )
                rows.append(_error_row(subject_id, record.cleaned_values, exc))

        summary = compute_summary(rows)
        completed_at = self._clock()

        logger.info(
            "Pipeline evaluation run complete: {} executive(s) processed, "
            "{:.1f}% success rate, {:.1f}% verification success rate",
            summary.total_executives_processed,
            summary.success_rate,
            summary.verification_success_rate,
        )

        return EvaluationRun(
            source_description=source_description
            or cleaning_result.cleaned_dataset.source_metadata.sheet_name,
            rows=tuple(rows),
            summary=summary,
            started_at=started_at,
            completed_at=completed_at,
        )


def _error_row(
    subject_id: str, cleaned_values: Mapping[str, Any], exc: Exception
) -> ExecutiveEvaluationRow:
    """A minimal ExecutiveEvaluationRow for a record that raised an
    unexpected exception outside the Executive Processing Pipeline's own
    fail-safe handling — should be rare in practice, since
    ExecutiveProcessingOrchestrator.process() itself never raises for an
    ordinary failure."""

    return ExecutiveEvaluationRow(
        subject_id=subject_id,
        executive_name=resolve_name(cleaned_values),
        company=resolve_company(cleaned_values),
        website_searched=_blank_to_none(cleaned_values.get(fc.URL)),
        providers_executed="",
        company_website_results_found=0,
        google_results_found=0,
        observations_collected=0,
        comparison_summary="not_compared",
        inflections_detected="not_detected",
        verification_status="error",
        processing_duration_ms=0.0,
        errors=f"Unexpected error: {exc}",
        status=ExecutiveProcessingStatus.FAILED,
    )


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
