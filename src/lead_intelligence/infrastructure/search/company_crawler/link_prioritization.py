"""Link scoring and exclusion for CompanyCrawlerProvider: given a page's
outbound links, decide which are worth crawling and in what order.

WHY THIS IS A SIBLING TO company_website/page_discovery.py, NOT A REUSE
OF IT:
That module already does near-identical keyword-based link scoring for
CompanyWebsiteProvider — reusing it directly was considered, but this
provider needs a materially different keyword set (adds "press"/"news",
per this task's own requirement) and an explicit exclusion list
page_discovery.py has no equivalent for. Changing page_discovery.py's own
keyword list to satisfy this would silently change CompanyWebsiteProvider's
unrelated behavior — out of scope for "replace BrowserSearchProvider,"
which never mentions CompanyWebsiteProvider. Same deterministic,
keyword-based, no-AI approach; a second, purpose-built copy rather than
smuggling a behavior change into a different provider's module.

WHY KEYWORD-BASED, NOT AI-BASED:
Same reasoning as page_discovery.py's own docstring: a link whose path or
visible text mentions "leadership," "press," "team," etc. is a strong,
fully-explainable signal — the deterministic floor this task's "No AI. No
LLM." requirement calls for.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

#: Substrings checked against a link's path and visible text — every
#: match counts equally toward that link's score (see `score_link`).
PRIORITY_KEYWORDS: tuple[str, ...] = (
    "leadership",
    "management",
    "executive",
    "executives",
    "board",
    "about",
    "team",
    "people",
    "press",
    "news",
)

#: Substrings that unconditionally disqualify a link, regardless of any
#: priority-keyword match — login walls, legal boilerplate, and product
#: marketing pages never lead to executive information.
_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "login",
    "log-in",
    "signin",
    "sign-in",
    "privacy",
    "product",
)

#: A "careers" link is not excluded outright (a company's own careers
#: overview page is harmless to visit, if unlikely to score), but a
#: *paginated* careers listing is — large in volume, never leads to
#: executive information, and would otherwise dominate a crawl budget.
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
    detection — "https://acme.com/team" and "https://acme.com/team#bio"
    and "https://acme.com/team/" are the same page for crawling purposes.
    """

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
            restricts candidates to the same domain (this provider never
            follows a link off the company's own site).
        already_seen: Normalized URLs (see `normalize_url`) to skip —
            mutated by the caller between calls, not by this function.
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
