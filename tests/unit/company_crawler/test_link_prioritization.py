"""Unit tests for link_prioritization.py's scoring, exclusion, and
duplicate-detection rules."""

from __future__ import annotations

from lead_intelligence.infrastructure.search.company_crawler.link_prioritization import (
    extract_priority_links,
    is_excluded,
    normalize_url,
    score_link,
)


class TestScoreLink:
    def test_leadership_keyword_scores_positive(self) -> None:
        assert score_link("/leadership", "Our Leadership") > 0

    def test_press_keyword_scores_positive(self) -> None:
        assert score_link("/press", "Press") > 0

    def test_news_keyword_scores_positive(self) -> None:
        assert score_link("/newsroom", "News") > 0

    def test_multiple_keyword_matches_score_higher(self) -> None:
        single = score_link("/about", "About")
        multiple = score_link("/about/leadership-team", "About Our Leadership Team")

        assert multiple > single

    def test_unrelated_link_scores_zero(self) -> None:
        assert score_link("/contact-us", "Contact Us") == 0


class TestIsExcluded:
    def test_login_link_is_excluded(self) -> None:
        assert is_excluded("/login", "Log In")

    def test_privacy_link_is_excluded(self) -> None:
        assert is_excluded("/privacy-policy", "Privacy Policy")

    def test_products_link_is_excluded(self) -> None:
        assert is_excluded("/products", "Our Products")

    def test_paginated_careers_link_is_excluded(self) -> None:
        assert is_excluded("/careers/page/2", "Careers")
        assert is_excluded("/careers?page=3", "Careers")

    def test_plain_careers_link_is_not_excluded(self) -> None:
        assert not is_excluded("/careers", "Careers")

    def test_leadership_link_is_not_excluded(self) -> None:
        assert not is_excluded("/leadership", "Leadership")


class TestNormalizeUrl:
    def test_strips_fragment(self) -> None:
        assert normalize_url("https://acme.com/team#bio") == "https://acme.com/team"

    def test_strips_trailing_slash(self) -> None:
        assert normalize_url("https://acme.com/team/") == "https://acme.com/team"

    def test_equivalent_urls_normalize_identically(self) -> None:
        assert normalize_url("https://acme.com/team/") == normalize_url(
            "https://acme.com/team#bio"
        )


class TestExtractPriorityLinks:
    def test_finds_priority_links_on_the_page(self) -> None:
        html = """
        <html><body>
          <a href="/leadership">Leadership</a>
          <a href="/contact">Contact</a>
          <a href="/press">Press Releases</a>
        </body></html>
        """

        results = extract_priority_links(html, "https://acme.com/", set())

        urls = [url for url, _, _ in results]
        assert "https://acme.com/leadership" in urls
        assert "https://acme.com/press" in urls
        assert "https://acme.com/contact" not in urls

    def test_orders_by_score_descending(self) -> None:
        html = """
        <html><body>
          <a href="/about">About</a>
          <a href="/about/leadership-team">About Leadership Team</a>
        </body></html>
        """

        results = extract_priority_links(html, "https://acme.com/", set())

        assert results[0][0] == "https://acme.com/about/leadership-team"

    def test_excludes_off_domain_links(self) -> None:
        html = '<html><body><a href="https://other.com/leadership">Leadership</a></body></html>'

        results = extract_priority_links(html, "https://acme.com/", set())

        assert results == []

    def test_excludes_already_seen_urls(self) -> None:
        html = '<html><body><a href="/leadership">Leadership</a></body></html>'

        results = extract_priority_links(
            html, "https://acme.com/", {"https://acme.com/leadership"}
        )

        assert results == []

    def test_excludes_javascript_and_fragment_only_links(self) -> None:
        html = """
        <html><body>
          <a href="javascript:void(0)">Leadership</a>
          <a href="#leadership">Leadership</a>
        </body></html>
        """

        results = extract_priority_links(html, "https://acme.com/", set())

        assert results == []

    def test_excludes_login_and_paginated_careers_even_with_a_priority_keyword(
        self,
    ) -> None:
        html = """
        <html><body>
          <a href="/login?next=/leadership">Leadership Login</a>
          <a href="/careers/page/2">Careers Team Page 2</a>
        </body></html>
        """

        results = extract_priority_links(html, "https://acme.com/", set())

        assert results == []

    def test_relative_links_resolved_against_base_url(self) -> None:
        html = '<html><body><a href="team">Team</a></body></html>'

        results = extract_priority_links(
            html, "https://acme.com/about/", set()
        )

        assert results[0][0] == "https://acme.com/about/team"

    def test_deduplicates_the_same_link_appearing_twice(self) -> None:
        html = """
        <html><body>
          <a href="/leadership">Leadership</a>
          <a href="/leadership">Our Leadership</a>
        </body></html>
        """

        results = extract_priority_links(html, "https://acme.com/", set())

        assert len(results) == 1
