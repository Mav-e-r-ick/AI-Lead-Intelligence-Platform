"""CleaningPipeline: the Cleaning Engine's single orchestration point.

WHY THIS FILE EXISTS, AND WHY IT'S STAGE-DRIVEN:
This class never imports or names a specific rule. It's constructed with an
injected list of rules (dependency injection) and iterates them, grouped
by `metadata.stage`, in the order CLEANING_RULES.md specifies: Safe ->
Business (if enabled) -> Warning (always). Adding rule CLN-069 later means
writing one new rule class/instance and appending it to
application/cleaning/rules/__init__.py's ALL_RULES — this file does not
change. See README.md for the full walkthrough.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Sequence

from loguru import logger

from lead_intelligence.application.cleaning.config import CleaningProfile
from lead_intelligence.application.dto.cleaning_models import (
    CleanedLeadDataset,
    CleanedLeadRecord,
    CleaningMetrics,
    CleaningReport,
    CleaningResult,
    FieldChange,
    QualityWarning,
    RuleExecutionFailure,
    RuleMetrics,
)
from lead_intelligence.application.dto.models import ImportedLeadDataset, RawRecord
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleStage,
)
from lead_intelligence.domain.exceptions import RuleExecutionError


class _RuleAccumulator:
    """Mutable per-rule metrics accumulator, used only within one pipeline run."""

    def __init__(self, rule_id: str, rule_version: int) -> None:
        self.rule_id = rule_id
        self.rule_version = rule_version
        self.records_evaluated = 0
        self.records_affected = 0
        self.records_skipped = 0
        self.execution_time_total_ms = 0.0
        self.failure_count = 0
        self.warning_count = 0

    def to_metrics(self) -> RuleMetrics:
        return RuleMetrics(
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            records_evaluated=self.records_evaluated,
            records_affected=self.records_affected,
            records_skipped=self.records_skipped,
            execution_time_total_ms=self.execution_time_total_ms,
            failure_count=self.failure_count,
            warning_count=self.warning_count,
        )


class CleaningPipeline:
    """Runs every enabled rule over an ImportedLeadDataset, in three stages."""

    def __init__(
        self,
        rules: Sequence[NormalizationRule | QualityCheckRule],
        profile: CleaningProfile,
    ) -> None:
        """Configure a pipeline bound to one rule set and one profile.

        Args:
            rules: Every rule this pipeline may run (typically
                `application.cleaning.rules.ALL_RULES`, but any subset is
                valid — this is dependency injection, not a hardcoded list).
            profile: The active CleaningProfile.
        """

        self._rules = tuple(rules)
        self._profile = profile

    def run(self, dataset: ImportedLeadDataset) -> CleaningResult:
        """Clean every record in `dataset` and return a CleaningResult.

        Raises:
            InvalidCleaningConfigurationError: If the profile itself, or
                any enabled rule's configuration, is invalid — raised
                before any record is processed.
        """

        self._profile.validate()
        for rule in self._rules:
            rule.validate_config(self._profile)

        started_at = datetime.now(timezone.utc)
        logger.info(
            "Cleaning pipeline starting: profile='{}', {} record(s)",
            self._profile.name,
            len(dataset.records),
        )

        accumulators: dict[str, _RuleAccumulator] = {
            rule.metadata.rule_id: _RuleAccumulator(
                rule.metadata.rule_id, rule.metadata.version
            )
            for rule in self._rules
        }

        cleaned_records: list[CleanedLeadRecord] = []
        audit_trail: list[FieldChange | QualityWarning] = []
        records_with_changes = 0
        records_with_warnings = 0
        records_with_failures = 0

        for raw_record in dataset.records:
            cleaned_record, record_audit_entries = self._clean_one_record(
                raw_record, accumulators
            )
            cleaned_records.append(cleaned_record)
            audit_trail.extend(record_audit_entries)
            if cleaned_record.field_changes:
                records_with_changes += 1
            if cleaned_record.warnings:
                records_with_warnings += 1
            if cleaned_record.execution_failures:
                records_with_failures += 1

        completed_at = datetime.now(timezone.utc)

        per_rule_metrics = {
            rule_id: acc.to_metrics() for rule_id, acc in accumulators.items()
        }
        metrics = CleaningMetrics(
            records_processed=len(cleaned_records),
            rules_executed=sum(
                1 for acc in accumulators.values() if acc.records_evaluated > 0
            ),
            fields_modified=sum(len(r.field_changes) for r in cleaned_records),
            warnings_generated=sum(len(r.warnings) for r in cleaned_records),
            failures=sum(len(r.execution_failures) for r in cleaned_records),
            execution_time_total_ms=sum(
                acc.execution_time_total_ms for acc in accumulators.values()
            ),
            per_rule=per_rule_metrics,
        )
        report = CleaningReport(
            profile_name=self._profile.name,
            profile_version=self._profile.version,
            started_at=started_at,
            completed_at=completed_at,
            records_processed=len(cleaned_records),
            records_with_changes=records_with_changes,
            records_with_warnings=records_with_warnings,
            records_with_failures=records_with_failures,
            metrics=metrics,
        )

        logger.info(
            "Cleaning pipeline complete: {} record(s), {} field change(s), "
            "{} warning(s), {} failure(s), {:.1f}ms",
            metrics.records_processed,
            metrics.fields_modified,
            metrics.warnings_generated,
            metrics.failures,
            metrics.execution_time_total_ms,
        )

        cleaned_dataset = CleanedLeadDataset(
            cleaned_records=tuple(cleaned_records), source_metadata=dataset.metadata
        )
        return CleaningResult(
            cleaned_dataset=cleaned_dataset,
            report=report,
            metrics=metrics,
            audit_trail=tuple(audit_trail),
        )

    def _clean_one_record(
        self, raw_record: RawRecord, accumulators: dict[str, _RuleAccumulator]
    ) -> tuple[CleanedLeadRecord, list[FieldChange | QualityWarning]]:
        values: dict[str, object] = {
            canonical: raw_record.values.get(literal)
            for canonical, literal in self._profile.field_mapping.items()
        }

        field_changes: list[FieldChange] = []
        warnings: list[QualityWarning] = []
        execution_failures: list[RuleExecutionFailure] = []
        audit_entries: list[FieldChange | QualityWarning] = []

        for rule in self._rules:
            if (
                isinstance(rule, NormalizationRule)
                and rule.metadata.stage == RuleStage.SAFE
            ):
                self._run_normalization_rule(
                    rule,
                    values,
                    accumulators,
                    field_changes,
                    audit_entries,
                    execution_failures,
                )

        if self._profile.enable_business_normalization:
            for rule in self._rules:
                if (
                    isinstance(rule, NormalizationRule)
                    and rule.metadata.stage == RuleStage.BUSINESS
                ):
                    acc = accumulators[rule.metadata.rule_id]
                    if not self._profile.is_enabled(rule):
                        acc.records_skipped += 1
                        continue
                    self._run_normalization_rule(
                        rule,
                        values,
                        accumulators,
                        field_changes,
                        audit_entries,
                        execution_failures,
                    )
        else:
            for rule in self._rules:
                if (
                    isinstance(rule, NormalizationRule)
                    and rule.metadata.stage == RuleStage.BUSINESS
                ):
                    accumulators[rule.metadata.rule_id].records_skipped += 1

        for rule in self._rules:
            if isinstance(rule, QualityCheckRule):
                acc = accumulators[rule.metadata.rule_id]
                if not self._profile.is_enabled(rule):
                    acc.records_skipped += 1
                    continue
                self._run_quality_check_rule(
                    rule, values, accumulators, warnings, audit_entries
                )

        cleaned_record = CleanedLeadRecord(
            raw_record=raw_record,
            cleaned_values=values,
            field_changes=tuple(field_changes),
            warnings=tuple(warnings),
            execution_failures=tuple(execution_failures),
        )
        return cleaned_record, audit_entries

    def _run_normalization_rule(
        self,
        rule: NormalizationRule,
        values: dict[str, object],
        accumulators: dict[str, _RuleAccumulator],
        field_changes: list[FieldChange],
        audit_entries: list[FieldChange | QualityWarning],
        execution_failures: list[RuleExecutionFailure],
    ) -> None:
        acc = accumulators[rule.metadata.rule_id]
        acc.records_evaluated += 1
        start = time.perf_counter()
        try:
            changes = rule.apply(values, self._profile)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - fail-safe: one bad rule must not sink the batch
            acc.failure_count += 1
            timestamp = datetime.now(timezone.utc)
            failure = RuleExecutionFailure(
                rule_id=rule.metadata.rule_id,
                rule_version=rule.metadata.version,
                error_message=str(RuleExecutionError(str(exc))),
                timestamp=timestamp,
            )
            execution_failures.append(failure)
            logger.warning(
                "Rule {} v{} raised an unexpected exception and was skipped for this record: {}",
                rule.metadata.rule_id,
                rule.metadata.version,
                exc,
            )
            return
        finally:
            acc.execution_time_total_ms += (time.perf_counter() - start) * 1000

        if changes:
            acc.records_affected += 1
            timestamp = datetime.now(timezone.utc)
            for field_name, new_value in changes.items():
                old_value = values.get(field_name)
                if old_value == new_value:
                    continue
                change = FieldChange(
                    rule_id=rule.metadata.rule_id,
                    rule_version=rule.metadata.version,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    stage=rule.metadata.stage.value,
                    timestamp=timestamp,
                )
                field_changes.append(change)
                audit_entries.append(change)
                values[field_name] = new_value
                logger.debug(
                    "{} v{}: {} changed ({!r} -> {!r})",
                    rule.metadata.rule_id,
                    rule.metadata.version,
                    field_name,
                    old_value,
                    new_value,
                )

    def _run_quality_check_rule(
        self,
        rule: QualityCheckRule,
        values: dict[str, object],
        accumulators: dict[str, _RuleAccumulator],
        warnings: list[QualityWarning],
        audit_entries: list[FieldChange | QualityWarning],
    ) -> None:
        acc = accumulators[rule.metadata.rule_id]
        acc.records_evaluated += 1
        start = time.perf_counter()
        try:
            drafts = rule.apply(values, self._profile)
        except (
            Exception
        ) as exc:  # noqa: BLE001 - fail-safe, see _run_normalization_rule
            acc.failure_count += 1
            logger.warning(
                "Rule {} v{} raised an unexpected exception and was skipped for this record: {}",
                rule.metadata.rule_id,
                rule.metadata.version,
                exc,
            )
            return
        finally:
            acc.execution_time_total_ms += (time.perf_counter() - start) * 1000

        if drafts:
            acc.records_affected += 1
            acc.warning_count += len(drafts)
            timestamp = datetime.now(timezone.utc)
            for draft in drafts:
                warning = QualityWarning(
                    rule_id=rule.metadata.rule_id,
                    rule_version=rule.metadata.version,
                    code=draft.code,
                    message=draft.message,
                    field_names=draft.field_names,
                    timestamp=timestamp,
                )
                warnings.append(warning)
                audit_entries.append(warning)
                logger.debug(
                    "{} v{}: warning {}",
                    rule.metadata.rule_id,
                    rule.metadata.version,
                    draft.code,
                )
