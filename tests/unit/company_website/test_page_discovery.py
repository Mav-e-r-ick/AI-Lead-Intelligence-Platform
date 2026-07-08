"""Unit tests for discover_leadership_pages."""

from __future__ import annotations

from lead_intelligence.infrastructure.enrichment.company_website.page_discovery import (
    discover_leadership_pages,
)


def test_finds_leadership_style_links() -> None:
    html = """
    <html><body>
      <a href="/products">Products</a>
      <a href="/leadership">Leadership</a>
      <a href="/contact">Contact</a>
    </body></html>
    """

    pages = discover_leadership_pages(html, "https://acme.com", limit=5)

    assert pages == ("https://acme.com/leadership",)


def test_excludes_off_domain_links() -> None:
    html = """
    <html><body>
      <a href="https://external.com/leadership">Their leadership</a>
      <a href="/about">About us</a>
    </body></html>
    """

    pages = discover_leadership_pages(html, "https://acme.com", limit=5)

    assert pages == ("https://acme.com/about",)


def test_resolves_relative_links_against_base_url() -> None:
    html = '<html><body><a href="team">Our Team</a></body></html>'

    pages = discover_leadership_pages(html, "https://acme.com/company/", limit=5)

    assert pages == ("https://acme.com/company/team",)


def test_ignores_fragment_and_javascript_links() -> None:
    html = """
    <html><body>
      <a href="#team">Jump to team</a>
      <a href="javascript:void(0)">Team</a>
    </body></html>
    """

    pages = discover_leadership_pages(html, "https://acme.com", limit=5)

    assert pages == ()


def test_orders_by_keyword_match_strength_then_alphabetically() -> None:
    html = """
    <html><body>
      <a href="/about">About</a>
      <a href="/about-us/leadership-team">Leadership Team</a>
      <a href="/zzz-team">Team</a>
    </body></html>
    """

    pages = discover_leadership_pages(html, "https://acme.com", limit=5)

    assert pages[0] == "https://acme.com/about-us/leadership-team"
    assert set(pages) == {
        "https://acme.com/about",
        "https://acme.com/about-us/leadership-team",
        "https://acme.com/zzz-team",
    }


def test_respects_limit() -> None:
    html = """
    <html><body>
      <a href="/about">About</a>
      <a href="/team">Team</a>
      <a href="/leadership">Leadership</a>
    </body></html>
    """

    pages = discover_leadership_pages(html, "https://acme.com", limit=2)

    assert len(pages) == 2


def test_duplicate_links_are_deduplicated() -> None:
    html = """
    <html><body>
      <a href="/leadership">Leadership</a>
      <a href="/leadership">Leadership (footer)</a>
    </body></html>
    """

    pages = discover_leadership_pages(html, "https://acme.com", limit=5)

    assert pages == ("https://acme.com/leadership",)


def test_no_matching_links_returns_empty() -> None:
    html = '<html><body><a href="/products">Products</a></body></html>'

    pages = discover_leadership_pages(html, "https://acme.com", limit=5)

    assert pages == ()
