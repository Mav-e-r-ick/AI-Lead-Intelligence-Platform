"""Extracts SearchResults from a rendered search-results page, using the
CSS selectors configured on BrowserSearchProviderSettings.

WHY THIS TAKES A DUCK-TYPED "page-like" OBJECT, NOT AN IMPORTED
`playwright.sync_api.Page` TYPE:
Every method this module calls (`query_selector_all`, `query_selector`,
`inner_text`, `get_attribute`, and the `.url` property) is exactly what a
real Playwright `Page`/`ElementHandle` already provides — but importing
the real type here would force every test of this pure extraction logic
to either construct a real browser or import Playwright's types just to
build a fake. Structural typing (`Protocol`) lets tests use a plain,
dependency-free fake that merely has the same methods, per requirement
10's "mock browser interactions in tests where practical."

WHY max_results STOPS AT THE FIRST N SUCCESSFULLY EXTRACTED RESULTS, NOT
THE FIRST N DOM CONTAINERS:
A results page can have malformed or ad/promoted containers missing a
title or link. "Collect the first N result URLs" means N usable results,
not N raw DOM nodes some of which might extract to nothing — so this
module keeps walking containers in page order until it has N genuine
results or runs out of containers, and `rank` reflects the order of what
was actually returned, not raw DOM position.
"""

from __future__ import annotations

from typing import Protocol, Sequence
from urllib.parse import urljoin

from loguru import logger

from lead_intelligence.application.dto.search_models import SearchResult
from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)


class ElementLike(Protocol):
    """The subset of Playwright's `ElementHandle` this module needs."""

    def query_selector(self, selector: str) -> "ElementLike | None": ...

    def inner_text(self) -> str: ...

    def get_attribute(self, name: str) -> str | None: ...


class PageLike(Protocol):
    """The subset of Playwright's `Page` this module needs."""

    url: str

    def query_selector_all(self, selector: str) -> Sequence[ElementLike]: ...


def extract_results(
    page: PageLike, settings: BrowserSearchProviderSettings, source: str
) -> tuple[SearchResult, ...]:
    """Extract up to `settings.max_results` SearchResults from `page`.

    Args:
        page: The rendered search-results page (or a fake matching
            PageLike, in tests).
        settings: Supplies which CSS selectors to use and how many
            results to collect.
        source: The provider_id to stamp onto every SearchResult's
            `source` field.

    Returns:
        Every successfully extracted result (title and URL both present
        and non-blank), up to `settings.max_results`, in page order.
        Containers missing a title or URL are skipped, not counted
        towards the limit.
    """

    containers = list(page.query_selector_all(settings.result_container_selector))
    logger.debug(
        "Result container selector '{}' matched {} element(s) on {}",
        settings.result_container_selector,
        len(containers),
        page.url,
    )

    results: list[SearchResult] = []
    skipped = 0
    for container in containers:
        if len(results) >= settings.max_results:
            break

        title_element = container.query_selector(settings.title_selector)
        url_element = container.query_selector(settings.url_selector)
        if title_element is None or url_element is None:
            skipped += 1
            continue

        title = (title_element.inner_text() or "").strip()
        href = (url_element.get_attribute("href") or "").strip()
        if not title or not href:
            skipped += 1
            continue
        url = urljoin(page.url, href)

        snippet = ""
        if settings.snippet_selector:
            snippet_element = container.query_selector(settings.snippet_selector)
            if snippet_element is not None:
                snippet = (snippet_element.inner_text() or "").strip()

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                source=source,
                rank=len(results) + 1,
            )
        )

    if not results:
        if not containers:
            logger.warning(
                "Result container selector '{}' matched 0 elements on {} — either "
                "the page did not render results (rate limiting/bot detection/a "
                "changed template) or the selector no longer matches this page's "
                "markup.",
                settings.result_container_selector,
                page.url,
            )
        else:
            logger.warning(
                "Result container selector '{}' matched {} element(s) on {}, but "
                "{} of them had no usable title ('{}') and URL ('{}') — those "
                "selectors likely no longer match this page's markup.",
                settings.result_container_selector,
                len(containers),
                page.url,
                skipped,
                settings.title_selector,
                settings.url_selector,
            )

    return tuple(results)
