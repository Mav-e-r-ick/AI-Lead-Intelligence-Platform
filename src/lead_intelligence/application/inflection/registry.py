"""InflectionRuleRegistry: the set of detection rules known to one
InflectionDetectionEngine, built once via dependency injection.

WHY THIS IS SEPARATE FROM InflectionProfile:
Mirrors ProviderRegistry / EnrichmentProfile's split in the Enrichment
Provider Framework: the registry answers "which rule *objects* exist"
(a structural, code-level question); the profile answers "which of them
are *enabled*, at what confidence" (a per-run, configuration-level
question). The same registry can be reused across many differently
configured runs without rebuilding rule instances each time.
"""

from __future__ import annotations

from typing import Sequence

from lead_intelligence.application.inflection.rule_base import InflectionRule
from lead_intelligence.domain.exceptions import DuplicateInflectionRuleError


class InflectionRuleRegistry:
    """A lookup of every registered InflectionRule, keyed by its `rule_id`."""

    def __init__(self, rules: Sequence[InflectionRule]) -> None:
        """Register every rule in `rules`.

        Args:
            rules: Every rule this registry should know about (dependency
                injection — typically `rules.ALL_RULES`, but any subset is
                valid).

        Raises:
            DuplicateInflectionRuleError: If two rules report the same
                `rule_id`.
        """

        by_id: dict[str, InflectionRule] = {}
        for rule in rules:
            rule_id = rule.metadata.rule_id
            if rule_id in by_id:
                raise DuplicateInflectionRuleError(
                    f"Rule id '{rule_id}' is registered more than once; rule ids "
                    "must be unique."
                )
            by_id[rule_id] = rule
        self._rules = by_id

    def get(self, rule_id: str) -> InflectionRule | None:
        """The rule registered under `rule_id`, or None if there isn't one."""

        return self._rules.get(rule_id)

    def all_rules(self) -> tuple[InflectionRule, ...]:
        """Every registered rule, in registration order."""

        return tuple(self._rules.values())
