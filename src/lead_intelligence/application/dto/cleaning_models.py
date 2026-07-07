"""Plain data shapes produced by the Cleaning Engine.

WHY THIS FILE EXISTS (SEPARATE FROM models.py):
models.py holds the Import Engine's output shapes (RawRecord,
ImportedLeadDataset, ...). This file holds the Cleaning Engine's — kept
separate because they're each a complete, cohesive vocabulary for their own
stage, and a file per stage's output keeps either one from growing into an
unrelated grab-bag as more stages (verification, enrichment) are added later.

Every dataclass here is immutable (frozen, tuple fields) for the same
reason as the Import Engine's DTOs: once a stage hands back its result, no
downstream code should be able to silently mutate it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from lead_intelligence.application.dto.models import RawRecord, SourceMetadata


@dataclass(frozen=True)
class FieldChange:
    """One value actually changed by one rule, on one record.

    Attributes:
        rule_id: The permanent Rule ID (e.g. "CLN-004") from CLEANING_RULES.md.
        rule_version: The rule's own version at the time it ran (see
            CLEANING_RULES.md's Versioning Strategy — this is what lets a
            historical change be traced to the exact logic that produced it).
        field_name: The field that changed.
        old_value: The value before this rule ran.
        new_value: The value after this rule ran.
        stage: Which pipeline stage produced this change ("safe" or "business").
        timestamp: UTC time this change was recorded.
    """

    rule_id: str
    rule_version: int
    field_name: str
    old_value: Any
    new_value: Any
    stage: str
    timestamp: datetime


@dataclass(frozen=True)
class QualityWarningDraft:
    """An unstamped warning, as returned directly by a QualityCheckRule.

    Deliberately minimal — a QualityCheckRule only knows *what* it observed,
    not *when* or *by which rule/version*. CleaningPipeline stamps a draft
    into a full QualityWarning. This split is what makes it structurally
    impossible for a QualityCheckRule to fabricate rule_id/version metadata
    for a rule other than itself.
    """

    code: str
    message: str
    field_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityWarning:
    """A stamped, non-destructive observation about a record's data.

    Never implies a value changed — QualityCheckRule's interface makes that
    structurally impossible (see application/ports/cleaning_rule_port.py).
    """

    rule_id: str
    rule_version: int
    code: str
    message: str
    field_names: tuple[str, ...]
    timestamp: datetime


@dataclass(frozen=True)
class RuleExecutionFailure:
    """An engineering fault: a rule itself raised an unexpected exception.

    Distinct from QualityWarning on purpose — this is a bug signal about the
    *pipeline*, not an observation about the *data*, and must be
    distinguishable at a glance (see CLEANING_RULES.md's Logging Strategy).
    """

    rule_id: str
    rule_version: int
    error_message: str
    timestamp: datetime


@dataclass(frozen=True)
class CleanedLeadRecord:
    """The complete result of cleaning one RawRecord.

    Attributes:
        raw_record: The original, untouched RawRecord — always retained, so
            this record is diffable against its true source at any time.
        cleaned_values: Canonical-field-name -> cleaned value, after every
            enabled Safe and Business rule has run.
        field_changes: Full audit trail of every value this record's rules
            actually changed (append-only; nothing here is ever edited).
        warnings: Every QualityWarning raised for this record.
        execution_failures: Any RuleExecutionFailure encountered for this
            record — normally empty; non-empty means a rule bug, not a data
            problem.
    """

    raw_record: RawRecord
    cleaned_values: Mapping[str, Any]
    field_changes: tuple[FieldChange, ...]
    warnings: tuple[QualityWarning, ...]
    execution_failures: tuple[RuleExecutionFailure, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "cleaned_values", MappingProxyType(dict(self.cleaned_values))
        )


@dataclass(frozen=True)
class CleanedLeadDataset:
    """Every cleaned record from one CleaningPipeline run, plus provenance."""

    cleaned_records: tuple[CleanedLeadRecord, ...]
    source_metadata: SourceMetadata

    @property
    def record_count(self) -> int:
        """Number of records in this dataset."""

        return len(self.cleaned_records)


@dataclass(frozen=True)
class RuleMetrics:
    """Metrics collected for one rule, for one CleaningPipeline run.

    Field meanings match CLEANING_RULES.md §8 exactly.
    """

    rule_id: str
    rule_version: int
    records_evaluated: int = 0
    records_affected: int = 0
    records_skipped: int = 0
    execution_time_total_ms: float = 0.0
    failure_count: int = 0
    warning_count: int = 0

    @property
    def execution_time_avg_ms_per_record(self) -> float:
        """Average per-record execution time, or 0.0 if never evaluated."""

        if self.records_evaluated == 0:
            return 0.0
        return self.execution_time_total_ms / self.records_evaluated


@dataclass(frozen=True)
class CleaningMetrics:
    """Aggregate metrics for one full CleaningPipeline run."""

    records_processed: int
    rules_executed: int
    fields_modified: int
    warnings_generated: int
    failures: int
    execution_time_total_ms: float
    per_rule: Mapping[str, RuleMetrics]

    def __post_init__(self) -> None:
        object.__setattr__(self, "per_rule", MappingProxyType(dict(self.per_rule)))


@dataclass(frozen=True)
class CleaningReport:
    """The human-readable digest of one CleaningPipeline run.

    Where CleaningMetrics is raw numbers, this is the narrative built from
    them plus run/profile identity — the thing you'd actually print or log
    as a summary.
    """

    profile_name: str
    profile_version: str
    started_at: datetime
    completed_at: datetime
    records_processed: int
    records_with_changes: int
    records_with_warnings: int
    records_with_failures: int
    metrics: CleaningMetrics

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the run, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass(frozen=True)
class CleaningResult:
    """The Cleaning Engine's single output type.

    Attributes:
        cleaned_dataset: Every cleaned record plus source provenance.
        report: The human-readable run digest.
        metrics: The raw per-rule and aggregate numbers the report is built from.
        audit_trail: Every FieldChange and QualityWarning raised across the
            whole run, flattened into one run-wide, chronologically-ordered
            sequence — a convenience view; the same entries also live on
            each individual CleanedLeadRecord.
    """

    cleaned_dataset: CleanedLeadDataset
    report: CleaningReport
    metrics: CleaningMetrics
    audit_trail: tuple[FieldChange | QualityWarning, ...]
