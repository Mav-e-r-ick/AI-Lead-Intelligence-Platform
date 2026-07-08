"""Shared fixtures for BrowserSearchProvider's tests — a fake, in-memory
stand-in for Playwright's Page/Browser plus an httpx mock-transport
builder for the robots.txt check, so no test here ever launches a real
browser or touches the real network."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

from lead_intelligence.infrastructure.search.browser.settings import (
    BrowserSearchProviderSettings,
)


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def build_settings(**overrides: object) -> BrowserSearchProviderSettings:
    """A valid BrowserSearchProviderSettings with sane test defaults,
    overridable per test."""

    defaults: dict[str, object] = {
        "search_url_template": "https://search.example.org/search?q={query}",
        "result_container_selector": "div.result",
        "title_selector": "h3",
        "url_selector": "a",
        "snippet_selector": "p.snippet",
    }
    defaults.update(overrides)
    return BrowserSearchProviderSettings(**defaults)  # type: ignore[arg-type]


class FakeElement:
    """A fake Playwright ElementHandle: a nested lookup table of child
    elements plus its own text/attributes."""

    def __init__(
        self,
        children: dict[str, "FakeElement"] | None = None,
        text: str = "",
        attrs: dict[str, str] | None = None,
    ) -> None:
        self._children = children or {}
        self._text = text
        self._attrs = attrs or {}

    def query_selector(self, selector: str) -> "FakeElement | None":
        return self._children.get(selector)

    def inner_text(self) -> str:
        return self._text

    def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)


def result_container(
    title: str | None,
    href: str | None,
    snippet: str | None = None,
) -> FakeElement:
    """One fake search-result container, matching the selectors
    `build_settings()` configures (h3 / a / p.snippet)."""

    children: dict[str, FakeElement] = {}
    if title is not None:
        children["h3"] = FakeElement(text=title)
    if href is not None:
        children["a"] = FakeElement(attrs={"href": href})
    if snippet is not None:
        children["p.snippet"] = FakeElement(text=snippet)
    return FakeElement(children=children)


class FakePage:
    """A fake Playwright Page: `query_selector_all` returns whichever
    containers it was built with; `goto` and `close` are no-ops unless a
    test injects a failure via `goto_raises`."""

    def __init__(
        self,
        containers: list[FakeElement] | None = None,
        url: str = "https://search.example.org/search?q=test",
        goto_raises: Exception | None = None,
    ) -> None:
        self._containers = containers or []
        self.url = url
        self._goto_raises = goto_raises
        self.goto_calls: list[str] = []
        self.closed = False

    def query_selector_all(self, selector: str) -> list[FakeElement]:
        return self._containers

    def goto(self, url: str, timeout: float | None = None) -> None:
        self.goto_calls.append(url)
        if self._goto_raises is not None:
            raise self._goto_raises

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    """A fake Playwright Browser: `new_page()` returns a fresh FakePage
    built from `page_factory` each time, and records every page it made."""

    def __init__(self, page_factory: Callable[[], FakePage] | None = None) -> None:
        self._page_factory = page_factory or FakePage
        self.pages: list[FakePage] = []
        self.closed = False

    def new_page(self) -> FakePage:
        page = self._page_factory()
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


def robots_allow_all_transport(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="User-agent: *\nAllow: /")


def robots_disallow_all_transport(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="User-agent: *\nDisallow: /")


def robots_not_found_transport(request: httpx.Request) -> httpx.Response:
    return httpx.Response(404)


def build_http_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.Client:
    """An httpx.Client whose requests are answered entirely by `handler`,
    never touching the real network — used only for the robots.txt check."""

    return httpx.Client(transport=httpx.MockTransport(handler))
