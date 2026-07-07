"""Generic, parameterized rule base classes shared across many CLN-### rules.

WHY THIS FILE EXISTS:
Roughly half of CLEANING_RULES.md's 68 rules share one of a handful of
underlying shapes ("trim whitespace for field group X," "warn if field Y is
missing," "warn if two fields are identical," ...). Rather than writing 30+
near-duplicate classes, each shape is implemented once here and
*instantiated* per rule in rules/identity.py, rules/contact.py, etc., with
that rule's own id/fields/parameters. This is what keeps CleaningPipeline's
Open/Closed guarantee cheap in practice: most new rules need zero new code,
just a new instantiation of something already here.

Every class below still carries its own RuleMetadata per instance, so each
instantiation is a fully independent, individually testable, individually
toggleable rule in the registry — sharing implementation never means
sharing identity.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleMetadata,
)

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE_PATTERN = re.compile(r"[ \t]+")


def _is_present(value: Any) -> bool:
    """True if value is neither None nor an empty/whitespace-only string."""

    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


#: Public alias — used by category rule modules for their own bespoke
#: presence checks (e.g. address.py's Incomplete Address Component Warning).
is_field_present = _is_present


def normalize_text(value: str) -> str:
    """The shared, lossless text-hygiene routine every whitespace rule uses.

    Unicode NFC normalization, then collapse internal whitespace runs,
    strip control characters, then trim ends. Order matters: control-char
    stripping must precede final trim so a control char at the very edge
    doesn't leave stray surrounding whitespace behind.
    """

    normalized = unicodedata.normalize("NFC", value)
    normalized = _CONTROL_CHAR_PATTERN.sub("", normalized)
    normalized = _MULTI_SPACE_PATTERN.sub(" ", normalized)
    return normalized.strip()


class WhitespaceNormalizationRule(NormalizationRule):
    """Trim/collapse whitespace, Unicode-normalize, strip control chars.

    Optionally strips a known source-format artifact first (e.g. Excel's
    force-text leading apostrophe on phone numbers) via `artifact_pattern`.
    Always Safe/Lossless — never configurable, always enabled.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        *,
        version: int = 1,
        artifact_pattern: re.Pattern[str] | None = None,
        remove_internal_whitespace: bool = False,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.SAFE,
            fields=fields,
            version=version,
            configurable=False,
            default_enabled=True,
        )
        self._artifact_pattern = artifact_pattern
        self._remove_internal_whitespace = remove_internal_whitespace

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            raw_value = values.get(field_name)
            if not isinstance(raw_value, str):
                continue
            working = unicodedata.normalize("NFC", raw_value)
            if self._artifact_pattern is not None:
                working = self._artifact_pattern.sub("", working)
            if self._remove_internal_whitespace:
                working = re.sub(r"\s+", "", working)
            else:
                working = normalize_text(working)
            if working != raw_value:
                changes[field_name] = working
        return changes


class WhitespaceOnlyTrimRule(NormalizationRule):
    """Trim leading/trailing whitespace only — never touches internal
    characters. For identifier fields where internal content (including
    leading zeros) must never be altered.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.SAFE,
            fields=fields,
            version=version,
            configurable=False,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            raw_value = values.get(field_name)
            if isinstance(raw_value, str):
                trimmed = raw_value.strip()
                if trimmed != raw_value:
                    changes[field_name] = trimmed
        return changes


class MissingValueRepresentationRule(NormalizationRule):
    """Canonicalize recognized "absent" sentinels to None.

    Never touches a present value — only standardizes how "nothing here" is
    represented, regardless of whether the source used an empty string or a
    sentinel like "N/A".
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        *,
        version: int = 1,
        sentinels: frozenset[str] = frozenset({""}),
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.SAFE,
            fields=fields,
            version=version,
            configurable=False,
            default_enabled=True,
        )
        self._sentinels = {s.lower() for s in sentinels}

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            raw_value = values.get(field_name)
            if (
                isinstance(raw_value, str)
                and raw_value.strip().lower() in self._sentinels
            ):
                changes[field_name] = None
        return changes


