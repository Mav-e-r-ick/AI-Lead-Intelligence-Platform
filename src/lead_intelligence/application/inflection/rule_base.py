"""The contract every inflection detection rule must implement, plus the
small shared pieces every rule uses.

WHY DRAFTS, NOT FULLY-STAMPED Inflections (mirrors QualityWarningDraft in
the Cleaning Engine):
A rule only knows *that* its pattern is present and *why* — it does not
know its own rule_id (that's registry-level identity) or the timestamp
(that's when the engine ran, not when the rule happened to execute). This
split makes it structurally impossible for a rule to fabricate metadata
about itself or another rule; InflectionDetectionEngine is the only place
that stamps a draft into a full Inflection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    FieldComparison,
)
from lead_intelligence.application.dto.inflection_models import InflectionType


@dataclass(frozen=True)
class InflectionRuleMetadata:
    """Static facts about one rule.

    Attributes:
        rule_id: Permanent rule id, e.g. "INF-001" (mirrors CLN-### in the
            Cleaning Engine).
        inflection_type: Which InflectionType this rule detects.
        name: Human-readable rule name.
        base_confidence: This rule's default confidence in [0.0, 1.0],
            before the engine discounts it by the originating
            ComparisonResult's own summary confidence. Overridable per
            profile — see config.py.
        description: A short explanation of what pattern this rule looks for.
    """

    rule_id: str
    inflection_type: InflectionType
    name: str
    base_confidence: float
    description: str


@dataclass(frozen=True)
class InflectionDraft:
    """An unstamped candidate, as returned directly by an InflectionRule.

    Attributes:
        supporting_comparisons: Every FieldComparison this decision was
            based on.
        explanation: A short, human-readable reason.
    """

    supporting_comparisons: tuple[FieldComparison, ...]
    explanation: str


class InflectionRule(ABC):
    """One deterministic pattern over a ComparisonResult's FieldComparisons."""

    @property
    @abstractmethod
    def metadata(self) -> InflectionRuleMetadata:
        """This rule's static registry metadata."""

    @abstractmethod
    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        """Return a draft if this rule's pattern is present in
        `comparison_result`, else None.

        Must never raise for an ordinary "pattern not present" outcome —
        return None instead, so the engine's per-rule fail-safe handling
        (see engine.py) is reserved for genuinely unexpected bugs.
        """


def get_field_comparison(
    comparison_result: ComparisonResult, field_name: str
) -> FieldComparison | None:
    """The FieldComparison named `field_name` in `comparison_result`, or
    None if that field wasn't part of this comparison run (e.g. a custom
    ComparisonProfile that omitted it).
    """

    return next(
        (
            comparison
            for comparison in comparison_result.field_comparisons
            if comparison.field_name == field_name
        ),
        None,
    )
