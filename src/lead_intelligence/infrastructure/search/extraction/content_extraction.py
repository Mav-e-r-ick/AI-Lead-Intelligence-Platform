"""Turns one fetched HTML page into plain PageContent: title, visible
text, and (when the page declares one) a publication date.

This is the "Content Extractor" stage from the approved Search Layer RFC.

WHY "VISIBLE TEXT" MEANS "EVERYTHING EXCEPT SCRIPT/STYLE/TEMPLATE MARKUP,
WHITESPACE-COLLAPSED" AND NOTHING SMARTER:
Boilerplate removal (navigation menus, cookie banners, footers) is a
genuinely hard, heuristic-laden problem — readability-style content
scoring is its own project, and a wrong guess silently deletes evidence.
Version 1 takes the honest floor: strip what is *definitionally* not
visible text (scripts, styles, templates, head metadata), collapse
whitespace, and truncate to a configured bound. The rule-based fact
patterns downstream are anchored phrasings ("X was appointed Y of Z"), so
surrounding boilerplate costs scan time but not correctness.

WHY published_at IS A RAW STRING, NEVER A PARSED datetime:
Same reasoning as infrastructure/enrichment/google_search/extraction.py's
own docstring, verbatim: pages declare dates in whatever format their
author chose; parsing every real-world format is its own error-prone
undertaking. This module reports whatever raw value the page's own
`<meta>` tags declare, or None — never a guessed or reformatted date.
"""

from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

#: Tags whose contents are never visible page text.
_INVISIBLE_TAGS = ("script", "style", "noscript", "template")

#: <meta> name/property values, checked in order, that commonly carry a
#: page's publication or last-updated date. The same deliberately
#: non-exhaustive list the Google Search provider already uses for its
#: `pagemap.metatags` equivalent — one shared vocabulary of "where dates
#: live," not two drifting ones.
_PUBLISHED_TIME_META_KEYS: tuple[str, ...] = (
    "article:published_time",
    "og:article:published_time",
    "datepublished",
    "date",
    "og:updated_time",
)


@dataclass(frozen=True)
class PageContent:
    """One fetched page, reduced to what the fact patterns can use.

    Attributes:
        title: The page's <title> text (falling back to `og:title` when
            the page has no <title>), or "" if neither exists.
        visible_text: The page's visible text, whitespace-collapsed and
            truncated to the configured bound.
        published_at: A raw, unparsed publication/last-updated date string
            from the page's own <meta> tags, or None if unavailable.
    """

    title: str
    visible_text: str
    published_at: str | None


def extract_page_content(html: str, max_text_chars: int) -> PageContent:
    """Reduce one HTML document to PageContent.

    Args:
        html: The fetched page's HTML text.
        max_text_chars: Upper bound on `visible_text`'s length.

    Returns:
        A PageContent. Never raises for malformed HTML — BeautifulSoup's
        parser is tolerant by design, and an empty/garbage document simply
        yields empty fields.
    """

    soup = BeautifulSoup(html, "html.parser")

    published_at = _extract_published_at(soup)

    for tag_name in _INVISIBLE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    title = ""
    if soup.title is not None and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title is not None:
            title = str(og_title.get("content") or "").strip()

    body = soup.body if soup.body is not None else soup
    visible_text = " ".join(body.get_text(separator=" ").split())[:max_text_chars]

    return PageContent(
        title=title, visible_text=visible_text, published_at=published_at
    )


def _extract_published_at(soup: BeautifulSoup) -> str | None:
    for key in _PUBLISHED_TIME_META_KEYS:
        for attribute in ("property", "name"):
            tag = soup.find("meta", attrs={attribute: key})
            if tag is not None:
                value = str(tag.get("content") or "").strip()
                if value:
                    return value
    return None
