"""Unit tests for content_extraction.extract_page_content."""

from __future__ import annotations

from lead_intelligence.infrastructure.search.extraction.content_extraction import (
    extract_page_content,
)

_MAX = 20_000


def test_extracts_title_from_title_tag() -> None:
    html = "<html><head><title>  Ada named CTO  </title></head><body>x</body></html>"

    content = extract_page_content(html, _MAX)

    assert content.title == "Ada named CTO"


def test_falls_back_to_og_title_when_title_tag_is_missing() -> None:
    html = (
        '<html><head><meta property="og:title" content="OG Title"></head>'
        "<body>x</body></html>"
    )

    content = extract_page_content(html, _MAX)

    assert content.title == "OG Title"


def test_missing_title_yields_empty_string() -> None:
    content = extract_page_content("<html><body>x</body></html>", _MAX)

    assert content.title == ""


def test_visible_text_excludes_script_style_noscript_template() -> None:
    html = """
    <html><body>
      <p>Visible sentence.</p>
      <script>var invisible = 1;</script>
      <style>.invisible { color: red; }</style>
      <noscript>Invisible fallback.</noscript>
      <template><p>Invisible template.</p></template>
    </body></html>
    """

    content = extract_page_content(html, _MAX)

    assert "Visible sentence." in content.visible_text
    assert "invisible" not in content.visible_text
    assert "Invisible" not in content.visible_text


def test_visible_text_collapses_whitespace() -> None:
    html = "<html><body><p>One\n\n   two\t three</p></body></html>"

    content = extract_page_content(html, _MAX)

    assert content.visible_text == "One two three"


def test_visible_text_is_truncated_to_max_text_chars() -> None:
    html = f"<html><body><p>{'a' * 100}</p></body></html>"

    content = extract_page_content(html, 10)

    assert content.visible_text == "a" * 10


def test_published_at_from_meta_property() -> None:
    html = (
        '<html><head><meta property="article:published_time" '
        'content="2024-05-30T09:00:00Z"></head><body>x</body></html>'
    )

    content = extract_page_content(html, _MAX)

    assert content.published_at == "2024-05-30T09:00:00Z"


def test_published_at_from_meta_name() -> None:
    html = (
        '<html><head><meta name="date" content="May 30, 2024"></head>'
        "<body>x</body></html>"
    )

    content = extract_page_content(html, _MAX)

    assert content.published_at == "May 30, 2024"


def test_published_at_is_reported_verbatim_never_parsed() -> None:
    html = (
        '<html><head><meta name="date" content="  30/05/2024 ish  "></head>'
        "<body>x</body></html>"
    )

    content = extract_page_content(html, _MAX)

    assert content.published_at == "30/05/2024 ish"


def test_missing_published_at_yields_none() -> None:
    content = extract_page_content("<html><body>x</body></html>", _MAX)

    assert content.published_at is None


def test_malformed_html_does_not_raise() -> None:
    content = extract_page_content("<div><p>broken<span></div>", _MAX)

    assert "broken" in content.visible_text
