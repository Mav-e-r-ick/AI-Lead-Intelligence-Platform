"""Unit tests for crawl_company_press_pages, using a fake Playwright
Browser/Page (fixtures.py) — no test here launches a real browser or
touches the real network."""

from __future__ import annotations

import pytest

from lead_intelligence.infrastructure.search.press_release.crawler import (
    HomepageUnreachable,
    crawl_company_press_pages,
)
from tests.unit.press_release.fixtures import FakeBrowser, build_settings

_HOMEPAGE = """
<html><head><title>Acme Corp</title></head><body>
  <a href="/press">Press</a>
  <a href="/contact">Contact</a>
  <a href="/careers">Careers</a>
</body></html>
"""

_PRESS_PAGE = """
<html><head><title>Acme Corp Press Releases</title>
<meta name="description" content="Acme names new CEO.">
</head><body>
  <p>Ada Lovelace has been named CEO.</p>
</body></html>
"""


class TestCrawlCompanyPressPages:
    def test_visits_priority_pages_and_skips_unrelated_ones(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/press": _PRESS_PAGE,
            }
        )
        settings = build_settings()

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        urls = [r.url for r in results]
        assert "https://acme.com/press" in urls
        assert "https://acme.com/contact" not in urls
        assert "https://acme.com/careers" not in urls

    def test_homepage_itself_is_never_a_result(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/press": _PRESS_PAGE,
            }
        )
        settings = build_settings()

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        assert all(r.url != "https://acme.com/" for r in results)

    def test_result_uses_page_title_and_meta_description(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/press": _PRESS_PAGE,
            }
        )
        settings = build_settings()

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        press_result = next(r for r in results if r.url == "https://acme.com/press")
        assert press_result.title == "Acme Corp Press Releases"
        assert press_result.snippet == "Acme names new CEO."
        assert press_result.source == "press_release"
        assert press_result.rank == 1

    def test_unreachable_homepage_raises_homepage_unreachable(self) -> None:
        browser = FakeBrowser(pages={"https://acme.com/": RuntimeError("boom")})
        settings = build_settings(max_retries=0)

        with pytest.raises(HomepageUnreachable):
            crawl_company_press_pages(
                browser,
                "https://acme.com/",
                settings,
                source="press_release",
                sleep_fn=lambda seconds: None,
            )

    def test_homepage_loading_but_no_priority_links_yields_empty_tuple_not_raise(
        self,
    ) -> None:
        no_links_homepage = "<html><head><title>Acme</title></head><body>text</body></html>"
        browser = FakeBrowser(pages={"https://acme.com/": no_links_homepage})
        settings = build_settings()

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        assert results == ()

    def test_respects_max_pages_budget(self) -> None:
        homepage = """
        <html><body>
          <a href="/press">Press</a>
          <a href="/newsroom">Newsroom</a>
          <a href="/media">Media</a>
        </body></html>
        """
        page_html = "<html><head><title>Page</title></head><body>text</body></html>"
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/press": page_html,
                "https://acme.com/newsroom": page_html,
                "https://acme.com/media": page_html,
            }
        )
        settings = build_settings(max_pages=2)

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        assert len(results) == 2

    def test_respects_max_results_cap_independent_of_max_pages(self) -> None:
        homepage = """
        <html><body>
          <a href="/press">Press</a>
          <a href="/newsroom">Newsroom</a>
        </body></html>
        """
        page_html = "<html><head><title>Page</title></head><body>text</body></html>"
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/press": page_html,
                "https://acme.com/newsroom": page_html,
            }
        )
        settings = build_settings(max_pages=5, max_results=1)

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        assert len(results) == 1

    def test_robots_allow_callback_is_checked_per_candidate(self) -> None:
        browser = FakeBrowser(
            pages={
                "https://acme.com/": _HOMEPAGE,
                "https://acme.com/press": _PRESS_PAGE,
            }
        )
        settings = build_settings()
        disallowed = {"https://acme.com/press"}

        results = crawl_company_press_pages(
            browser,
            "https://acme.com/",
            settings,
            source="press_release",
            robots_allow=lambda url: url not in disallowed,
        )

        assert results == ()

    def test_finds_pages_one_hop_deeper_than_the_homepage(self) -> None:
        homepage = '<html><body><a href="/newsroom">Newsroom</a></body></html>'
        newsroom_page = """
        <html><head><title>Newsroom</title></head><body>
          <a href="/newsroom/2024-release">2024 Release</a>
        </body></html>
        """
        release_page = (
            "<html><head><title>2024 Press Release</title></head><body>text</body></html>"
        )
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/newsroom": newsroom_page,
                "https://acme.com/newsroom/2024-release": release_page,
            }
        )
        settings = build_settings(max_depth=2)

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        urls = [r.url for r in results]
        assert "https://acme.com/newsroom" in urls
        assert "https://acme.com/newsroom/2024-release" in urls

    def test_max_depth_one_does_not_follow_links_past_the_first_hop(self) -> None:
        homepage = '<html><body><a href="/newsroom">Newsroom</a></body></html>'
        newsroom_page = """
        <html><head><title>Newsroom</title></head><body>
          <a href="/newsroom/2024-release">2024 Release</a>
        </body></html>
        """
        browser = FakeBrowser(
            pages={
                "https://acme.com/": homepage,
                "https://acme.com/newsroom": newsroom_page,
            }
        )
        settings = build_settings(max_depth=1)

        results = crawl_company_press_pages(
            browser, "https://acme.com/", settings, source="press_release"
        )

        urls = [r.url for r in results]
        assert "https://acme.com/newsroom" in urls
        assert "https://acme.com/newsroom/2024-release" not in urls
