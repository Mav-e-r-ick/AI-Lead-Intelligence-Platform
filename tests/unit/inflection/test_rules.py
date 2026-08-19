"""Tests for the seven Version 1 detection rules."""

from __future__ import annotations

from lead_intelligence.application.dto.comparison_models import ComparisonStatus
from lead_intelligence.application.inflection.rules import (
    ALL_RULES,
    CompanyChangeRule,
    ContactInfoChangedRule,
    DemotionRule,
    ExecutiveNewlyAppearedRule,
    ExecutiveNoLongerFoundRule,
    PossibleResignationRule,
    PromotionRule,
)
from tests.unit.inflection.fixtures import (
    make_all_match_comparisons,
    make_comparison_result,
    make_field_comparison,
)


class TestPromotionRule:
    def test_fires_on_higher_seniority_title_change(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        draft = PromotionRule().detect(result)

        assert draft is not None
        assert title in draft.supporting_comparisons

    def test_does_not_fire_when_title_matches(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        assert PromotionRule().detect(result) is None

    def test_does_not_fire_for_lower_seniority_change(self) -> None:
        title = make_field_comparison(
            "title", "Vice President", "Manager", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        assert PromotionRule().detect(result) is None

    def test_does_not_fire_when_seniority_unrecognized(self) -> None:
        title = make_field_comparison(
            "title", "Widget Wizard", "Gadget Guru", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        assert PromotionRule().detect(result) is None

    def test_does_not_fire_when_title_missing(self) -> None:
        title = make_field_comparison(
            "title", "Manager", None, ComparisonStatus.MISSING
        )
        name = make_field_comparison(
            "name", "Ada Lovelace", "Ada Lovelace", ComparisonStatus.MATCH
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title, name=name)
        )

        assert PromotionRule().detect(result) is None


class TestDemotionRule:
    def test_fires_on_lower_seniority_title_change(self) -> None:
        title = make_field_comparison(
            "title", "Vice President", "Manager", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        draft = DemotionRule().detect(result)

        assert draft is not None
        assert title in draft.supporting_comparisons

    def test_does_not_fire_for_higher_seniority_change(self) -> None:
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(title=title))

        assert DemotionRule().detect(result) is None


class TestCompanyChangeRule:
    def test_fires_when_company_changed(self) -> None:
        company = make_field_comparison(
            "company", "Acme Corp", "Globex", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(company=company))

        draft = CompanyChangeRule().detect(result)

        assert draft is not None
        assert company in draft.supporting_comparisons

    def test_does_not_fire_when_company_matches(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        assert CompanyChangeRule().detect(result) is None


class TestPossibleResignationRule:
    def test_fires_when_title_missing_and_name_present(self) -> None:
        title = make_field_comparison("title", "CEO", None, ComparisonStatus.MISSING)
        name = make_field_comparison(
            "name", "Ada Lovelace", "Ada Lovelace", ComparisonStatus.MATCH
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title, name=name)
        )

        draft = PossibleResignationRule().detect(result)

        assert draft is not None
        assert title in draft.supporting_comparisons
        assert name in draft.supporting_comparisons

    def test_does_not_fire_when_name_also_missing(self) -> None:
        title = make_field_comparison("title", "CEO", None, ComparisonStatus.MISSING)
        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title, name=name)
        )

        # ExecutiveNoLongerFoundRule covers this case instead.
        assert PossibleResignationRule().detect(result) is None

    def test_does_not_fire_when_title_present(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        assert PossibleResignationRule().detect(result) is None

    def test_does_not_fire_when_company_change_is_confirmed(self) -> None:
        """Regression test for Product Accuracy Audit Priority 5: a real
        company-change observation with no full_name observation in the
        same batch left `title` MISSING (no title evidence either) while
        `company` genuinely changed -- POSSIBLE_RESIGNATION must not fire
        alongside that confirmed positive evidence."""

        title = make_field_comparison("title", "CEO", None, ComparisonStatus.MISSING)
        name = make_field_comparison(
            "name", "Ada Lovelace", "Ada Lovelace", ComparisonStatus.MATCH
        )
        company = make_field_comparison(
            "company", "Acme Corp", "Globex Inc", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title, name=name, company=company)
        )

        assert PossibleResignationRule().detect(result) is None


class TestContactInfoChangedRule:
    def test_fires_when_email_changed(self) -> None:
        email = make_field_comparison(
            "email", "old@example.com", "new@example.com", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(email=email))

        draft = ContactInfoChangedRule().detect(result)

        assert draft is not None
        assert email in draft.supporting_comparisons

    def test_fires_when_phone_changed(self) -> None:
        phone = make_field_comparison(
            "phone", "555-1000", "555-2000", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(make_all_match_comparisons(phone=phone))

        draft = ContactInfoChangedRule().detect(result)

        assert draft is not None
        assert phone in draft.supporting_comparisons

    def test_fires_with_both_when_both_changed(self) -> None:
        email = make_field_comparison(
            "email", "old@example.com", "new@example.com", ComparisonStatus.CHANGED
        )
        phone = make_field_comparison(
            "phone", "555-1000", "555-2000", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(email=email, phone=phone)
        )

        draft = ContactInfoChangedRule().detect(result)

        assert draft is not None
        assert email in draft.supporting_comparisons
        assert phone in draft.supporting_comparisons

    def test_does_not_fire_when_contact_fields_match(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        assert ContactInfoChangedRule().detect(result) is None


class TestExecutiveNewlyAppearedRule:
    def test_fires_when_name_is_new(self) -> None:
        name = make_field_comparison("name", None, "Ada Lovelace", ComparisonStatus.NEW)
        result = make_comparison_result(make_all_match_comparisons(name=name))

        draft = ExecutiveNewlyAppearedRule().detect(result)

        assert draft is not None
        assert name in draft.supporting_comparisons

    def test_does_not_fire_when_name_matches(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        assert ExecutiveNewlyAppearedRule().detect(result) is None


class TestExecutiveNoLongerFoundRule:
    def test_fires_when_name_is_missing(self) -> None:
        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        result = make_comparison_result(make_all_match_comparisons(name=name))

        draft = ExecutiveNoLongerFoundRule().detect(result)

        assert draft is not None
        assert name in draft.supporting_comparisons

    def test_does_not_fire_when_name_matches(self) -> None:
        result = make_comparison_result(make_all_match_comparisons())

        assert ExecutiveNoLongerFoundRule().detect(result) is None

    def test_does_not_fire_alongside_a_confirmed_title_change(self) -> None:
        """Regression test for Product Accuracy Audit Priority 5,
        reproducing the real co-firing observed in this session's demo:
        a real title-change observation (e.g. a promotion announcement)
        with no full_name observation in the same batch (email/phone/
        title are extracted independently of name by
        SearchExtractionEngine) left `name` MISSING while `title`
        genuinely changed -- EXECUTIVE_NO_LONGER_FOUND fired alongside a
        real, positive PromotionRule detection. It must not."""

        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        title = make_field_comparison(
            "title", "Manager", "Vice President", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(name=name, title=title)
        )

        assert PromotionRule().detect(result) is not None
        assert ExecutiveNoLongerFoundRule().detect(result) is None

    def test_does_not_fire_alongside_a_confirmed_company_change(self) -> None:
        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        company = make_field_comparison(
            "company", "Acme Corp", "Globex Inc", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(name=name, company=company)
        )

        assert CompanyChangeRule().detect(result) is not None
        assert ExecutiveNoLongerFoundRule().detect(result) is None

    def test_does_not_fire_alongside_a_confirmed_email_change(self) -> None:
        """Regression test for the most common real shape of this bug,
        reproduced end-to-end by simulate_pipeline.py's `contact_change`
        scenario: SearchExtractionEngine extracts email independently of
        the name/title/company announcement pattern, so a leadership-page
        bio card routinely yields a new email with no parseable name --
        leaving `name` MISSING while proving the executive was found.
        EXECUTIVE_NO_LONGER_FOUND (0.85) fired anyway and outranked the
        correct CONTACT_INFO_CHANGED (0.70), so the drafted message was
        "it's been a while" instead of the contact-update one."""

        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        email = make_field_comparison(
            "email", "ada@acme.com", "ada.new@acme.com", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(name=name, email=email)
        )

        assert ContactInfoChangedRule().detect(result) is not None
        assert ExecutiveNoLongerFoundRule().detect(result) is None

    def test_does_not_fire_alongside_a_confirmed_phone_change(self) -> None:
        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        phone = make_field_comparison(
            "phone", "+14155550100", "+14155550199", ComparisonStatus.CHANGED
        )
        result = make_comparison_result(
            make_all_match_comparisons(name=name, phone=phone)
        )

        assert ContactInfoChangedRule().detect(result) is not None
        assert ExecutiveNoLongerFoundRule().detect(result) is None

    def test_still_fires_when_no_other_field_has_confirmed_evidence(self) -> None:
        # Guard rail: the new positive-evidence check must not silently
        # suppress the genuine, evidence-free case this rule exists for.
        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        result = make_comparison_result(make_all_match_comparisons(name=name))

        assert ExecutiveNoLongerFoundRule().detect(result) is not None


class TestMutualExclusivity:
    def test_possible_resignation_and_executive_no_longer_found_never_both_fire(
        self,
    ) -> None:
        title = make_field_comparison("title", "CEO", None, ComparisonStatus.MISSING)
        name = make_field_comparison(
            "name", "Ada Lovelace", None, ComparisonStatus.MISSING
        )
        result = make_comparison_result(
            make_all_match_comparisons(title=title, name=name)
        )

        assert PossibleResignationRule().detect(result) is None
        assert ExecutiveNoLongerFoundRule().detect(result) is not None


class TestAllRules:
    def test_all_rules_has_seven_unique_rule_ids(self) -> None:
        rule_ids = {rule.metadata.rule_id for rule in ALL_RULES}

        assert len(ALL_RULES) == 7
        assert len(rule_ids) == 7

    def test_all_rules_cover_every_inflection_type(self) -> None:
        from lead_intelligence.application.dto.inflection_models import InflectionType

        detected_types = {rule.metadata.inflection_type for rule in ALL_RULES}

        assert detected_types == set(InflectionType)
