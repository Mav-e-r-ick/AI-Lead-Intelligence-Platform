"""crawl_company_site: drives a real (or, in tests, fake) browser
breadth-first through a company's website, prioritized by
link_prioritization.py, producing one SearchResult per successfully
visited priority page.

WHY THE HOMEPAGE ITSELF IS NEVER RETURNED AS A RESULT:
The homepage is the crawl's starting point, used only to discover links —
matching CompanyWebsiteProvider's own precedent (it fetches the homepage
purely to find leadership-page candidates, never treats the homepage
itself as executive-information evidence). A SearchResult here means
"this specific page plausibly has executive information on it," which the
undifferentiated homepage usually doesn't.

WHY BREADTH-FIRST, BOUNDED BY max_depth AND max_pages:
A "Team" or "Press" link often lives one hop deeper than the homepage
(e.g. only linked from the "About" page) — pure homepage-only discovery
(page_discovery.py's own scope) would miss it. Going breadth-first, not
depth-first, means the crawl always exhausts the highest-scoring,
shallowest candidates before spending budget on deeper, lower-confidence
ones. Both bounds exist for the same reason CompanyWebsiteProvider's
`max_leadership_pages` does: keep one crawl's cost and duration bounded
and deterministic, never open-ended.

WHY robots_allow IS A CALLBACK, NOT THIS MODULE'S OWN CONCERN:
Checking robots.txt is a plain HTTP concern (see provider.py), while this
module only knows how to drive the browser — same separation
BrowserSearchProvider's own provider.py/its browser-driving code already
keeps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from loguru import logger

from lead_intelligence.application.dto.search_models import SearchResult
from lead_intelligence.infrastructure.search.company_crawler.link_prioritization import (
    extract_priority_links,
    normalize_url,
)
from lead_intelligence.infrastructure.search.company_crawler.settings import (
    CompanyCrawlerProviderSettings,
)


class PageLike(Protocol):
    """The subset of Playwright's `Page` this module needs."""

    url: str

    def goto(self, url: str, timeout: float | None = None) -> object: ...

    def content(self) -> str: ...

    def close(self) -> None: ...


class BrowserLike(Protocol):
    """The subset of Playwright's `Browser` this module needs — kept
    minimal and structural so tests can fake it without importing
    Playwright at all."""

    def new_page(self) -> PageLike: ...

    def close(self) -> None: ...


class HomepageUnreachable(Exception):
    """Raised when the homepage itself (as opposed to some candidate
    priority page found on it) could not be loaded — distinct from "the
    crawl completed but found zero priority pages," which is a legitimate
    empty result, not a failure. provider.py catches this and reports
    EnrichmentStatus.FAILURE, the same distinction CompanyWebsiteProvider
    already draws for its own homepage fetch."""

    def __init__(self, homepage_url: str) -> None:
        super().__init__(f"could not load homepage {homepage_url}")
        self.homepage_url = homepage_url


@dataclass(frozen=True)
class _PageSummary:
    title: str
    snippet: str


