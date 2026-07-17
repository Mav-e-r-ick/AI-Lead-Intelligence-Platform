"""crawl_company_press_pages: drives a real (or, in tests, fake) browser
breadth-first through a company's website, prioritized by
`link_prioritization.py`'s press/newsroom/media/investor-relations/
announcements keyword set, producing one SearchResult per successfully
visited priority page.

WHY THIS IS A SIBLING TO company_crawler/crawler.py, NOT A REUSE OF IT:
Structurally near-identical BFS crawl loop, but deliberately kept as an
independent module rather than a shared, parameterized one — this task
explicitly says "Keep the existing implementation" for
CompanyCrawlerProvider, so its `crawler.py` is not refactored to share
internals with this one, even though the shape overlaps. See
`link_prioritization.py`'s own module docstring for the same reasoning
applied one layer down.

WHY THE HOMEPAGE ITSELF IS NEVER RETURNED AS A RESULT, WHY BREADTH-FIRST,
WHY robots_allow IS A CALLBACK:
Same reasoning as `company_crawler/crawler.py`'s own module docstring,
verbatim — nothing about those decisions changes for a narrower keyword
set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from loguru import logger

from lead_intelligence.application.dto.search_models import SearchResult
from lead_intelligence.infrastructure.search.press_release.link_prioritization import (
    extract_priority_links,
    normalize_url,
)
from lead_intelligence.infrastructure.search.press_release.settings import (
    PressReleaseProviderSettings,
)


class PageLike(Protocol):
    """The subset of Playwright's `Page` this module needs."""

    url: str

    def goto(self, url: str, timeout: float | None = None) -> object: ...

    def content(self) -> str: ...

    def close(self) -> None: ...


class BrowserLike(Protocol):
    """The subset of Playwright's `Browser` this module needs."""

    def new_page(self) -> PageLike: ...

    def close(self) -> None: ...


class HomepageUnreachable(Exception):
    """Raised when the homepage itself could not be loaded — distinct
    from "the crawl completed but found zero priority pages," which is a
    legitimate empty result, not a failure. `provider.py` catches this and
    reports `EnrichmentStatus.FAILURE`."""

    def __init__(self, homepage_url: str) -> None:
        super().__init__(f"could not load homepage {homepage_url}")
        self.homepage_url = homepage_url


@dataclass(frozen=True)
class _PageSummary:
    title: str
    snippet: str


def crawl_company_press_pages(
    browser: BrowserLike,
    homepage_url: str,
    settings: PressReleaseProviderSettings,
    source: str,
    robots_allow: Callable[[str], bool] = lambda url: True,
    sleep_fn: Callable[[float], None] = lambda seconds: None,
) -> tuple[SearchResult, ...]:
    """Crawl `homepage_url`'s site and return every successfully visited
    press/newsroom/media/investor-relations/announcements page as a
    SearchResult, most-plausible first.

    Raises:
        HomepageUnreachable: If the homepage itself could not be loaded
            (after retries).

    Args:
        browser: Already-launched; this function only opens/closes pages
            on it, never the browser itself.
        homepage_url: Where the crawl starts (never itself returned).
        settings: Crawl budget and per-page timeout/retry policy.
        source: Stamped onto every SearchResult's `source` field.
        robots_allow: Called with each candidate URL before it is
            visited; a URL this rejects is skipped and never counted
            against `max_pages`.
        sleep_fn: Called between retry attempts.
    """

    seen: set[str] = {normalize_url(homepage_url)}
    homepage_html = _fetch(browser, homepage_url, settings, sleep_fn)
    if homepage_html is None:
        logger.warning("Could not load homepage {}; nothing to crawl.", homepage_url)
        raise HomepageUnreachable(homepage_url)

    frontier = extract_priority_links(homepage_html, homepage_url, seen)
    _mark_seen(frontier, seen)
    logger.info(
        "Press release crawl: homepage loaded, {} priority link(s) found on {}",
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
        "Press release crawl complete: {} page(s) crawled from {}",
        len(results),
        homepage_url,
    )
    return tuple(results[: settings.max_results])


def _mark_seen(candidates: Sequence[tuple[str, str, int]], seen: set[str]) -> None:
    for url, _, _ in candidates:
        seen.add(normalize_url(url))


def _summarize(html: str) -> _PageSummary:
    """A page's title and a short preview of its content — a lightweight,
    SERP-style summary only, not the real content extraction
    SearchExtractionEngine performs on this same URL afterward."""

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
    settings: PressReleaseProviderSettings,
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