class PassthroughRule(NormalizationRule):
    """A formal no-op — documents that a field is deliberately never cleaned.

    Exists so the guarantee ("this field is never touched") is a real,
    testable registry entry rather than an informal assumption.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.SAFE,
            fields=fields,
            version=version,
            configurable=False,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        return {}


class BooleanRepresentationNormalizationRule(NormalizationRule):
    """Map configured source string representations to native booleans.

    Native bool/None values pass through unchanged. An unmapped string is
    left unchanged (never guessed).
    """

    _DEFAULT_MAPPING: dict[str, bool] = {
        "y": True,
        "yes": True,
        "true": True,
        "1": True,
        "n": False,
        "no": False,
        "false": False,
        "0": False,
    }

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        *,
        version: int = 1,
        default_enabled: bool = True,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.BUSINESS,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=default_enabled,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        mapping: dict[str, bool] = {
            **self._DEFAULT_MAPPING,
            **params.get("mapping", {}),
        }
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            raw_value = values.get(field_name)
            if isinstance(raw_value, str):
                mapped = mapping.get(raw_value.strip().lower())
                if mapped is not None:
                    changes[field_name] = mapped
        return changes


class PrimarySelectionRule(NormalizationRule):
    """Derive a new attribute pointing at the first populated field in a
    configured priority order. Purely additive — never modifies or removes
    any source field.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        candidate_fields: tuple[str, ...],
        derived_field: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.BUSINESS,
            fields=candidate_fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._derived_field = derived_field

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        priority = tuple(params.get("priority", self._metadata.fields))
        for field_name in priority:
            candidate = values.get(field_name)
            if _is_present(candidate):
                if values.get(self._derived_field) != candidate:
                    return {self._derived_field: candidate}
                return {}
        if values.get(self._derived_field) is not None:
            return {self._derived_field: None}
        return {}


# --------------------------------------------------------------------------
# Warning-stage generics
# --------------------------------------------------------------------------


class MissingFieldWarningRuleSet(QualityCheckRule):
    """Independently checks several fields, warning once per field that's
    absent. Each field has its own warning code (e.g. MISSING_FIRST_NAME,
    MISSING_LAST_NAME under one CLN rule for the Identity category).
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        checks: tuple[tuple[str, str, str], ...],
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        fields = tuple(field_name for field_name, _, _ in checks)
        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._checks = checks

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        warnings: list[QualityWarningDraft] = []
        for field_name, code, message in self._checks:
            if not _is_present(values.get(field_name)):
                warnings.append(
                    QualityWarningDraft(
                        code=code, message=message, field_names=(field_name,)
                    )
                )
        return warnings


class AllFieldsAbsentWarningRule(QualityCheckRule):
    """Warns once if every field in a list is absent simultaneously."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        code: str,
        message: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._code = code
        self._message = message

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        if all(not _is_present(values.get(f)) for f in self._metadata.fields):
            return [
                QualityWarningDraft(
                    code=self._code,
                    message=self._message,
                    field_names=self._metadata.fields,
                )
            ]
        return []


class FieldPresentWarningRule(QualityCheckRule):
    """Warns whenever a field is present — for standing disclaimers (e.g.
    CLN-062's Dedup ID reliability notice), not an error condition.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        field_name: str,
        code: str,
        message: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=(field_name,),
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._code = code
        self._message = message

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        if _is_present(values.get(self._metadata.fields[0])):
            return [
                QualityWarningDraft(
                    code=self._code,
                    message=self._message,
                    field_names=self._metadata.fields,
                )
            ]
        return []


class IdenticalFieldsWarningRule(QualityCheckRule):
    """Warns if the concatenation of `left_fields` equals `right_field`
    (case-insensitive, whitespace-normalized). left_fields=(a,) covers a
    simple a==b check; left_fields=(a, b) covers "a b" == c.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        left_fields: tuple[str, ...],
        right_field: str,
        code: str,
        message: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=left_fields + (right_field,),
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._left_fields = left_fields
        self._right_field = right_field
        self._code = code
        self._message = message

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        left_parts = [values.get(f) for f in self._left_fields]
        if any(part is None for part in left_parts):
            return []
        right = values.get(self._right_field)
        if right is None:
            return []
        left_joined = " ".join(str(part).strip() for part in left_parts).strip().lower()
        if left_joined and left_joined == str(right).strip().lower():
            return [
                QualityWarningDraft(
                    code=self._code,
                    message=self._message,
                    field_names=self._metadata.fields,
                )
            ]
        return []


