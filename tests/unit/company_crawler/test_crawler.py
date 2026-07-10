"""Unit tests for crawl_company_site, using a fake Playwright Browser/Page
(fixtures.py) — no test here launches a real browser or touches the real
network."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.search.company_crawler.crawler import (
    HomepageUnreachable,
    crawl_company_site,
)
from tests.unit.company_crawler.fixtures import FakeBrowser, build_settings

_HOMEPAGE = """
<html><head><title>Acme Corp</title></head><body>
  <a href="/leadership">Leadership</a>
  <a href="/contact">Contact</a>
  <a href="/careers">Careers</a>
</body></html>
"""

_LEADERSHIP_PAGE = """
<html><head><title>Acme Corp Leadership</title>
<meta name="description" content="Meet our executive team.">
</head><body>
  <p>Ada Lovelace is our CEO.</p>
</body></html>
"""


class TestCrawlCompanySite:
    def test_visits_priority_pages_and_skips_unrelated_ones(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/leadership": _LEADERSHIP_PAGE,
            }
        )
        settings = build_settings()

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        urls = [r.url for r in results]
        assert "https://acme.com/leadership" in urls
        assert "https://acme.com/contact" not in urls
        assert "https://acme.com/careers" not in urls  # scores 0, not excluded, not visited

    def test_homepage_itself_is_never_a_result(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/leadership": _LEADERSHIP_PAGE,
            }
        )
        settings = build_settings()

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        assert all(r.url != "https://acme.com/" for r in results)

    def test_result_uses_page_title_and_meta_description(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/leadership": _LEADERSHIP_PAGE,
            }
        )
        settings = build_settings()

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        leadership_result = next(r for r in results if r.url == "https://acme.com/leadership")
        assert leadership_result.title == "Acme Corp Leadership"
        assert leadership_result.snippet == "Meet our executive team."
        assert leadership_result.source == "company_crawler"
        assert leadership_result.rank == 1

    def test_unreachable_homepage_raises_homepage_unreachable(self) -> None:
        """Distinct from a successful crawl finding zero priority pages —
        see HomepageUnreachable's own docstring for why this must not
        just silently return an empty tuple."""

        browser = FakeBrowser(pages={"https://acme.com/": RuntimeError("boom")})
        settings = build_settings(max_retries=0)

        with pytest.raises(HomepageUnreachable):
            crawl_company_site(
                browser,
                "https://acme.com/",
                settings,
                source="company_crawler",
                sleep_fn=lambda seconds: None,
            )

    def test_homepage_loading_but_no_priority_links_yields_empty_tuple_not_raise(
        self,
    ) -> None:
        no_links_homepage = "<html><head><title>Acme</title></head><body>text</body></html>"
        browser = FakeBrowser(pages={"https://acme.com/": no_links_homepage})
        settings = build_settings()

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        assert results == ()

    def test_respects_max_pages_budget(self) -> None:
        homepage = """
        <html><body>
          <a href="/leadership">Leadership</a>
          <a href="/management">Management</a>
          <a href="/board">Board</a>
        </body></html>
        """
        page_html = "<html><head><title>Page</title></head><body>text</body></html>"
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/leadership": page_html,
                "https://acme.com/management": page_html,
                "https://acme.com/board": page_html,
            }
        )
        settings = build_settings(max_pages=2)

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        assert len(results) == 2

    def test_respects_max_results_cap_independent_of_max_pages(self) -> None:
        homepage = """
        <html><body>
          <a href="/leadership">Leadership</a>
          <a href="/management">Management</a>
        </body></html>
        """
        page_html = "<html><head><title>Page</title></head><body>text</body></html>"
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/leadership": page_html,
                "https://acme.com/management": page_html,
            }
        )
        settings = build_settings(max_pages=5, max_results=1)

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        assert len(results) == 1

    def test_robots_allow_callback_is_checked_per_candidate(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/leadership": _LEADERSHIP_PAGE,
            }
        )
        settings = build_settings()
        disallowed = {"https://acme.com/leadership"}

        results = crawl_company_site(
            browser,
            "https://acme.com/",
            settings,
            source="company_crawler",
            robots_allow=lambda url: url not in disallowed,
        )

        assert results == ()

    def test_finds_pages_one_hop_deeper_than_the_homepage(self) -> None:
        homepage = '<html><body><a href="/about">About</a></body></html>'
        about_page = """
        <html><head><title>About Acme</title></head><body>
          <a href="/about/team">Team</a>
        </body></html>
        """
        team_page = "<html><head><title>Our Team</title></head><body>text</body></html>"
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/about": about_page,
                "https://acme.com/about/team": team_page,
            }
        )
        settings = build_settings(max_depth=2)

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        urls = [r.url for r in results]
        assert "https://acme.com/about" in urls
        assert "https://acme.com/about/team" in urls

    def test_max_depth_one_does_not_follow_links_past_the_first_hop(self) -> None:
        homepage = '<html><body><a href="/about">About</a></body></html>'
        about_page = """
        <html><head><title>About Acme</title></head><body>
          <a href="/about/team">Team</a>
        </body></html>
        """
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/about": about_page,
            }
        )
        settings = build_settings(max_depth=1)

        results = crawl_company_site(
            browser, "https://acme.com/", settings, source="company_crawler"
        )

        urls = [r.url for r in results]
        assert "https://acme.com/about" in urls
        assert "https://acme.com/about/team" not in urls
