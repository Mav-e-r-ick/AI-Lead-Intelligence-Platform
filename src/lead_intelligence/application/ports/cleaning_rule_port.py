"""The contracts every cleaning rule must implement.

WHY THIS FILE EXISTS:
CleaningPipeline must be able to run 68 (and eventually more) different
rules polymorphically without knowing anything about any specific one. Two
separate interfaces exist — not one — specifically so a QualityCheckRule is
*structurally* incapable of returning a changed value: its return type is a
list of warning drafts, nothing else. This is "make illegal states
unrepresentable" applied to the non-destructiveness guarantee CLEANING_RULES.md
promises for every Warning-type rule, enforced by the type system rather
than by convention or code review alone.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping

from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft

if TYPE_CHECKING:
    from lead_intelligence.application.cleaning.config import CleaningProfile


class RuleStage(str, Enum):
    """Which of the three CLEANING_RULES.md categories a rule belongs to."""

    SAFE = "safe"
    BUSINESS = "business"
    WARNING = "warning"


class RuleCategory(str, Enum):
    """Which of the 8 CLEANING_RULES.md sections a rule belongs to."""

    IDENTITY = "identity"
    CONTACT = "contact"
    COMPANY = "company"
    ADDRESS = "address"
    FINANCIAL = "financial"
    INDUSTRY = "industry"
    METADATA = "metadata"
    CROSS_FIELD = "cross_field"


@dataclass(frozen=True)
class RuleMetadata:
    """Static facts about a rule, matching its CLEANING_RULES.md entry exactly.

    Every rule instance exposes one of these via its `metadata` property, so
    the pipeline, metrics, and audit trail can all introspect a rule
    generically instead of special-casing each one.

    Attributes:
        rule_id: Permanent Rule ID, e.g. "CLN-004" (see CLEANING_RULES.md §3).
        name: Human-readable rule name, matching the registry entry.
        category: One of the 8 registry categories.
        stage: Safe, Business, or Warning.
        fields: The field(s) this rule reads (and, for NormalizationRule, writes).
        version: This rule's own version (see CLEANING_RULES.md §5 — bump
            whenever the rule's logic could change output for input it has
            already processed before).
        configurable: Whether this rule accepts profile-supplied parameters.
        default_enabled: Whether a profile with no explicit override runs
            this rule. Ignored for Safe rules, which always run.
        dependencies: Rule IDs that must run before this one, if any.
    """

    rule_id: str
    name: str
    category: RuleCategory
    stage: RuleStage
    fields: tuple[str, ...]
    version: int = 1
    configurable: bool = False
    default_enabled: bool = True
    dependencies: tuple[str, ...] = field(default_factory=tuple)


class NormalizationRule(ABC):
    """A rule that may change field values — used for the Safe and Business stages.

    Concrete rules implement `metadata` (stage=SAFE or stage=BUSINESS) and
    `apply()`. `apply()` returns only the fields it actually changed; a rule
    that changes nothing returns an empty mapping. The caller (CleaningPipeline)
    already holds the pre-call values, so it derives old_value itself when
    building the audit trail — keeping this interface's only job "compute
    new values," never "assemble audit metadata."
    """

    @property
    @abstractmethod
    def metadata(self) -> RuleMetadata:
        """This rule's static registry metadata."""

    @abstractmethod
    def apply(
        self, values: Mapping[str, Any], profile: "CleaningProfile"
    ) -> Mapping[str, Any]:
        """Return the subset of this rule's fields whose value should change.

        Args:
            values: Canonical-field-name -> current value, reflecting every
                rule that has already run earlier in the pipeline.
            profile: The active CleaningProfile, for reading this rule's
                own configured parameters via `profile.parameters_for(rule_id)`.

        Returns:
            A mapping of only the fields this call changed. Fields left
            unchanged must be omitted, not returned with their old value.
        """

    def validate_config(self, profile: "CleaningProfile") -> None:
        """Raise InvalidCleaningConfigurationError if this rule is enabled
        with missing/contradictory configuration.

        Called once by CleaningPipeline for every enabled rule, before any
        record is processed (see CLEANING_RULES.md §4: a broken profile
        must fail the whole run immediately). Default no-op; only rules
        with required parameters (e.g. CLN-016's default phone region)
        override this.
        """


class QualityCheckRule(ABC):
    """A rule that only observes — used for the Warning stage.

    Cannot alter data even by accident: apply() returns warning drafts only.
    """

    @property
    @abstractmethod
    def metadata(self) -> RuleMetadata:
        """This rule's static registry metadata."""

    @abstractmethod
    def apply(
        self, values: Mapping[str, Any], profile: "CleaningProfile"
    ) -> list[QualityWarningDraft]:
        """Return zero or more warnings about the current field values.

        Args:
            values: Canonical-field-name -> current value, after every Safe
                and (if enabled) Business rule has already run.
            profile: The active CleaningProfile, for reading this rule's
                own configured thresholds via `profile.parameters_for(rule_id)`.

        Returns:
            A list of QualityWarningDraft — empty if nothing is worth flagging.
        """

    def validate_config(self, profile: "CleaningProfile") -> None:
        """Raise InvalidCleaningConfigurationError if this rule is enabled
        with missing/contradictory configuration. Default no-op; see
        NormalizationRule.validate_config for the full rationale.
        """
