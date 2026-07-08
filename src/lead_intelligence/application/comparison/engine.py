"""ComparisonEngine: the Executive Comparison Engine's single orchestration
point.

Given one existing (cleaned) executive record and a set of newly collected
ObservationCandidates, produces one ComparisonResult: a FieldComparison
per configured field, plus a summary. This engine only *identifies*
differences — it never decides what a difference means (no promotion/
resignation/inflection classification, no AI, no verification). That
interpretation is explicitly future work.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Sequence

from loguru import logger

from lead_intelligence.application.comparison.comparators import (
    normalize_text,
    normalizer_for,
    similarity,
)
from lead_intelligence.application.comparison.config import (
    ComparisonFieldRule,
    ComparisonProfile,
)
from lead_intelligence.application.comparison.resolvers import EXISTING_VALUE_RESOLVERS
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
    ComparisonStrategy,
    ComparisonSummary,
    FieldComparison,
)
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate


class ComparisonEngine:
    """Compares one existing executive record against newly collected
    ObservationCandidates, field by field."""

    def __init__(
        self,
        profile: ComparisonProfile,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure an engine bound to one profile.

        Args:
            profile: The active ComparisonProfile.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._profile = profile
        self._clock = clock

    def compare(
        self,
        existing_record: CleanedLeadRecord,
        observations: Sequence[ObservationCandidate],
        record_reference: str,
    ) -> ComparisonResult:
        """Compare `existing_record` against `observations` and return one
        ComparisonResult.

        Raises:
            InvalidComparisonConfigurationError: If the profile itself is
                invalid — raised before any field is compared.
        """

        self._profile.validate()

        logger.info(
            "Comparison starting: profile='{}', record_reference={}, "
            "{} observation(s)",
            self._profile.name,
            record_reference,
            len(observations),
        )

        field_comparisons = tuple(
            self._compare_field(rule, existing_record, observations)
            for rule in self._profile.field_rules
        )

        summary = self._build_summary(field_comparisons)
        logger.info(
            "Comparison complete: record_reference={}, matched={}, changed={}, "
            "missing={}, new={}, conflict={}, unknown={}, confidence={:.3f}",
            record_reference,
            summary.fields_matched,
            summary.fields_changed,
            summary.fields_missing,
            summary.fields_new,
            summary.fields_conflict,
            summary.fields_unknown,
            summary.confidence,
        )

        return ComparisonResult(
            record_reference=record_reference,
            field_comparisons=field_comparisons,
            summary=summary,
        )

    def _compare_field(
        self,
        rule: ComparisonFieldRule,
        existing_record: CleanedLeadRecord,
        observations: Sequence[ObservationCandidate],
    ) -> FieldComparison:
        resolver = EXISTING_VALUE_RESOLVERS[rule.field_name]
        existing_value = resolver(existing_record.cleaned_values)
        new_values = self._distinct_new_values(rule, observations)

        if existing_value is None and not new_values:
            return self._result(
                rule,
                existing_value,
                None,
                ComparisonStatus.UNKNOWN,
                None,
                (),
                "No data available from either the existing record or new observations.",
            )

        if len(new_values) > 1:
            return self._result(
                rule,
                existing_value,
                None,
                ComparisonStatus.CONFLICT,
                None,
                tuple(new_values),
                f"{len(new_values)} differing new value(s) found for this field: "
                f"{', '.join(new_values)}.",
            )

        new_value = new_values[0] if new_values else None

        if existing_value is not None and new_value is None:
            return self._result(
                rule,
                existing_value,
                None,
                ComparisonStatus.MISSING,
                None,
                (),
                "Existing value present; no corresponding new observation was found.",
            )

        if existing_value is None and new_value is not None:
            return self._result(
                rule,
                None,
                new_value,
                ComparisonStatus.NEW,
                None,
                (),
                "No existing value; a new observation provides one.",
            )

        # Both present, exactly one distinct new value: the only branch
        # where a mypy-visible non-None `existing_value`/`new_value` pair
        # is actually compared.
        assert existing_value is not None and new_value is not None
        if rule.strategy is ComparisonStrategy.EXACT:
            normalize = normalizer_for(rule.field_name)
            is_match = normalize(existing_value) == normalize(new_value)
            score = 1.0 if is_match else 0.0
        else:
            score = similarity(existing_value, new_value)
            is_match = score >= rule.fuzzy_threshold

        status = ComparisonStatus.MATCH if is_match else ComparisonStatus.CHANGED
        explanation = (
            f"{rule.strategy.value} comparison: "
            f"{'equivalent' if is_match else 'differs'} (score={score:.3f})."
        )
        return self._result(
            rule, existing_value, new_value, status, score, (), explanation
        )

    def _distinct_new_values(
        self, rule: ComparisonFieldRule, observations: Sequence[ObservationCandidate]
    ) -> list[str]:
        """Every distinct new value found for `rule`'s field, deduplicated
        by normalized form (so trivial casing/whitespace differences
        across observations don't manufacture a false CONFLICT), and
        returned in a deterministic (alphabetical) order.
        """

        normalize = (
            normalizer_for(rule.field_name)
            if rule.strategy is ComparisonStrategy.EXACT
            else normalize_text
        )

        groups: dict[str, list[str]] = {}
        for observation in observations:
            if observation.attribute not in rule.observation_attributes:
                continue
            raw = observation.value.strip()
            if not raw:
                continue
            key = normalize(raw)
            groups.setdefault(key, []).append(raw)

        representatives = [sorted(candidates)[0] for candidates in groups.values()]
        return sorted(representatives)

    def _result(
        self,
        rule: ComparisonFieldRule,
        existing_value: str | None,
        new_value: str | None,
        status: ComparisonStatus,
        similarity_score: float | None,
        conflicting_values: tuple[str, ...],
        explanation: str,
    ) -> FieldComparison:
        return FieldComparison(
            field_name=rule.field_name,
            existing_value=existing_value,
            new_value=new_value,
            status=status,
            strategy=rule.strategy,
            similarity_score=similarity_score,
            conflicting_values=conflicting_values,
            explanation=explanation,
        )

    def _build_summary(
        self, field_comparisons: tuple[FieldComparison, ...]
    ) -> ComparisonSummary:
        counts = {status: 0 for status in ComparisonStatus}
        for comparison in field_comparisons:
            counts[comparison.status] += 1

        clean_verdicts = (
            counts[ComparisonStatus.MATCH]
            + counts[ComparisonStatus.CHANGED]
            + counts[ComparisonStatus.MISSING]
            + counts[ComparisonStatus.NEW]
        )
        comparable_fields = len(field_comparisons) - counts[ComparisonStatus.UNKNOWN]
        confidence = (
            clean_verdicts / comparable_fields if comparable_fields > 0 else 0.0
        )

        return ComparisonSummary(
            fields_matched=counts[ComparisonStatus.MATCH],
            fields_changed=counts[ComparisonStatus.CHANGED],
            fields_missing=counts[ComparisonStatus.MISSING],
            fields_new=counts[ComparisonStatus.NEW],
            fields_conflict=counts[ComparisonStatus.CONFLICT],
            fields_unknown=counts[ComparisonStatus.UNKNOWN],
            confidence=confidence,
            compared_at=self._clock(),
        )