class ThresholdWarningRule(QualityCheckRule):
    """Warns if len(str(value)) is above (comparator="gt") or below
    (comparator="lt") a configurable threshold.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        field_name: str,
        default_threshold: int,
        comparator: str,
        code: str,
        message_template: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=(field_name,),
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._default_threshold = default_threshold
        self._comparator = comparator
        self._code = code
        self._message_template = message_template

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        field_name = self._metadata.fields[0]
        value = values.get(field_name)
        if not isinstance(value, str) or not value:
            return []
        params = profile.parameters_for(self._metadata.rule_id)
        threshold = int(params.get("threshold", self._default_threshold))
        length = len(value)
        triggered = (
            length > threshold if self._comparator == "gt" else length < threshold
        )
        if triggered:
            message = self._message_template.format(length=length, threshold=threshold)
            return [
                QualityWarningDraft(
                    code=self._code, message=message, field_names=(field_name,)
                )
            ]
        return []


class DigitCountWarningRule(QualityCheckRule):
    """Warns if a value has fewer than a configurable minimum digit count."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        default_min_digits: int,
        code: str,
        message_template: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._default_min_digits = default_min_digits
        self._code = code
        self._message_template = message_template

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        params = profile.parameters_for(self._metadata.rule_id)
        min_digits = int(params.get("min_digits", self._default_min_digits))
        warnings: list[QualityWarningDraft] = []
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if not isinstance(value, str) or not value:
                continue
            digit_count = sum(character.isdigit() for character in value)
            if digit_count < min_digits:
                message = self._message_template.format(
                    digit_count=digit_count, min_digits=min_digits
                )
                warnings.append(
                    QualityWarningDraft(
                        code=self._code, message=message, field_names=(field_name,)
                    )
                )
        return warnings


class RegexShapeWarningRule(QualityCheckRule):
    """Warns, per field, if its value matches (invert=False) or does not
    match (invert=True) a compiled regex pattern. Independently checks
    every field in `fields`.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        pattern: re.Pattern[str],
        invert: bool,
        code: str,
        message: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._pattern = pattern
        self._invert = invert
        self._code = code
        self._message = message

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        warnings: list[QualityWarningDraft] = []
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if not isinstance(value, str) or not value:
                continue
            matched = self._pattern.search(value) is not None
            triggered = (not matched) if self._invert else matched
            if triggered:
                warnings.append(
                    QualityWarningDraft(
                        code=self._code,
                        message=self._message,
                        field_names=(field_name,),
                    )
                )
        return warnings


class NegativeValueWarningRule(QualityCheckRule):
    """Warns if a numeric field is negative — only for the configured field
    list, which is deliberately per-field, not blanket (see CLN-048: some
    financial fields, like Pre Tax Profit, legitimately go negative).
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        fields: tuple[str, ...],
        code: str,
        message_template: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._code = code
        self._message_template = message_template

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        warnings: list[QualityWarningDraft] = []
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, (int, float)) and value < 0:
                message = self._message_template.format(field=field_name, value=value)
                warnings.append(
                    QualityWarningDraft(
                        code=self._code, message=message, field_names=(field_name,)
                    )
                )
        return warnings


class CrossFieldGreaterThanWarningRule(QualityCheckRule):
    """Warns if field_a's value is greater than field_b's value."""

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        field_a: str,
        field_b: str,
        code: str,
        message: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=(field_a, field_b),
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._field_a = field_a
        self._field_b = field_b
        self._code = code
        self._message = message

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        a = values.get(self._field_a)
        b = values.get(self._field_b)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > b:
            return [
                QualityWarningDraft(
                    code=self._code,
                    message=self._message,
                    field_names=self._metadata.fields,
                )
            ]
        return []


