"""Unit tests for press_release/link_prioritization.py."""

from __future__ import annotations

from lead_intelligence.infrastructure.search.press_release.link_prioritization import (
    extract_priority_links,
    is_excluded,
    normalize_url,
    score_link,
)


class TestScoreLink:
    def test_press_keyword_scores_one(self) -> None:
        assert score_link("/press", "Press") == 1

    def test_multiple_keywords_add_up(self) -> None:
        assert score_link("/press/newsroom", "Press Newsroom") >= 2

    def test_unrelated_link_scores_zero(self) -> None:
        assert score_link("/contact", "Contact us") == 0

    def test_investor_relations_scores(self) -> None:
        assert score_link("/investor-relations", "Investor Relations") >= 1

    def test_leadership_keyword_does_not_score_here(self) -> None:
        # Deliberately narrower than company_crawler's keyword set.
        assert score_link("/leadership", "Leadership") == 0


class TestIsExcluded:
    def test_login_link_is_excluded(self) -> None:
        assert is_excluded("/login", "Log in") is True

    def test_privacy_link_is_excluded(self) -> None:
        assert is_excluded("/privacy-policy", "Privacy") is True

    def test_plain_careers_page_is_not_excluded(self) -> None:
        assert is_excluded("/careers", "Careers") is False

    def test_paginated_careers_listing_is_excluded(self) -> None:
        assert is_excluded("/careers/page/2", "Careers") is True

    def test_press_link_is_not_excluded(self) -> None:
        assert is_excluded("/press", "Press") is False


class TestNormalizeUrl:
    def test_strips_fragment(self) -> None:
        assert normalize_url("https://acme.com/press#top") == "https://acme.com/press"

    def test_strips_trailing_slash(self) -> None:
        assert normalize_url("https://acme.com/press/") == "https://acme.com/press"

    def test_trailing_slash_is_stripped_even_for_the_bare_domain(self) -> None:
        # Matches company_crawler/link_prioritization.py's identical rule:
        # trailing-slash stripping applies unconditionally, including the
        # bare-root case.
        assert normalize_url("https://acme.com/") == "https://acme.com"


class TestExtractPriorityLinks:
    def test_finds_press_and_newsroom_links(self) -> None:
        html = """
        <html><body>
          <a href="/press">Press</a>
          <a href="/newsroom">Newsroom</a>
          <a href="/contact">Contact</a>
        </body></html>
        """

        links = extract_priority_links(html, "https://acme.com/", set())

        urls = [url for url, _, _ in links]
        assert "https://acme.com/press" in urls
        assert "https://acme.com/newsroom" in urls
        assert "https://acme.com/contact" not in urls

    def test_off_domain_links_are_excluded(self) -> None:
        html = '<html><body><a href="https://other.com/press">Press</a></body></html>'

        links = extract_priority_links(html, "https://acme.com/", set())

        assert links == []

    def test_already_seen_links_are_skipped(self) -> None:
        html = '<html><body><a href="/press">Press</a></body></html>'

        links = extract_priority_links(
            html, "https://acme.com/", {"https://acme.com/press"}
        )

        assert links == []

    def test_javascript_and_fragment_only_links_are_skipped(self) -> None:
        html = """
        <html><body>
          <a href="javascript:void(0)">Press</a>
          <a href="#">Newsroom</a>
        </body></html>
        """

        links = extract_priority_links(html, "https://acme.com/", set())

        assert links == []

    def test_relative_links_are_resolved_to_absolute(self) -> None:
        html = '<html><body><a href="press/2024">2024 Press</a></body></html>'

        links = extract_priority_links(html, "https://acme.com/newsroom", set())

        urls = [url for url, _, _ in links]
        assert "https://acme.com/press/2024" in urls

    def test_duplicate_links_are_deduped_keeping_highest_score(self) -> None:
        html = """
        <html><body>
          <a href="/press">Press</a>
          <a href="/press">Press Newsroom</a>
        </body></html>
        """

        links = extract_priority_links(html, "https://acme.com/", set())

        assert len([url for url, _, _ in links if url == "https://acme.com/press"]) == 1

    def test_results_are_sorted_by_score_descending(self) -> None:
        html = """
        <html><body>
          <a href="/press">Press</a>
          <a href="/press/newsroom/media">Press Newsroom Media</a>
        </body></html>
        """

        links = extract_priority_links(html, "https://acme.com/", set())

        scores = [score for _, _, score in links]
        assert scores == sorted(scores, reverse=True)