def crawl_company_site(
    browser: BrowserLike,
    homepage_url: str,
    settings: CompanyCrawlerProviderSettings,
    source: str,
    robots_allow: Callable[[str], bool] = lambda url: True,
    sleep_fn: Callable[[float], None] = lambda seconds: None,
) -> tuple[SearchResult, ...]:
    """Crawl `homepage_url`'s site and return every successfully visited
    priority page as a SearchResult, most-plausible first.

    Raises:
        HomepageUnreachable: If the homepage itself could not be loaded
            (after retries) — distinct from a successful crawl that
            simply found zero priority pages, which returns `()` rather
            than raising.

    Args:
        browser: Already-launched; this function only opens/closes pages
            on it, never the browser itself.
        homepage_url: Where the crawl starts (never itself returned).
        settings: Crawl budget (max_pages/max_depth/max_results) and
            per-page timeout/retry policy.
        source: Stamped onto every SearchResult's `source` field (the
            provider_id).
        robots_allow: Called with each candidate URL before it is
            visited; a URL this rejects is skipped, logged, and never
            counted against `max_pages`. Defaults to "always allowed" so
            tests exercising crawl logic don't need a robots fixture.
        sleep_fn: Called between retry attempts. Override with a no-op in
            tests to avoid real delays.

    Returns:
        Up to `settings.max_results` SearchResults, in the order their
        pages were discovered/prioritized (BFS, highest-scoring first
        within each depth level) — never more than `settings.max_pages`
        pages were actually visited to produce them.
    """

    seen: set[str] = {normalize_url(homepage_url)}
    homepage_html = _fetch(browser, homepage_url, settings, sleep_fn)
    if homepage_html is None:
        logger.warning("Could not load homepage {}; nothing to crawl.", homepage_url)
        raise HomepageUnreachable(homepage_url)

    frontier = extract_priority_links(homepage_html, homepage_url, seen)
    _mark_seen(frontier, seen)
    logger.info(
        "Company crawl: homepage loaded, {} priority link(s) found on {}",
        len(frontier),
        homepage_url,
    )

    results: list[SearchResult] = []
    depth = 1
    while frontier and len(results) < settings.max_pages and depth <= settings.max_depth:
        next_frontier: list[tuple[str, str, int]] = []

        for url, link_text, score in frontier:
            if len(results) >= settings.max_pages:
                break

            if not robots_allow(url):
                logger.info("robots.txt disallows {}; skipping.", url)
                continue

            html = _fetch(browser, url, settings, sleep_fn)
            if html is None:
                continue

            summary = _summarize(html)
            results.append(
                SearchResult(
                    title=summary.title or link_text or url,
                    url=url,
                    snippet=summary.snippet,
                    source=source,
                    rank=len(results) + 1,
                )
            )
            logger.debug("Crawled priority page ({} keyword match(es)): {}", score, url)

            if depth < settings.max_depth:
                deeper = extract_priority_links(html, url, seen)
                _mark_seen(deeper, seen)
                next_frontier.extend(deeper)

        frontier = sorted(next_frontier, key=lambda item: (-item[2], item[0]))
        depth += 1

    logger.info(
        "Company crawl complete: {} page(s) crawled from {}", len(results), homepage_url
    )
    return tuple(results[: settings.max_results])


def _mark_seen(
    candidates: Sequence[tuple[str, str, int]], seen: set[str]
) -> None:
    """Marks every candidate URL as seen the moment it's *discovered*
    (not only once visited) — otherwise the same link, found again from a
    second page at the same crawl depth, would be queued twice."""

    for url, _, _ in candidates:
        seen.add(normalize_url(url))


def _summarize(html: str) -> _PageSummary:
    """A page's title and a short preview of its content — a lightweight,
    SERP-style summary only, not the real content extraction
    SearchExtractionEngine performs on this same URL afterward (see
    provider.py's module docstring on why this stays deliberately
    shallow)."""

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    title = ""
    if soup.title is not None and soup.title.string:
        title = soup.title.string.strip()

    snippet = ""
    description = soup.find("meta", attrs={"name": "description"})
    if description is not None:
        snippet = str(description.get("content") or "").strip()
    if not snippet:
        body = soup.body if soup.body is not None else soup
        snippet = " ".join(body.get_text(" ", strip=True).split())[:240]

    return _PageSummary(title=title, snippet=snippet)


def _fetch(
    browser: BrowserLike,
    url: str,
    settings: CompanyCrawlerProviderSettings,
    sleep_fn: Callable[[float], None],
) -> str | None:
    """Navigate to `url` and return its rendered HTML, retrying transient
    navigation failures up to `settings.max_retries` additional times.
    Returns None if the page could not be loaded at all."""

    attempts = settings.max_retries + 1
    for attempt in range(1, attempts + 1):
        page: PageLike | None = None
        try:
            page = browser.new_page()
            page.goto(url, timeout=settings.timeout_seconds * 1000)
            return page.content()
        except Exception as exc:  # noqa: BLE001 - any navigation failure is retried
            logger.warning(
                "Error loading {} (attempt {}/{}): {}", url, attempt, attempts, exc
            )
            if attempt == attempts:
                return None
            sleep_fn(settings.retry_backoff_seconds * attempt)
            continue
        finally:
            if page is not None:
                page.close()

    return None
