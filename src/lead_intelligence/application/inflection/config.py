"""InflectionRuleOverride and InflectionProfile: the Inflection Detection
Engine's single configuration surface.

WHY THIS FILE EXISTS:
Mirrors ComparisonProfile / EnrichmentProfile's role: which rules run, and
at what confidence, is a per-run configuration decision, not a literal
buried in engine.py or rules.py. A rule's own `base_confidence` (in its
InflectionRuleMetadata) is its author's honest default; a profile may
override that default per-deployment, or disable a rule entirely, without
touching the rule's code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from lead_intelligence.application.inflection.rule_base import InflectionRule
from lead_intelligence.domain.exceptions import InvalidInflectionConfigurationError


@dataclass(frozen=True)
class InflectionRuleOverride:
    """A per-rule configuration override.

    Attributes:
        enabled: Whether this rule should run at all. Defaults to True.
        base_confidence: If set, replaces the rule's own
            `InflectionRuleMetadata.base_confidence` for this profile. Must
            be within [0.0, 1.0] — see InflectionProfile.validate().
    """

    enabled: bool = True
    base_confidence: float | None = None


@dataclass(frozen=True)
class InflectionProfile:
    """Immutable, typed configuration for one InflectionDetectionEngine run.

    Attributes:
        name: Profile name (e.g. "default", "strict").
        version: Profile version string, independent of any code version.
        rule_overrides: Per-`rule_id` overrides. A rule with no entry here
            runs enabled, at its own `base_confidence`. Defaults to empty
            (every rule enabled, unmodified).
    """

    name: str
    version: str = "1.0.0"
    rule_overrides: Mapping[str, InflectionRuleOverride] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def is_enabled(self, rule: InflectionRule) -> bool:
        """Whether `rule` should run under this profile."""

        override = self.rule_overrides.get(rule.metadata.rule_id)
        return override is None or override.enabled

    def confidence_for(self, rule: InflectionRule) -> float:
        """The base confidence to use for `rule` under this profile: the
        override's `base_confidence` if one is configured, else the rule's
        own `InflectionRuleMetadata.base_confidence`.
        """

        override = self.rule_overrides.get(rule.metadata.rule_id)
        if override is not None and override.base_confidence is not None:
            return override.base_confidence
        return rule.metadata.base_confidence

    def validate(self) -> None:
        """Raise InvalidInflectionConfigurationError if this profile is
        self-contradictory. Called once, before any rule runs — a broken
        profile must fail the whole run immediately, not degrade into
        per-rule failures.
        """

        for rule_id, override in self.rule_overrides.items():
            if override.base_confidence is None:
                continue
            if not (0.0 <= override.base_confidence <= 1.0):
                raise InvalidInflectionConfigurationError(
                    f"Profile '{self.name}': override for rule '{rule_id}' has "
                    f"base_confidence={override.base_confidence}, must be within "
                    "[0.0, 1.0]."
                )


def default_profile() -> InflectionProfile:
    """The platform's conservative, out-of-the-box Inflection profile."""

    return InflectionProfile(name="default", version="1.0.0")
