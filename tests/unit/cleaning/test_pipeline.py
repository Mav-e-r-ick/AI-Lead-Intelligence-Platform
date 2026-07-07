"""Unit tests for CleaningPipeline, using small fake rules instead of the
real 68-rule registry — isolates orchestration logic (stage ordering, the
business master switch, fail-safe error handling, audit trail assembly,
metrics) from any individual rule's behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import pytest

from lead_intelligence.application.cleaning.config import CleaningProfile, RuleOverride
from lead_intelligence.application.cleaning.pipeline import CleaningPipeline
from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.dto.models import (
    ImportedLeadDataset,
    RawRecord,
    SourceMetadata,
)
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)
from lead_intelligence.domain.exceptions import InvalidCleaningConfigurationError


class UppercaseRule(NormalizationRule):
    """A trivial Safe rule: uppercases field 'name' if not already."""

    def __init__(
        self, rule_id: str = "CLN-T01", stage: RuleStage = RuleStage.SAFE
    ) -> None:
        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name="Uppercase",
            category=RuleCategory.METADATA,
            stage=stage,
            fields=("name",),
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        value = values.get("name")
        if isinstance(value, str) and value != value.upper():
            return {"name": value.upper()}
        return {}


class AppendSuffixBusinessRule(NormalizationRule):
    """A Business rule that appends '!' to 'name' — used to prove Business
    rules see the Safe stage's output, and can be individually disabled."""

    def __init__(self, rule_id: str = "CLN-T02", default_enabled: bool = True) -> None:
        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name="AppendSuffix",
            category=RuleCategory.METADATA,
            stage=RuleStage.BUSINESS,
            fields=("name",),
            configurable=True,
            default_enabled=default_enabled,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        value = values.get("name")
        if isinstance(value, str):
            return {"name": value + "!"}
        return {}


class AlwaysWarnRule(QualityCheckRule):
    def __init__(self, rule_id: str = "CLN-T03") -> None:
        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name="AlwaysWarn",
            category=RuleCategory.METADATA,
            stage=RuleStage.WARNING,
            fields=("name",),
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        return [
            QualityWarningDraft(
                code="ALWAYS", message="always warns", field_names=("name",)
            )
        ]


class ExplodingRule(NormalizationRule):
    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-T04",
            name="Exploding",
            category=RuleCategory.METADATA,
            stage=RuleStage.SAFE,
            fields=("name",),
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        raise RuntimeError("boom")


class RequiresConfigRule(NormalizationRule):
    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-T05",
            name="RequiresConfig",
            category=RuleCategory.METADATA,
            stage=RuleStage.BUSINESS,
            fields=("name",),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def validate_config(self, profile: Any) -> None:
        if profile.is_enabled(self) and not profile.parameters_for(
            self._metadata.rule_id
        ).get("required"):
            raise InvalidCleaningConfigurationError("missing 'required' parameter")

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        return {}


def _dataset(name_value: str = "ada") -> ImportedLeadDataset:
    record = RawRecord(row_number=2, sheet_name="Sheet1", values={"Name": name_value})
    metadata = SourceMetadata(
        source_path="fake",
        source_type="fake",
        sheet_name="Sheet1",
        available_sheets=("Sheet1",),
        column_names=("Name",),
        row_count=1,
        imported_at=datetime.now(timezone.utc),
    )
    return ImportedLeadDataset(records=(record,), metadata=metadata, warnings=())


def _profile(**kwargs: Any) -> CleaningProfile:
    return CleaningProfile(name="test", field_mapping={"name": "Name"}, **kwargs)


