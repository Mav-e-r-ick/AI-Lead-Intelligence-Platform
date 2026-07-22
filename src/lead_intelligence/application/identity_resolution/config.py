"""IdentityResolutionProfile: the Identity Resolution Engine's single
configuration surface.

WHY THIS FILE EXISTS:
Per the approved RFC's requirement that "every scoring rule stays
configurable" — signal tiers, their weights, which signals are eligible for
candidate generation, which are contradiction-sensitive, and every
threshold used to turn a raw score into a decision all live here, not
scattered as literals through scoring.py or candidate_generation.py.
Profiles are supplied per-run, never read from global/environment state,
mirroring CleaningProfile — so two callers can run different profiles
concurrently and every scoring decision stays independently testable with
a fake profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from lead_intelligence.application.dto.identity_resolution_models import SignalTier
from lead_intelligence.domain.exceptions import (
    InvalidIdentityResolutionConfigurationError,
)


@dataclass(frozen=True)
class SignalTypeDefinition:
    """Static, configurable facts about one signal type (RFC §2).

    Attributes:
        tier: Strong / Moderate / Weak.
        weight: This signal type's contribution to a match score when it
            matches exactly, within [0.0, 1.0].
        usable_for_candidate_generation: Whether this signal type may be
            used to look up candidates. The RFC states a title match
            should "never be a matching signal on its own, only a
            corroborating detail" — modeled here by simply excluding title
            from candidate generation (so it can never single-handedly
            surface a candidate), rather than a special-cased branch
            elsewhere in the engine.
        contradiction_sensitive: Whether a *different* value for this
            signal type on an otherwise-matching candidate counts as
            active, score-reducing contradiction. True for near-unique
            identifiers where a mismatch is meaningful (an email, a DUNS
            number); false for anything that legitimately varies for the
            same real-world Subject over time (a phone number after a job
            change) — for those, a mismatch is simply not evidence either
            way, not counter-evidence.
    """

    tier: SignalTier
    weight: float
    usable_for_candidate_generation: bool = True
    contradiction_sensitive: bool = False


DEFAULT_SIGNAL_DEFINITIONS: dict[str, SignalTypeDefinition] = {
    "duns_number": SignalTypeDefinition(
        tier=SignalTier.STRONG, weight=1.0, contradiction_sensitive=True
    ),
    "email_exact": SignalTypeDefinition(
        tier=SignalTier.MODERATE, weight=0.5, contradiction_sensitive=True
    ),
    "company_domain_and_name": SignalTypeDefinition(
        tier=SignalTier.MODERATE, weight=0.45
    ),
    "company_name_city": SignalTypeDefinition(tier=SignalTier.MODERATE, weight=0.35),
    "full_name": SignalTypeDefinition(tier=SignalTier.WEAK, weight=0.15),
    "phone": SignalTypeDefinition(tier=SignalTier.WEAK, weight=0.12),
    "title": SignalTypeDefinition(
        tier=SignalTier.WEAK, weight=0.05, usable_for_candidate_generation=False
    ),
}


@dataclass(frozen=True)
class IdentityResolutionProfile:
    """Immutable, typed configuration for one IdentityResolutionEngine run.

    Attributes:
        name: Profile name (e.g. "default", "conservative").
        version: Profile version string, independent of any code version.
        signal_definitions: signal_type -> SignalTypeDefinition. Defaults
            to DEFAULT_SIGNAL_DEFINITIONS.
        auto_merge_threshold: A candidate scoring at or above this value is
            auto-merged (RFC §3, "Auto-merge" band).

            PRODUCT ACCURACY AUDIT, PRIORITY 3 — WHY PERSON-SUBJECT
            RESOLUTION CAN NEVER REACH THIS THRESHOLD, AND WHY THAT IS
            INTENTIONAL, NOT A BUG:
            Under DEFAULT_SIGNAL_DEFINITIONS, the only STRONG-tier signal
            is `duns_number`, a company identifier — `duns_number` is
            never extracted for `SubjectType.PERSON` (see
            `signal_extraction._extract_person_signals`, which only ever
            adds email/full_name/phone/title). The maximum possible score
            for a person-subject candidate is therefore the sum of every
            person signal's weight — email_exact(0.5) + full_name(0.15)
            + phone(0.12) + title(0.05) = 0.82 — structurally below the
            default 0.90 auto_merge_threshold, no matter how many person
            signals agree. This is confirmed intentional, not an
            oversight: `tests/unit/identity_resolution/test_engine.py`'s
            `test_resolve_record_queues_candidate_review_on_moderate_confidence`
            already asserts exactly this outcome — an email_exact + full_name
            match (the strongest realistic person-signal combination) is
            expected to be `CANDIDATE_REVIEW`, never `AUTO_MERGE` — and
            predates this audit. It follows directly from two explicit
            RFC rules already documented on `SignalTypeDefinition`: title
            must "never be a matching signal on its own, only a
            corroborating detail," and (RFC §2) "a single weak signal is
            never sufficient." Reserving auto-merge for either a
            Strong-tier identifier or an unusually strong combination
            reflects that person-level identifiers (an email, a name, a
            phone number) are individually far less certain than a
            company's DUNS number — `default_profile`'s own docstring
            calls this "the platform's conservative, out-of-the-box"
            profile. Every legitimately re-encountered executive is
            still correctly recognized (never silently dropped or
            treated as brand new) — it is routed to CANDIDATE_REVIEW for
            a human to confirm, exactly as designed. Left unchanged.
        candidate_review_threshold: A candidate scoring at or above this
            value (but below auto_merge_threshold) is queued for manual
            review (RFC §3, "Candidate" band). Below this: "No match".
        contradiction_penalty: Score subtracted per contradicting,
            contradiction-sensitive signal.
        min_independent_signals_without_strong_match: The RFC's rule that
            "a single weak signal is never sufficient" is enforced by this
            count: with no Strong-tier match, at least this many distinct
            signal types must independently support the same candidate
            before any nonzero score is produced at all.
        max_candidates_considered: Deterministic cap on how many candidates
            candidate_generation.py will return for scoring, keeping each
            run's cost and output both bounded and reproducible.
    """

    name: str
    version: str = "1.0.0"
    signal_definitions: Mapping[str, SignalTypeDefinition] = field(
        default_factory=lambda: dict(DEFAULT_SIGNAL_DEFINITIONS)
    )
    auto_merge_threshold: float = 0.90
    candidate_review_threshold: float = 0.55
    contradiction_penalty: float = 0.35
    min_independent_signals_without_strong_match: int = 2
    max_candidates_considered: int = 25

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "signal_definitions", MappingProxyType(dict(self.signal_definitions))
        )

    def definition_for(self, signal_type: str) -> SignalTypeDefinition:
        """The SignalTypeDefinition for `signal_type`.

        Raises:
            InvalidIdentityResolutionConfigurationError: If no definition
                exists for this signal type under this profile.
        """

        try:
            return self.signal_definitions[signal_type]
        except KeyError as exc:
            raise InvalidIdentityResolutionConfigurationError(
                f"Profile '{self.name}' has no definition for signal type "
                f"'{signal_type}'."
            ) from exc

    def validate(self) -> None:
        """Raise InvalidIdentityResolutionConfigurationError if this
        profile is self-contradictory. Called once, before any record is
        processed — a broken profile must fail the whole run immediately,
        not degrade into per-record failures.
        """

        if not self.signal_definitions:
            raise InvalidIdentityResolutionConfigurationError(
                f"Profile '{self.name}' has no signal_definitions configured."
            )
        if not (
            0.0 < self.candidate_review_threshold <= self.auto_merge_threshold <= 1.0
        ):
            raise InvalidIdentityResolutionConfigurationError(
                f"Profile '{self.name}' has invalid thresholds: "
                f"candidate_review_threshold={self.candidate_review_threshold}, "
                f"auto_merge_threshold={self.auto_merge_threshold}. Require "
                "0 < candidate_review_threshold <= auto_merge_threshold <= 1."
            )
        if self.contradiction_penalty < 0.0:
            raise InvalidIdentityResolutionConfigurationError(
                f"Profile '{self.name}' has a negative contradiction_penalty="
                f"{self.contradiction_penalty}; it is subtracted, not added, so "
                "it must be >= 0."
            )
        if self.min_independent_signals_without_strong_match < 1:
            raise InvalidIdentityResolutionConfigurationError(
                f"Profile '{self.name}' has "
                "min_independent_signals_without_strong_match="
                f"{self.min_independent_signals_without_strong_match}; must be >= 1."
            )
        if self.max_candidates_considered < 1:
            raise InvalidIdentityResolutionConfigurationError(
                f"Profile '{self.name}' has max_candidates_considered="
                f"{self.max_candidates_considered}; must be >= 1."
            )
        for signal_type, definition in self.signal_definitions.items():
            if not 0.0 <= definition.weight <= 1.0:
                raise InvalidIdentityResolutionConfigurationError(
                    f"Profile '{self.name}': signal type '{signal_type}' has "
                    f"weight={definition.weight}, must be within [0.0, 1.0]."
                )


def default_profile() -> IdentityResolutionProfile:
    """The platform's conservative, out-of-the-box Identity Resolution
    profile."""

    return IdentityResolutionProfile(name="default", version="1.0.0")
