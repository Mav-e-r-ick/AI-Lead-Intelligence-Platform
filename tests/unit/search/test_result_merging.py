"""Unit tests for application/search/result_merging.py's dedup_and_rank."""

from __future__ import annotations

from lead_intelligence.application.dto.search_models import SearchResult
from lead_intelligence.application.search.result_merging import dedup_and_rank


def _result(
    url: str, source: str, confidence: float, rank: int = 1, title: str = "t"
) -> SearchResult:
    return SearchResult(
        title=title, url=url, snippet="s", source=source, rank=rank, confidence=confidence
    )


def test_no_duplicates_returns_every_result() -> None:
    a = _result("https://a.example/x", "google_web_search", 0.80)
    b = _result("https://b.example/y", "news_search", 0.94)

    merged = dedup_and_rank([a, b])

    assert set(merged) == {a, b}


def test_same_url_from_two_providers_collapses_to_one() -> None:
    lower_confidence = _result("https://reuters.com/x", "google_web_search", 0.80)
    higher_confidence = _result("https://reuters.com/x", "news_search", 0.94)

    merged = dedup_and_rank([lower_confidence, higher_confidence])

    assert len(merged) == 1
    assert merged[0].source == "news_search"
    assert merged[0].confidence == 0.94


def test_survivor_of_a_duplicate_is_always_the_highest_confidence_copy_regardless_of_order() -> (
    None
):
    lower_confidence = _result("https://reuters.com/x", "google_web_search", 0.80)
    higher_confidence = _result("https://reuters.com/x", "news_search", 0.94)

    merged_low_first = dedup_and_rank([lower_confidence, higher_confidence])
    merged_high_first = dedup_and_rank([higher_confidence, lower_confidence])

    assert merged_low_first[0].source == "news_search"
    assert merged_high_first[0].source == "news_search"


def test_results_are_ranked_by_confidence_descending() -> None:
    low = _result("https://a.example", "google_web_search", 0.80)
    high = _result("https://b.example", "company_crawler", 1.00)
    mid = _result("https://c.example", "press_release", 0.95)

    merged = dedup_and_rank([low, high, mid])

    assert [r.source for r in merged] == ["company_crawler", "press_release", "google_web_search"]


def test_trailing_slash_and_fragment_are_treated_as_the_same_url() -> None:
    a = _result("https://acme.com/team", "company_crawler", 1.00)
    b = _result("https://acme.com/team/#bio", "press_release", 0.95)

    merged = dedup_and_rank([a, b])

    assert len(merged) == 1


def test_host_case_is_ignored_for_deduplication() -> None:
    a = _result("https://Acme.com/team", "company_crawler", 1.00)
    b = _result("https://acme.com/team", "press_release", 0.95)

    merged = dedup_and_rank([a, b])

    assert len(merged) == 1


def test_different_paths_on_the_same_host_are_not_duplicates() -> None:
    a = _result("https://acme.com/team", "company_crawler", 1.00)
    b = _result("https://acme.com/press", "press_release", 0.95)

    merged = dedup_and_rank([a, b])

    assert len(merged) == 2


def test_tie_break_is_deterministic_by_source_then_rank() -> None:
    a = _result("https://a.example", "news_search", 0.80, rank=2)
    b = _result("https://b.example", "google_web_search", 0.80, rank=1)

    merged = dedup_and_rank([a, b])

    # Same confidence: alphabetical by source ("google_web_search" < "news_search").
    assert [r.source for r in merged] == ["google_web_search", "news_search"]


def test_empty_input_returns_empty_tuple() -> None:
    assert dedup_and_rank([]) == ()


def test_is_deterministic_given_the_same_input_regardless_of_order() -> None:
    a = _result("https://a.example", "news_search", 0.80)
    b = _result("https://b.example", "company_crawler", 1.00)
    c = _result("https://c.example", "press_release", 0.95)

    assert dedup_and_rank([a, b, c]) == dedup_and_rank([c, a, b])
