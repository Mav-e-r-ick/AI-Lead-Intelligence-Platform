"""Link scoring and exclusion for PressReleaseProvider: given a page's
outbound links, decide which are worth crawling and in what order.

WHY THIS IS A SIBLING TO company_crawler/link_prioritization.py, NOT A
REUSE OF IT:
Same reasoning as that module's own docstring for why it doesn't reuse
`company_website/page_discovery.py`: this provider needs a materially
different, narrower keyword set — press/newsroom/media/investor-relations/
announcements specifically, per this task's own specification, not the
broader leadership/management/board/about/team/people/press/news set
`company_crawler` already covers. Changing `company_crawler`'s own
keyword list to also emphasize press/newsroom pages would silently change
CompanyCrawlerProvider's own behavior — explicitly out of scope (this
task says "Keep the existing implementation" for CompanyCrawlerProvider).
Same deterministic, keyword-based, no-AI approach; a second, purpose-built
copy rather than a shared, more general module.

WHY KEYWORD-BASED, NOT AI-BASED:
Same reasoning as every other link-prioritization module in this
codebase: a link whose path or visible text mentions "press,"
"newsroom," "investor-relations," etc. is a strong, fully-explainable
signal — the deterministic floor this task's "No AI. No LLM." requirement
calls for.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

#: Substrings checked against a link's path and visible text — every
#: match counts equally toward that link's score (see `score_link`).
#: Deliberately narrower than `company_crawler`'s own list — see module
#: docstring.
PRIORITY_KEYWORDS: tuple[str, ...] = (
    "press",
    "newsroom",
    "news-room",
    "media",
    "investor",
    "investors",
    "investor-relations",
    "announcement",
    "announcements",
    "release",
    "releases",
)

#: Substrings that unconditionally disqualify a link, regardless of any
#: priority-keyword match — same rationale as `company_crawler`'s own
#: exclusion list.
_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "login",
    "log-in",
    "signin",
    "sign-in",
    "privacy",
    "product",
)

#: A "careers" link is not excluded outright, but a *paginated* careers
#: listing is — same reasoning as `company_crawler`'s own module.
_CAREERS_MARKER = "career"
_PAGINATION_PATTERN = re.compile(r"(?:[/?]page[/=]?\d+|[/?]p=\d+|/\d+/?$)")


def score_link(path: str, link_text: str) -> int:
    """How many `PRIORITY_KEYWORDS` appear in `path`/`link_text` — 0 means
    "not a priority candidate," not "excluded" (see `is_excluded`)."""

    haystack = f"{path} {link_text}".lower()
    return sum(1 for keyword in PRIORITY_KEYWORDS if keyword in haystack)


def is_excluded(path: str, link_text: str) -> bool:
    """Whether this link should never be crawled, regardless of score."""

    haystack = f"{path} {link_text}".lower()
    if any(keyword in haystack for keyword in _EXCLUDE_KEYWORDS):
        return True
    if _CAREERS_MARKER in haystack and _PAGINATION_PATTERN.search(haystack):
        return True
    return False


def normalize_url(url: str) -> str:
    """`url` with its fragment and trailing slash stripped, for duplicate
    detection."""

    without_fragment = url.split("#", 1)[0]
    return without_fragment[:-1] if without_fragment.endswith("/") else without_fragment


def extract_priority_links(
    html: str, base_url: str, already_seen: set[str]
) -> list[tuple[str, str, int]]:
    """Every same-domain, non-excluded, not-already-seen link on `html`
    that scores > 0, as (absolute_url, link_text, score) — most-plausible
    first, then alphabetically for a stable, deterministic tie-break.

    Args:
        html: The page's raw HTML.
        base_url: The page's own URL — resolves relative links and
            restricts candidates to the same domain.
        already_seen: Normalized URLs (see `normalize_url`) to skip.
    """

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    base_netloc = urlparse(base_url).netloc

    candidates: dict[str, tuple[str, int]] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc and parsed.netloc != base_netloc:
            continue  # stay on the company's own site
        if parsed.scheme not in ("http", "https"):
            continue

        normalized = normalize_url(absolute)
        if normalized in already_seen:
            continue

        link_text = anchor.get_text(" ", strip=True)
        if is_excluded(parsed.path, link_text):
            continue

        score = score_link(parsed.path, link_text)
        if score <= 0:
            continue

        existing = candidates.get(normalized)
        if existing is None or score > existing[1]:
            candidates[normalized] = (link_text, score)

    ordered = sorted(
        candidates.items(), key=lambda item: (-item[1][1], item[0])
    )
    return [(url, text, score) for url, (text, score) in ordered]