def test_safe_stage_runs_unconditionally() -> None:
    pipeline = CleaningPipeline([UppercaseRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    assert result.cleaned_dataset.cleaned_records[0].cleaned_values["name"] == "ADA"


def test_business_stage_sees_safe_stages_output() -> None:
    pipeline = CleaningPipeline(
        [UppercaseRule(), AppendSuffixBusinessRule()], _profile()
    )
    result = pipeline.run(_dataset("ada"))
    assert result.cleaned_dataset.cleaned_records[0].cleaned_values["name"] == "ADA!"


def test_business_master_switch_skips_all_business_rules() -> None:
    pipeline = CleaningPipeline(
        [UppercaseRule(), AppendSuffixBusinessRule()],
        _profile(enable_business_normalization=False),
    )
    result = pipeline.run(_dataset("ada"))
    assert result.cleaned_dataset.cleaned_records[0].cleaned_values["name"] == "ADA"
    assert result.metrics.per_rule["CLN-T02"].records_skipped == 1
    assert result.metrics.per_rule["CLN-T02"].records_evaluated == 0


def test_individually_disabled_business_rule_is_skipped() -> None:
    rule = AppendSuffixBusinessRule(default_enabled=False)
    pipeline = CleaningPipeline([UppercaseRule(), rule], _profile())
    result = pipeline.run(_dataset("ada"))
    assert result.cleaned_dataset.cleaned_records[0].cleaned_values["name"] == "ADA"


def test_warning_stage_runs_even_when_business_stage_disabled() -> None:
    pipeline = CleaningPipeline(
        [AlwaysWarnRule()], _profile(enable_business_normalization=False)
    )
    result = pipeline.run(_dataset("ada"))
    assert len(result.cleaned_dataset.cleaned_records[0].warnings) == 1


def test_warning_stage_never_modifies_values() -> None:
    pipeline = CleaningPipeline([UppercaseRule(), AlwaysWarnRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    record = result.cleaned_dataset.cleaned_records[0]
    assert record.cleaned_values["name"] == "ADA"
    assert len(record.warnings) == 1


def test_field_change_carries_rule_id_and_version() -> None:
    pipeline = CleaningPipeline([UppercaseRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    change = result.cleaned_dataset.cleaned_records[0].field_changes[0]
    assert change.rule_id == "CLN-T01"
    assert change.rule_version == 1
    assert change.old_value == "ada"
    assert change.new_value == "ADA"


def test_a_rule_exception_is_caught_and_does_not_abort_the_batch() -> None:
    pipeline = CleaningPipeline([ExplodingRule(), UppercaseRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    record = result.cleaned_dataset.cleaned_records[0]
    assert len(record.execution_failures) == 1
    assert record.execution_failures[0].rule_id == "CLN-T04"
    # the next rule still ran despite the failure
    assert record.cleaned_values["name"] == "ADA"
    assert result.metrics.failures == 1


def test_invalid_configuration_fails_before_any_record_is_processed() -> None:
    profile = _profile(rule_overrides={"CLN-T05": RuleOverride(enabled=True)})
    pipeline = CleaningPipeline([RequiresConfigRule()], profile)
    with pytest.raises(InvalidCleaningConfigurationError):
        pipeline.run(_dataset("ada"))


def test_valid_configuration_does_not_raise() -> None:
    profile = _profile(
        rule_overrides={
            "CLN-T05": RuleOverride(enabled=True, parameters={"required": True})
        }
    )
    pipeline = CleaningPipeline([RequiresConfigRule()], profile)
    pipeline.run(_dataset("ada"))  # should not raise


def test_audit_trail_contains_field_changes_and_warnings() -> None:
    pipeline = CleaningPipeline([UppercaseRule(), AlwaysWarnRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    codes = {type(entry).__name__ for entry in result.audit_trail}
    assert codes == {"FieldChange", "QualityWarning"}


def test_metrics_and_report_reflect_the_run() -> None:
    pipeline = CleaningPipeline([UppercaseRule(), AlwaysWarnRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    assert result.metrics.records_processed == 1
    assert result.metrics.fields_modified == 1
    assert result.metrics.warnings_generated == 1
    assert result.report.records_with_changes == 1
    assert result.report.records_with_warnings == 1
    assert result.report.duration_ms >= 0


def test_raw_record_is_retained_unmodified() -> None:
    pipeline = CleaningPipeline([UppercaseRule()], _profile())
    result = pipeline.run(_dataset("ada"))
    record = result.cleaned_dataset.cleaned_records[0]
    assert record.raw_record.values["Name"] == "ada"
