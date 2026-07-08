"""Plain data shapes produced by the Inflection Detection Engine.

WHY THIS FILE EXISTS (SEPARATE FROM comparison_models.py etc.):
Same reasoning as every other stage's own DTO file's docstring: each
pipeline stage gets one cohesive vocabulary file, so none of them grows
into an unrelated grab-bag as more stages are added.

Every dataclass here is immutable (frozen, tuple fields) for the same
reason as every other stage's DTOs: once the engine hands back a report,
no downstream code should be able to silently mutate the evidence behind
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from lead_intelligence.application.dto.comparison_models import FieldComparison


class InflectionType(str, Enum):
    """The seven Version 1 business events this engine can detect.

    Each is a deterministic, explainable pattern over a ComparisonResult's
    FieldComparisons — never an AI judgment, never a guess.
    """

    PROMOTION = "promotion"
    DEMOTION = "demotion"
    COMPANY_CHANGE = "company_change"
    POSSIBLE_RESIGNATION = "possible_resignation"
    CONTACT_INFO_CHANGED = "contact_info_changed"
    EXECUTIVE_NEWLY_APPEARED = "executive_newly_appeared"
    EXECUTIVE_NO_LONGER_FOUND = "executive_no_longer_found"


@dataclass(frozen=True)
class Inflection:
    """One detected business event.

    Attributes:
        type: Which of the seven InflectionType events this is.
        confidence: In [0.0, 1.0] — see engine.py for the deterministic
            formula (the rule's configured base confidence, discounted by
            the originating ComparisonResult's own summary confidence).
        supporting_comparisons: Every FieldComparison this inflection's
            rule based its decision on — the evidence, not just the verdict.
        explanation: A short, human-readable reason for this inflection —
            every detection must be explainable, not a bare enum value.
        detected_at: UTC timestamp this inflection was detected.
        rule_id: The permanent rule id (e.g. "INF-001") that detected this
            inflection, for traceability — mirrors CLN-### in the Cleaning
            Engine.
    """

    type: InflectionType
    confidence: float
    supporting_comparisons: tuple[FieldComparison, ...]
    explanation: str
    detected_at: datetime
    rule_id: str


@dataclass(frozen=True)
class InflectionReport:
    """The Inflection Detection Engine's single output type for one record.

    Attributes:
        record_reference: The same opaque, traceable reference carried
            from the originating ComparisonResult (e.g. "row:42").
        inflections: Every detected Inflection, in rule-registry order.
            Empty means no business event was detected — a legitimate,
            common outcome, not an error.
        generated_at: UTC timestamp this report was generated.
    """

    record_reference: str
    inflections: tuple[Inflection, ...]
    generated_at: datetime

    @property
    def inflection_count(self) -> int:
        """Number of detected inflections."""

        return len(self.inflections)

    @property
    def detected_types(self) -> frozenset[InflectionType]:
        """The distinct InflectionTypes present in this report."""

        return frozenset(inflection.type for inflection in self.inflections)
