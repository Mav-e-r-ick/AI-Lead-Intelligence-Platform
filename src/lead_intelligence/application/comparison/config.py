"""ComparisonFieldRule and ComparisonProfile: the Executive Comparison
Engine's single configuration surface.

WHY THIS FILE EXISTS:
Mirrors CleaningProfile / IdentityResolutionProfile / EnrichmentProfile's
role: every knob a caller might reasonably want to turn — which fields are
compared, in what order, with which strategy (exact vs. fuzzy), at what
fuzzy similarity threshold, and which ObservationCandidate attributes
count as "new value" evidence for a field — lives here, not scattered as
literals through engine.py. Profiles are supplied per-run, never read
from global/environment state, so two callers can run different profiles
concurrently and every comparison decision stays independently testable
with a fake profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lead_intelligence.application.comparison.resolvers import EXISTING_VALUE_RESOLVERS
from lead_intelligence.application.dto.comparison_models import ComparisonStrategy
from lead_intelligence.domain.exceptions import InvalidComparisonConfigurationError


@dataclass(frozen=True)
class ComparisonFieldRule:
    """Configuration for comparing one field.

    Attributes:
        field_name: The canonical comparable field name (e.g. "name").
            Must have a matching entry in
            `resolvers.EXISTING_VALUE_RESOLVERS` — see
            ComparisonProfile.validate().
        observation_attributes: Which `ObservationCandidate.attribute`
            values count as "new value" evidence for this field. Empty
            means no current provider reports this field — the comparison
            still runs, using whatever the existing record has (typically
            producing MISSING or UNKNOWN), honestly reflecting that no new
            information exists yet rather than fabricating a value.
        strategy: EXACT or FUZZY.
        fuzzy_threshold: For FUZZY fields, the similarity score (from
            `comparators.similarity`) at or above which two present values
            are considered MATCH rather than CHANGED. Ignored for EXACT
            fields.
    """

    field_name: str
    observation_attributes: tuple[str, ...]
    strategy: ComparisonStrategy
    fuzzy_threshold: float = 0.85


DEFAULT_FIELD_RULES: tuple[ComparisonFieldRule, ...] = (
    ComparisonFieldRule(
        "name", ("full_name",), ComparisonStrategy.FUZZY, fuzzy_threshold=0.85
    ),
    ComparisonFieldRule(
        "title", ("title",), ComparisonStrategy.FUZZY, fuzzy_threshold=0.80
    ),
    ComparisonFieldRule("company", (), ComparisonStrategy.FUZZY, fuzzy_threshold=0.80),
    ComparisonFieldRule("email", ("email",), ComparisonStrategy.EXACT),
    ComparisonFieldRule("phone", ("phone",), ComparisonStrategy.EXACT),
)


@dataclass(frozen=True)
class ComparisonProfile:
    """Immutable, typed configuration for one ComparisonEngine run.

    Attributes:
        name: Profile name (e.g. "default", "strict").
        version: Profile version string, independent of any code version.
        field_rules: One ComparisonFieldRule per comparable field, in the
            order FieldComparisons are produced. Defaults to
            DEFAULT_FIELD_RULES (name, title, company, email, phone).
    """

    name: str
    version: str = "1.0.0"
    field_rules: tuple[ComparisonFieldRule, ...] = field(
        default_factory=lambda: DEFAULT_FIELD_RULES
    )

    def validate(self) -> None:
        """Raise InvalidComparisonConfigurationError if this profile is
        self-contradictory. Called once, before any field is compared — a
        broken profile must fail the whole run immediately, not degrade
        into per-field failures.
        """

        if not self.field_rules:
            raise InvalidComparisonConfigurationError(
                f"Profile '{self.name}' has no field_rules configured."
            )

        seen: set[str] = set()
        for rule in self.field_rules:
            if rule.field_name in seen:
                raise InvalidComparisonConfigurationError(
                    f"Profile '{self.name}' has more than one rule for field "
                    f"'{rule.field_name}'."
                )
            seen.add(rule.field_name)

            if rule.field_name not in EXISTING_VALUE_RESOLVERS:
                raise InvalidComparisonConfigurationError(
                    f"Profile '{self.name}': field '{rule.field_name}' has no "
                    "matching entry in resolvers.EXISTING_VALUE_RESOLVERS."
                )

            if rule.strategy is ComparisonStrategy.FUZZY and not (
                0.0 <= rule.fuzzy_threshold <= 1.0
            ):
                raise InvalidComparisonConfigurationError(
                    f"Profile '{self.name}': field '{rule.field_name}' has "
                    f"fuzzy_threshold={rule.fuzzy_threshold}, must be within [0.0, 1.0]."
                )


def default_profile() -> ComparisonProfile:
    """The platform's conservative, out-of-the-box Comparison profile."""

    return ComparisonProfile(name="default", version="1.0.0")
