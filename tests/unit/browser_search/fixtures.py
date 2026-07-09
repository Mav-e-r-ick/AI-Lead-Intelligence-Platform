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
        "user_data_dir": "/tmp/fake-chrome-profile",
        "snippet_selector": "p.snippet",
        # Disabled by default so tests that don't care about debug-artifact
        # saving never write files to the real filesystem; tests that do
        # care override this explicitly (e.g. with pytest's tmp_path).
        "debug_dir": "",
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


class FakeKeyboard:
    """A fake Playwright Keyboard: records every character typed (as one
    combined string, in order) and every key pressed."""

    def __init__(self) -> None:
        self.typed_text = ""
        self.pressed_keys: list[str] = []

    def type(self, text: str, delay: float | None = None) -> None:
        self.typed_text += text

    def press(self, key: str) -> None:
        self.pressed_keys.append(key)


class FakeMouse:
    """A fake Playwright Mouse: records every wheel-scroll call."""

    def __init__(self) -> None:
        self.wheel_calls: list[tuple[float, float]] = []

    def wheel(self, delta_x: float, delta_y: float) -> None:
        self.wheel_calls.append((delta_x, delta_y))


class FakePage:
    """A fake Playwright Page: `query_selector_all` returns whichever
    result containers it was built with; `goto` and `close` are no-ops
    unless a test injects a failure via `goto_raises`. Also fakes the
    human-like-search interaction surface (`query_selector`, `click`,
    `wait_for_load_state`, `wait_for_selector`, `keyboard`, `mouse`,
    `title`) `_perform_human_like_search` drives — by default a search
    box is "present" (so the happy path doesn't need special setup) and
    no consent control is present; a test that wants to exercise consent
    handling passes `consent_accept_selector` plus `post_consent_*` to
    describe what the page looks like after that control is clicked
    (this fake's state does not otherwise change over time)."""

    def __init__(
        self,
        containers: list[FakeElement] | None = None,
        url: str = "https://search.example.org/search?q=test",
        goto_raises: Exception | None = None,
        html: str = "<html><body>fake page</body></html>",
        title: str = "Fake Search Results",
        search_box_selector: str | None = "textarea[name='q']",
        consent_accept_selector: str | None = None,
        post_consent_url: str | None = None,
        post_consent_html: str | None = None,
        post_consent_containers: list[FakeElement] | None = None,
        wait_for_selector_raises: Exception | None = None,
    ) -> None:
        self._containers = containers or []
        self.url = url
        self._goto_raises = goto_raises
        self._html = html
        self._title = title
        self._search_box_selector = search_box_selector
        self._consent_accept_selector = consent_accept_selector
        self._post_consent_url = post_consent_url
        self._post_consent_html = post_consent_html
        self._post_consent_containers = post_consent_containers
        self._wait_for_selector_raises = wait_for_selector_raises
        self.goto_calls: list[str] = []
        self.click_calls: list[str] = []
        self.wait_for_load_state_calls = 0
        self.wait_for_selector_calls: list[str] = []
        self.closed = False
        self.screenshot_paths: list[str] = []
        self.keyboard = FakeKeyboard()
        self.mouse = FakeMouse()

    def query_selector_all(self, selector: str) -> list[FakeElement]:
        return self._containers

    def query_selector(self, selector: str) -> FakeElement | None:
        if selector == self._search_box_selector:
            return FakeElement()
        if selector == self._consent_accept_selector:
            return FakeElement()
        return None

    def click(self, selector: str, timeout: float | None = None) -> None:
        self.click_calls.append(selector)
        if selector == self._consent_accept_selector and (
            self._post_consent_url is not None
            or self._post_consent_html is not None
            or self._post_consent_containers is not None
        ):
            self.url = self._post_consent_url or self.url
            self._html = self._post_consent_html or self._html
            if self._post_consent_containers is not None:
                self._containers = self._post_consent_containers

    def wait_for_load_state(
        self, state: str = "load", timeout: float | None = None
    ) -> None:
        self.wait_for_load_state_calls += 1

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> None:
        self.wait_for_selector_calls.append(selector)
        if self._wait_for_selector_raises is not None:
            raise self._wait_for_selector_raises

    def title(self) -> str:
        return self._title

    def goto(self, url: str, timeout: float | None = None) -> None:
        self.goto_calls.append(url)
        if self._goto_raises is not None:
            raise self._goto_raises

    def close(self) -> None:
        self.closed = True

    def content(self) -> str:
        return self._html

    def screenshot(self, path: str) -> None:
        self.screenshot_paths.append(path)
        # A real Playwright screenshot() writes an actual file; match that
        # so tests can assert on the file existing, not just the call.
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")


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
