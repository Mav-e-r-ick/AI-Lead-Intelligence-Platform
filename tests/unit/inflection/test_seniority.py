"""Tests for the keyword-based title seniority ranking."""

from __future__ import annotations

import pytest

from lead_intelligence.application.inflection.seniority import seniority_rank


class TestSeniorityRank:
    def test_unrecognized_title_returns_none(self) -> None:
        assert seniority_rank("Wizard of Widgets") is None

    def test_case_insensitive(self) -> None:
        assert seniority_rank("chief executive officer") == seniority_rank(
            "CHIEF EXECUTIVE OFFICER"
        )

    def test_ceo_outranks_manager(self) -> None:
        assert seniority_rank("CEO") > seniority_rank("Manager")  # type: ignore[operator]

    def test_manager_outranks_analyst(self) -> None:
        assert seniority_rank("Manager") > seniority_rank("Analyst")  # type: ignore[operator]

    def test_vice_president_and_vp_are_equal_rank(self) -> None:
        assert seniority_rank("Vice President") == seniority_rank("VP")

    def test_senior_vice_president_outranks_vice_president(self) -> None:
        assert seniority_rank("Senior Vice President") > seniority_rank(  # type: ignore[operator]
            "Vice President"
        )

    def test_longer_phrase_wins_over_shorter_substring(self) -> None:
        # "Director" is a substring of "Senior Director"; the longer, more
        # specific phrase must win (max-match), not whichever keyword the
        # table happens to check first.
        assert seniority_rank("Senior Director") > seniority_rank("Director")  # type: ignore[operator]

    def test_empty_string_returns_none(self) -> None:
        assert seniority_rank("") is None

    def test_whitespace_is_stripped(self) -> None:
        assert seniority_rank("  CEO  ") == seniority_rank("CEO")


class TestNamedCSuiteTitles:
    """Regression tests for Product Accuracy Audit Priority 4: named
    C-suite functional titles (COO, CFO, CTO, CIO, CMO, CHRO, and several
    "Chief ... Officer" variants) previously all fell through to the
    generic "chief" keyword, so they were indistinguishable from each
    other and from any other unrecognized "Chief"-something title."""

    @pytest.mark.parametrize(
        "title",
        [
            "Chief Operating Officer",
            "COO",
            "Chief Financial Officer",
            "CFO",
            "Chief Technology Officer",
            "CTO",
            "Chief Information Officer",
            "CIO",
            "Chief Marketing Officer",
            "CMO",
            "Chief Human Resources Officer",
            "CHRO",
            "Chief Revenue Officer",
            "Chief Experience Officer",
            "Chief Relationship Officer",
            "Chief Product Officer",
            "Chief Growth Officer",
            "Chief Data Officer",
            "Chief Digital Officer",
        ],
    )
    def test_every_named_c_suite_title_is_recognized(self, title: str) -> None:
        assert seniority_rank(title) is not None

    def test_named_c_suite_titles_outrank_vice_president_tier(self) -> None:
        for title in ("COO", "CFO", "CTO", "Chief Experience Officer"):
            assert seniority_rank(title) > seniority_rank(  # type: ignore[operator]
                "Executive Vice President"
            )

    def test_named_c_suite_titles_do_not_outrank_ceo(self) -> None:
        for title in ("COO", "CFO", "CTO", "Chief Experience Officer"):
            assert seniority_rank(title) < seniority_rank("CEO")  # type: ignore[operator]

    def test_two_different_c_suite_titles_are_equal_rank(self) -> None:
        # Real case from the audit: "Chief Relationship Officer" ->
        # "Chief Operating Officer" must not be silently guessed as a
        # promotion or demotion -- neither title outranks the other by
        # any evidence this module has, so they compare equal (see
        # seniority.py's own docstring for why).
        assert seniority_rank("Chief Relationship Officer") == seniority_rank(
            "Chief Operating Officer"
        )

    def test_ambiguous_acronyms_are_not_recognized(self) -> None:
        # "CRO"/"CPO"/"CDO" each have two common, conflicting real-world
        # meanings (Revenue vs. Risk, Product vs. People, Data vs.
        # Digital) -- only the unambiguous spelled-out forms are
        # recognized, never the acronym.
        assert seniority_rank("CRO") is None
        assert seniority_rank("CPO") is None
        assert seniority_rank("CDO") is None

    def test_promotion_from_vp_into_named_c_suite_role_is_still_detected(
        self,
    ) -> None:
        assert seniority_rank("Chief Data Officer") > seniority_rank(  # type: ignore[operator]
            "Vice President"
        )
