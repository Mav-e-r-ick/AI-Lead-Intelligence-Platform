"""Plain data shapes produced by the Executive Comparison Engine.

WHY THIS FILE EXISTS (SEPARATE FROM cleaning/identity_resolution/enrichment_models.py):
Same reasoning as those files' own docstrings: each pipeline stage gets one
cohesive vocabulary file, so none of them grows into an unrelated grab-bag
as more stages are added.

Every dataclass here is immutable (frozen, tuple fields) for the same
reason as every other stage's DTOs: once the engine hands back a
comparison, no downstream code should be able to silently mutate the
evidence behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ComparisonStatus(str, Enum):
    """The one-of-six verdict for a single field comparison.

    MATCH: both sources have a value, and they're considered equivalent
        (exact or fuzzy-similar at or above the configured threshold).
    CHANGED: both sources have a single value, and they differ.
    MISSING: the existing record has a value; no corresponding new
        observation was found (something we knew is absent from the new
        source — not necessarily wrong, just unconfirmed).
    NEW: the existing record has no value; the new source provides one.
    CONFLICT: the new observations themselves disagree — two or more
        distinct values were found for the same field, so no single "new
        value" can be confidently reported. Independent of whether the
        existing record has a value.
    UNKNOWN: neither source has a value for this field. Nothing to compare.
    """

    MATCH = "match"
    CHANGED = "changed"
    MISSING = "missing"
    NEW = "new"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class ComparisonStrategy(str, Enum):
    """How two present values are judged equivalent."""

    EXACT = "exact"
    FUZZY = "fuzzy"


@dataclass(frozen=True)
class FieldComparison:
    """The result of comparing one field between the existing record and
    newly collected observations.

    Attributes:
        field_name: The canonical comparable field (e.g. "name", "title",
            "company", "email", "phone").
        existing_value: The value resolved from the existing record, or
            None if absent.
        new_value: The single resolved new value, or None if absent,
            ambiguous (CONFLICT), or there was nothing to compare
            (UNKNOWN).
        status: One of the six ComparisonStatus verdicts.
        strategy: Which comparison strategy this field uses (informational
            — always the field's configured strategy, regardless of
            status).
        similarity_score: In [0.0, 1.0], populated only when both values
            were directly compared (MATCH/CHANGED) — 1.0/0.0 for EXACT,
            the real similarity ratio for FUZZY. None otherwise.
        conflicting_values: Every distinct new value found, populated only
            when status is CONFLICT.
        explanation: A short, human-readable reason for the verdict —
            every comparison decision must be explainable, not a bare
            enum value.
    """

    field_name: str
    existing_value: str | None
    new_value: str | None
    status: ComparisonStatus
    strategy: ComparisonStrategy
    similarity_score: float | None
    conflicting_values: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class ComparisonSummary:
    """The aggregate digest of one ComparisonResult.

    Attributes:
        fields_matched: Count of MATCH.
        fields_changed: Count of CHANGED.
        fields_missing: Count of MISSING.
        fields_new: Count of NEW.
        fields_conflict: Count of CONFLICT.
        fields_unknown: Count of UNKNOWN.
        confidence: In [0.0, 1.0] — the fraction of fields that were
            comparable at all (i.e. excluding UNKNOWN) that produced a
            clear, unambiguous verdict (MATCH/CHANGED/MISSING/NEW, not
            CONFLICT). 0.0 if every field was UNKNOWN (nothing was ever
            comparable, so there is nothing to be confident about).
        compared_at: UTC timestamp this comparison was performed.
    """

    fields_matched: int
    fields_changed: int
    fields_missing: int
    fields_new: int
    fields_conflict: int
    fields_unknown: int
    confidence: float
    compared_at: datetime

    @property
    def total_fields(self) -> int:
        """Total number of fields compared, across every status."""

        return (
            self.fields_matched
            + self.fields_changed
            + self.fields_missing
            + self.fields_new
            + self.fields_conflict
            + self.fields_unknown
        )


@dataclass(frozen=True)
class ComparisonResult:
    """The Executive Comparison Engine's single output type for one record.

    Attributes:
        record_reference: An opaque, traceable reference to the existing
            record being compared (e.g. "row:42"), for logging/audit.
        field_comparisons: One FieldComparison per configured comparable
            field, in profile-configured order.
        summary: The aggregate digest built from `field_comparisons`.
    """

    record_reference: str
    field_comparisons: tuple[FieldComparison, ...]
    summary: ComparisonSummary
