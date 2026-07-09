"""Plain data shapes produced by the Executive Processing Pipeline.

WHY THIS FILE EXISTS (SEPARATE FROM comparison_models.py / inflection_models.py / etc.):
Same reasoning as every other stage's own DTO file's docstring: each
pipeline stage gets one cohesive vocabulary file, so none of them grows
into an unrelated grab-bag as more stages are added.

WHY THIS REPORT EMBEDS THE FULL RESULT TYPES FROM EACH STAGE, RATHER THAN
FLATTENING THEM INTO NEW FIELDS:
The Executive Processing Pipeline composes engines that already have their
own rich, well-tested output types (ComparisonResult, InflectionReport,
VerificationReport) — duplicating their fields here would be exactly the
kind of "framework redesign" this task's scope explicitly excludes.
Instead, `ExecutiveProcessingReport` carries each stage's real output
object directly (or None if that stage didn't run), so nothing about a
stage's own result is ever lost, renamed, or reinterpreted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from lead_intelligence.application.dto.comparison_models import ComparisonResult
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityResolutionOutcome,
)
from lead_intelligence.application.dto.inflection_models import InflectionReport
from lead_intelligence.application.dto.verification_models import VerificationReport

__all__ = [
    "ExecutiveProcessingStatus",
    "ExecutiveProcessingReport",
    "ExecutiveBatchStatistics",
    "ExecutiveIntelligenceReport",
]


class ExecutiveProcessingStatus(str, Enum):
    """The overall outcome of one executive's run through the pipeline.

    SUCCESS: every stage that was applicable ran without error.
    PARTIAL: the Executive Comparison Engine produced a ComparisonResult
        (the pipeline's backbone — Inflection Detection depends on it),
        but at least one other stage (enrichment, inflection detection, or
        verification) encountered an error along the way.
    FAILED: no ComparisonResult could be produced at all — either because
        no executive name could be resolved from the input record (the
        pipeline never started), or because the Executive Comparison
        Engine itself failed.
    """

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutiveProcessingReport:
    """The Executive Processing Pipeline's single output type for one
    executive.

    Attributes:
        subject_id: The opaque id this executive was processed under —
            passed identically to enrichment, comparison, and
            verification, so every stage's own result can be traced back
            to the same run.
        executive_name: The executive's full name, resolved from the input
            record via the same `resolve_name` the Executive Comparison
            Engine itself uses — None only when FAILED for that reason.
        providers_executed: Every enrichment provider_id that actually ran
            (Company Website, Google Search — whichever were applicable
            and enabled), in execution order. Empty if the enrichment
            stage did not run or failed before any provider executed.
        observations_collected: Every ObservationCandidate collected
            across every executed provider — the same aggregated view
            EnrichmentCoordinationResult.observations already provides.
        comparison_result: The Executive Comparison Engine's full output
            (field-by-field verdicts plus its ComparisonSummary), or None
            if this stage did not run or failed.
        inflection_report: The Inflection Detection Engine's full output
            (every detected business event), or None if this stage did
            not run (requires a comparison_result) or failed.
        verification_report: The Verification Coordinator's full output
            for the executive's known email address, or None if no
            VerificationCoordinator was configured, no email was known, or
            this stage failed.
        status: The overall outcome — see ExecutiveProcessingStatus.
        stage_errors: A human-readable message per stage that raised an
            unexpected exception, in the order encountered. Empty when
            status is SUCCESS.
        started_at: When this executive's processing began.
        completed_at: When this executive's processing finished.
        identity_resolution_outcome: The Identity Resolution Engine's full
            decision for this record (auto-merge / candidate review / new
            identity, with its extracted identity and scored candidates),
            or None if no IdentityResolutionEngine was configured or that
            stage failed. Appended with a None default so every existing
            construction site (and the Evaluation module's fixtures)
            stays valid unchanged.
    """

    subject_id: str
    executive_name: str | None
    providers_executed: tuple[str, ...]
    observations_collected: tuple[ObservationCandidate, ...]
    comparison_result: ComparisonResult | None
    inflection_report: InflectionReport | None
    verification_report: VerificationReport | None
    status: ExecutiveProcessingStatus
    stage_errors: tuple[str, ...]
    started_at: datetime
    completed_at: datetime
    identity_resolution_outcome: IdentityResolutionOutcome | None = None

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of this executive's processing, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass(frozen=True)
class ExecutiveBatchStatistics:
    """Aggregate statistics for one ExecutiveProcessingOrchestrator batch run.

    Attributes:
        total_executives: How many records went in.
        succeeded / partial / failed: How many reports finished with each
            ExecutiveProcessingStatus.
        executives_with_errors: How many reports carry at least one stage
            error (a superset of `failed` — a PARTIAL report has errors
            too).
        stage_errors_total: Every stage error across every report, summed.
        execution_time_total_ms: Wall-clock time spent inside per-executive
            processing, summed (a real measurement, deliberately excluded
            from any determinism guarantee, like every other engine's own
            execution-time metric).
    """

    total_executives: int
    succeeded: int
    partial: int
    failed: int
    executives_with_errors: int
    stage_errors_total: int
    execution_time_total_ms: float


@dataclass(frozen=True)
class ExecutiveIntelligenceReport:
    """The pipeline's single final report object for one batch of
    executives — the "Final Executive Intelligence Report."

    Attributes:
        executive_reports: One ExecutiveProcessingReport per input record,
            in input order — including a FAILED report (never a gap) for
            any record whose processing raised unexpectedly.
        statistics: The batch-level numbers above.
        started_at: When the batch began.
        completed_at: When the batch finished.
    """

    executive_reports: tuple[ExecutiveProcessingReport, ...]
    statistics: ExecutiveBatchStatistics
    started_at: datetime
    completed_at: datetime

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the whole batch, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000
