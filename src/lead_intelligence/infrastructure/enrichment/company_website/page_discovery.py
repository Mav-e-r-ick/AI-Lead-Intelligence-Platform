"""Leadership/about/team page discovery: given a company's homepage HTML,
find the links most likely to lead to a page listing its executives.

WHY THIS IS KEYWORD-BASED, NOT AI-BASED:
This task's scope explicitly excludes AI. A link whose path or visible
text mentions "leadership," "about," "team," etc. is a strong, simple,
fully-explainable signal a real crawler can rely on without any model
call — the same kind of deterministic heuristic already used throughout
this platform's other engines.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

#: Substrings checked against a link's path and visible text. Order does
#: not affect scoring — every match counts equally; see `_score`.
LEADERSHIP_KEYWORDS: tuple[str, ...] = (
    "leadership",
    "about-us",
    "about",
    "our-team",
    "team",
    "management",
    "executive-team",
    "executives",
    "who-we-are",
    "board-of-directors",
    "board",
    "meet-the-team",
    "people",
    "staff",
)


def discover_leadership_pages(
    homepage_html: str, base_url: str, limit: int
) -> tuple[str, ...]:
    """Every same-domain link on `homepage_html` that plausibly leads to a
    leadership/about/team page, most-plausible first, capped at `limit`.

    Args:
        homepage_html: The homepage's raw HTML.
        base_url: The homepage's URL, used to resolve relative links and
            to restrict candidates to the same domain (this provider never
            follows a link off the company's own site).
        limit: Maximum number of candidate URLs to return.

    Returns:
        Absolute URLs, ranked by keyword-match strength (most matches
        first) and then alphabetically for a stable, deterministic order
        when scores tie — never in DOM/iteration order, which carries no
        meaningful signal here.
    """

    soup = BeautifulSoup(homepage_html, "html.parser")
    base_netloc = urlparse(base_url).netloc

    scored: dict[str, int] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        absolute = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.netloc and parsed.netloc != base_netloc:
            continue  # stay on the company's own site

        score = _score(parsed.path, anchor.get_text(" ", strip=True))
        if score > 0:
            scored[absolute] = max(scored.get(absolute, 0), score)

    ordered = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    return tuple(url for url, _ in ordered[:limit])


def _score(path: str, link_text: str) -> int:
    haystack = f"{path} {link_text}".lower()
    return sum(1 for keyword in LEADERSHIP_KEYWORDS if keyword in haystack)
