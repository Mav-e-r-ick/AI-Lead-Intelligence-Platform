"""Shared fixtures for PressReleaseProvider's tests — a fake, in-memory
stand-in for Playwright's Page/Browser plus an httpx mock-transport
builder for robots.txt checks, so no test here ever launches a real
browser or touches the real network."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

from lead_intelligence.infrastructure.search.press_release.settings import (
    PressReleaseProviderSettings,
)


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def build_settings(**overrides: object) -> PressReleaseProviderSettings:
    return PressReleaseProviderSettings(**overrides)  # type: ignore[arg-type]


class FakePage:
    """A fake Playwright Page keyed by URL: `pages` maps a URL to either
    its HTML (str) or an Exception to raise on `goto`."""

    def __init__(self, pages: dict[str, str | Exception]) -> None:
        self._pages = pages
        self.url = ""
        self._content = ""
        self.closed = False

    def goto(self, url: str, timeout: float | None = None) -> None:
        self.url = url
        outcome = self._pages.get(url)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise RuntimeError(f"FakePage has no fixture for {url}")
        self._content = outcome

    def content(self) -> str:
        return self._content

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    """A fake Playwright Browser: every `new_page()` call returns a fresh
    FakePage sharing the same `pages` URL->HTML/Exception map."""

    def __init__(self, pages: dict[str, str | Exception] | None = None) -> None:
        self.pages_served = pages or {}
        self.opened_pages: list[FakePage] = []
        self.closed = False

    def new_page(self) -> FakePage:
        page = FakePage(self.pages_served)
        self.opened_pages.append(page)
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
    return httpx.Client(transport=httpx.MockTransport(handler))
