"""Unit tests for application/search/confidence.py's score_confidence."""

from __future__ import annotations

from lead_intelligence.application.search.confidence import (
    DEFAULT_CONFIDENCE,
    score_confidence,
)


def test_company_crawler_scores_1_00() -> None:
    assert score_confidence("https://acme.com/leadership", "company_crawler") == 1.00


def test_linkedin_domain_scores_0_98_regardless_of_finding_provider() -> None:
    assert (
        score_confidence("https://www.linkedin.com/in/ada-lovelace", "google_web_search")
        == 0.98
    )
    assert (
        score_confidence("https://linkedin.com/in/ada-lovelace", "linkedin_search") == 0.98
    )


def test_press_release_provider_scores_0_95_on_an_unrecognized_domain() -> None:
    assert score_confidence("https://acme.com/press/release-1", "press_release") == 0.95


def test_reuters_and_bloomberg_score_0_94_regardless_of_finding_provider() -> None:
    assert score_confidence("https://www.reuters.com/article/x", "news_search") == 0.94
    assert score_confidence("https://bloomberg.com/news/x", "google_web_search") == 0.94


def test_businesswire_prnewswire_globenewswire_yahoo_finance_score_0_92() -> None:
    for url in (
        "https://www.businesswire.com/news/home/x",
        "https://www.prnewswire.com/news-releases/x",
        "https://www.globenewswire.com/news-release/x",
        "https://finance.yahoo.com/news/x",
    ):
        assert score_confidence(url, "news_search") == 0.92


def test_google_web_search_scores_0_80_on_an_unrecognized_domain() -> None:
    assert score_confidence("https://example.com/article", "google_web_search") == 0.80


def test_unrecognized_provider_and_domain_scores_default_0_50() -> None:
    assert score_confidence("https://example.com/x", "unknown_provider") == DEFAULT_CONFIDENCE
    assert DEFAULT_CONFIDENCE == 0.50


def test_www_prefix_is_stripped_before_matching() -> None:
    assert score_confidence("https://www.reuters.com/x", "news_search") == 0.94


def test_domain_match_is_case_insensitive() -> None:
    assert score_confidence("https://REUTERS.com/x", "news_search") == 0.94
