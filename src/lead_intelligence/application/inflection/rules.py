"""The seven Version 1 detection rules, and the registry-ready tuple of
their instances.

Each rule is a small, single-responsibility class: it inspects one or two
FieldComparisons from a ComparisonResult and decides whether its specific,
named business pattern is present. None of them call an AI model, a
search engine, LinkedIn, or a verification service — every decision is a
deterministic check against `ComparisonStatus` values (and, for title
direction, the keyword-based `seniority_rank`).

WHY POSSIBLE_RESIGNATION AND EXECUTIVE_NO_LONGER_FOUND ARE MUTUALLY EXCLUSIVE:
Both rules react to "we can no longer confirm something about this
executive," but at different strengths. EXECUTIVE_NO_LONGER_FOUND fires
when the name itself can't be confirmed (MISSING) — the strongest "this
person isn't there anymore" signal. POSSIBLE_RESIGNATION fires only when
the *title* can't be confirmed (MISSING) while the *name* still resolves
to something other than MISSING — a softer, more tentative signal (hence
"Possible"). PossibleResignationRule explicitly excludes the case where
name is also MISSING, so the two rules never both fire off the same
underlying evidence.
"""

from __future__ import annotations

from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
)
from lead_intelligence.application.dto.inflection_models import InflectionType
from lead_intelligence.application.inflection.rule_base import (
    InflectionDraft,
    InflectionRule,
    InflectionRuleMetadata,
    get_field_comparison,
)
from lead_intelligence.application.inflection.seniority import seniority_rank


class PromotionRule(InflectionRule):
    """The title changed to a recognized, strictly more senior title."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-001",
            inflection_type=InflectionType.PROMOTION,
            name="Promotion",
            base_confidence=0.90,
            description=(
                "Title field is CHANGED, and the new title's seniority rank is "
                "strictly higher than the existing title's."
            ),
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        title = get_field_comparison(comparison_result, "title")
        if title is None or title.status is not ComparisonStatus.CHANGED:
            return None
        if title.existing_value is None or title.new_value is None:
            return None

        old_rank = seniority_rank(title.existing_value)
        new_rank = seniority_rank(title.new_value)
        if old_rank is None or new_rank is None or new_rank <= old_rank:
            return None

        return InflectionDraft(
            supporting_comparisons=(title,),
            explanation=(
                f"Title changed from '{title.existing_value}' (seniority rank "
                f"{old_rank}) to '{title.new_value}' (seniority rank {new_rank}), "
                "a move to a more senior title."
            ),
        )


class DemotionRule(InflectionRule):
    """The title changed to a recognized, strictly less senior title."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-002",
            inflection_type=InflectionType.DEMOTION,
            name="Demotion",
            base_confidence=0.90,
            description=(
                "Title field is CHANGED, and the new title's seniority rank is "
                "strictly lower than the existing title's."
            ),
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        title = get_field_comparison(comparison_result, "title")
        if title is None or title.status is not ComparisonStatus.CHANGED:
            return None
        if title.existing_value is None or title.new_value is None:
            return None

        old_rank = seniority_rank(title.existing_value)
        new_rank = seniority_rank(title.new_value)
        if old_rank is None or new_rank is None or new_rank >= old_rank:
            return None

        return InflectionDraft(
            supporting_comparisons=(title,),
            explanation=(
                f"Title changed from '{title.existing_value}' (seniority rank "
                f"{old_rank}) to '{title.new_value}' (seniority rank {new_rank}), "
                "a move to a less senior title."
            ),
        )