class PresenceConsistencyWarningRule(QualityCheckRule):
    """Warns if a trigger-field condition holds but a required-field
    condition doesn't. Both conditions use "any populated" or "all
    populated" quantifiers over their own field list.

    Covers "field X present without field Y" style checks generically:
    CLN-050 (financial data without Sales), CLN-055 (classification code
    without industry label), CLN-068 (Sales without any industry field).
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        trigger_fields: tuple[str, ...],
        trigger_mode: str,
        required_fields: tuple[str, ...],
        required_mode: str,
        code: str,
        message: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=trigger_fields + required_fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._trigger_fields = trigger_fields
        self._trigger_mode = trigger_mode
        self._required_fields = required_fields
        self._required_mode = required_mode
        self._code = code
        self._message = message

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    @staticmethod
    def _quantify(mode: str, flags: list[bool]) -> bool:
        return all(flags) if mode == "all" else any(flags)

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        trigger_flags = [_is_present(values.get(f)) for f in self._trigger_fields]
        if not self._quantify(self._trigger_mode, trigger_flags):
            return []
        required_flags = [_is_present(values.get(f)) for f in self._required_fields]
        if self._quantify(self._required_mode, required_flags):
            return []
        return [
            QualityWarningDraft(
                code=self._code,
                message=self._message,
                field_names=self._metadata.fields,
            )
        ]


class PairedFieldsConsistencyWarningRule(QualityCheckRule):
    """Warns once per pair, for each (field_a, field_b) pair where exactly
    one of the two is populated. Used for CLN-053's code/description pairs.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        pairs: tuple[tuple[str, str], ...],
        code: str,
        message_template: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        fields = tuple(f for pair in pairs for f in pair)
        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=fields,
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._pairs = pairs
        self._code = code
        self._message_template = message_template

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        warnings: list[QualityWarningDraft] = []
        for field_a, field_b in self._pairs:
            present_a = _is_present(values.get(field_a))
            present_b = _is_present(values.get(field_b))
            if present_a != present_b:
                message = self._message_template.format(
                    field_a=field_a, field_b=field_b
                )
                warnings.append(
                    QualityWarningDraft(
                        code=self._code, message=message, field_names=(field_a, field_b)
                    )
                )
        return warnings


class ReferenceTableMembershipWarningRule(QualityCheckRule):
    """Warns if a populated field's value is absent from its bundled
    reference table. A field with no configured table is skipped, never
    guessed at (mirrors CLN-042's "skip silently" policy).
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        field_to_table: Mapping[str, frozenset[str]],
        code: str,
        message_template: str,
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.WARNING,
            fields=tuple(field_to_table.keys()),
            version=version,
            configurable=True,
            default_enabled=True,
        )
        self._field_to_table = field_to_table
        self._code = code
        self._message_template = message_template

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        warnings: list[QualityWarningDraft] = []
        for field_name, table in self._field_to_table.items():
            value = values.get(field_name)
            if isinstance(value, str) and value and value not in table:
                message = self._message_template.format(field=field_name, value=value)
                warnings.append(
                    QualityWarningDraft(
                        code=self._code, message=message, field_names=(field_name,)
                    )
                )
        return warnings


class ReferenceTableStandardizationRule(NormalizationRule):
    """Maps a field's value to a target format ("abbreviation" or
    "full_name") via two lookup tables. Used for CLN-037 (state/province)
    and CLN-038 (country) — a genuine convention choice, so off by default.
    An unmapped value is left unchanged (never guessed).
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        category: Any,
        field_name: str,
        name_to_code: Mapping[str, str],
        code_to_name: Mapping[str, str],
        *,
        version: int = 1,
    ) -> None:
        from lead_intelligence.application.ports.cleaning_rule_port import RuleStage

        self._metadata = RuleMetadata(
            rule_id=rule_id,
            name=name,
            category=category,
            stage=RuleStage.BUSINESS,
            fields=(field_name,),
            version=version,
            configurable=True,
            default_enabled=False,
        )
        self._field_name = field_name
        self._name_to_code = name_to_code
        self._code_to_name = code_to_name

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        target = params.get("target", "abbreviation")
        value = values.get(self._field_name)
        if not isinstance(value, str) or not value.strip():
            return {}
        if target == "abbreviation":
            mapped = self._name_to_code.get(value.strip().lower())
        else:
            mapped = self._code_to_name.get(value.strip().upper())
        if mapped and mapped != value:
            return {self._field_name: mapped}
        return {}
