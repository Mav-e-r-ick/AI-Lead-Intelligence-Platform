"""Tests for the keyword-based title seniority ranking."""

from __future__ import annotations

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
