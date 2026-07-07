"""CleaningProfile: the Cleaning Engine's single configuration surface.

WHY THIS FILE EXISTS:
Per CLEANING_RULES.md §8 ("Configuration strategy" in the approved
architecture): Safe rules have no configuration surface at all — that
absence is deliberate, not an oversight. Every Business and Warning rule is
individually toggleable, with conservative, documented defaults
(CLEANING_RULES.md's Default-Enabled Policy). Profiles are supplied
per-run, never read from global/environment state, so two callers can run
different profiles concurrently and every rule stays independently testable
with a fake profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

from lead_intelligence.application.cleaning.field_contract import DEFAULT_FIELD_MAPPING
from lead_intelligence.application.ports.cleaning_rule_port import RuleMetadata
from lead_intelligence.domain.exceptions import InvalidCleaningConfigurationError

if TYPE_CHECKING:
    from lead_intelligence.application.ports.cleaning_rule_port import (
        NormalizationRule,
        QualityCheckRule,
    )


@dataclass(frozen=True)
class RuleOverride:
    """A profile's override for one specific rule.

    Attributes:
        enabled: True/False to force this rule on/off; None means "use the
            rule's own default_enabled" (irrelevant for Safe rules, which
            always run regardless).
        parameters: Rule-specific configuration (e.g. a length threshold, a
            target casing format, a default phone region).
    """

    enabled: bool | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True)
class CleaningProfile:
    """Immutable, typed configuration for one CleaningPipeline run.

    Attributes:
        name: Profile name (e.g. "default", "us_b2b_outreach").
        version: Profile version string, independent of any rule's own version.
        field_mapping: canonical field name -> literal source column name,
            for the specific dataset this profile will clean. Defaults to
            DEFAULT_FIELD_MAPPING (the reference D&B Hoovers schema).
        enable_business_normalization: Master switch for the entire Business
            stage. False lets a caller run Safe-plus-Warnings only (e.g. for
            a compliance-sensitive integration that must preserve exact
            source values but still wants a QA warning report).
        rule_overrides: rule_id -> RuleOverride, for individually toggling
            or parameterizing specific rules.
    """

    name: str
    version: str = "1.0.0"
    field_mapping: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_FIELD_MAPPING)
    )
    enable_business_normalization: bool = True
    rule_overrides: Mapping[str, RuleOverride] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "field_mapping", MappingProxyType(dict(self.field_mapping))
        )
        object.__setattr__(
            self, "rule_overrides", MappingProxyType(dict(self.rule_overrides))
        )

    def is_enabled(
        self, rule_or_metadata: "RuleMetadata | NormalizationRule | QualityCheckRule"
    ) -> bool:
        """Whether the given rule should run under this profile.

        Accepts either a rule instance (reads its `.metadata`) or a
        RuleMetadata directly. Safe-stage rules are always enabled,
        regardless of overrides — this method is never even consulted for
        them by CleaningPipeline, but returns True defensively if it is.
        """

        rule_metadata = (
            rule_or_metadata
            if isinstance(rule_or_metadata, RuleMetadata)
            else rule_or_metadata.metadata
        )
        if rule_metadata.stage.value == "safe":
            return True

        override = self.rule_overrides.get(rule_metadata.rule_id)
        if override is not None and override.enabled is not None:
            return override.enabled
        return rule_metadata.default_enabled

    def parameters_for(self, rule_id: str) -> Mapping[str, Any]:
        """Configured parameters for a rule, or an empty mapping if none set."""

        override = self.rule_overrides.get(rule_id)
        if override is None:
            return MappingProxyType({})
        return override.parameters

    def validate(self) -> None:
        """Raise InvalidCleaningConfigurationError if this profile is self-contradictory.

        Called once, before any record is processed (see
        CLEANING_RULES.md §4: a broken profile must fail the whole run
        immediately, not degrade into per-record failures).
        """

        if not self.field_mapping:
            raise InvalidCleaningConfigurationError(
                f"Profile '{self.name}' has an empty field_mapping; no rule "
                "could resolve any field."
            )


def default_profile() -> CleaningProfile:
    """The platform's conservative, out-of-the-box profile.

    Every Safe rule runs. Business rules follow CLEANING_RULES.md's
    Default-Enabled Policy (on only where a specific defect was fixed; off
    where the rule encodes a style preference). All Warning rules run.
    """

    return CleaningProfile(name="default", version="1.0.0")