class CompanyChangeRule(InflectionRule):
    """The company field changed to a different, confirmed company."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-003",
            inflection_type=InflectionType.COMPANY_CHANGE,
            name="Company Change",
            base_confidence=0.95,
            description="Company field is CHANGED: the existing and new company differ.",
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        company = get_field_comparison(comparison_result, "company")
        if company is None or company.status is not ComparisonStatus.CHANGED:
            return None

        return InflectionDraft(
            supporting_comparisons=(company,),
            explanation=(
                f"Company changed from '{company.existing_value}' to "
                f"'{company.new_value}'."
            ),
        )


class PossibleResignationRule(InflectionRule):
    """The title can no longer be confirmed, but the executive's name still
    resolves to something other than MISSING (see module docstring for why
    this is distinct from ExecutiveNoLongerFoundRule)."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-004",
            inflection_type=InflectionType.POSSIBLE_RESIGNATION,
            name="Possible Resignation",
            base_confidence=0.50,
            description=(
                "Title field is MISSING while the name field is not MISSING — the "
                "executive's role can no longer be confirmed, though their "
                "identity still can be."
            ),
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        title = get_field_comparison(comparison_result, "title")
        name = get_field_comparison(comparison_result, "name")
        if title is None or name is None:
            return None
        if title.status is not ComparisonStatus.MISSING:
            return None
        if name.status is ComparisonStatus.MISSING:
            return None  # ExecutiveNoLongerFoundRule covers this, more strongly.

        return InflectionDraft(
            supporting_comparisons=(title, name),
            explanation=(
                f"Title '{title.existing_value}' is no longer confirmed by any new "
                "observation, though the executive's name is still recognized — "
                "possibly a resignation or role change."
            ),
        )


class ContactInfoChangedRule(InflectionRule):
    """The email and/or phone field changed."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-005",
            inflection_type=InflectionType.CONTACT_INFO_CHANGED,
            name="Contact Information Changed",
            base_confidence=0.70,
            description="Email and/or phone field is CHANGED.",
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        email = get_field_comparison(comparison_result, "email")
        phone = get_field_comparison(comparison_result, "phone")
        changed = tuple(
            comparison
            for comparison in (email, phone)
            if comparison is not None and comparison.status is ComparisonStatus.CHANGED
        )
        if not changed:
            return None

        fields_description = "; ".join(
            f"{comparison.field_name} changed from '{comparison.existing_value}' to "
            f"'{comparison.new_value}'"
            for comparison in changed
        )
        return InflectionDraft(
            supporting_comparisons=changed,
            explanation=f"Contact information changed: {fields_description}.",
        )


class ExecutiveNewlyAppearedRule(InflectionRule):
    """No existing name was on record; a new observation identifies one."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-006",
            inflection_type=InflectionType.EXECUTIVE_NEWLY_APPEARED,
            name="Executive Newly Appeared",
            base_confidence=0.85,
            description="Name field is NEW: no existing value, a new observation provides one.",
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        name = get_field_comparison(comparison_result, "name")
        if name is None or name.status is not ComparisonStatus.NEW:
            return None

        return InflectionDraft(
            supporting_comparisons=(name,),
            explanation=(
                "No existing name was on record; a new observation identifies "
                f"this executive as '{name.new_value}'."
            ),
        )


class ExecutiveNoLongerFoundRule(InflectionRule):
    """An existing name can no longer be confirmed by any new observation."""

    @property
    def metadata(self) -> InflectionRuleMetadata:
        return InflectionRuleMetadata(
            rule_id="INF-007",
            inflection_type=InflectionType.EXECUTIVE_NO_LONGER_FOUND,
            name="Executive No Longer Found",
            base_confidence=0.85,
            description=(
                "Name field is MISSING: an existing value is on record, but no "
                "new observation confirms it."
            ),
        )

    def detect(self, comparison_result: ComparisonResult) -> InflectionDraft | None:
        name = get_field_comparison(comparison_result, "name")
        if name is None or name.status is not ComparisonStatus.MISSING:
            return None

        return InflectionDraft(
            supporting_comparisons=(name,),
            explanation=(
                f"Existing name '{name.existing_value}' is no longer confirmed by "
                "any new observation."
            ),
        )


#: Every Version 1 rule, in the numeric order of their rule ids
#: (INF-001..INF-007) — the registry-ready default set.
ALL_RULES: tuple[InflectionRule, ...] = (
    PromotionRule(),
    DemotionRule(),
    CompanyChangeRule(),
    PossibleResignationRule(),
    ContactInfoChangedRule(),
    ExecutiveNewlyAppearedRule(),
    ExecutiveNoLongerFoundRule(),
)
