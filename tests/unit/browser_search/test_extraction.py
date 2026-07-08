"""Unit tests for extraction.extract_results, using fake Playwright-like
page/element objects — no test here ever launches a real browser."""

from __future__ import annotations

from lead_intelligence.infrastructure.search.browser.extraction import extract_results
from tests.unit.browser_search.fixtures import (
    FakeElement,
    FakePage,
    build_settings,
    result_container,
)


def test_extracts_title_url_snippet_and_rank() -> None:
    page = FakePage(
        containers=[result_container("Ada Lovelace promoted", "/a", "snippet text")]
    )
    settings = build_settings()

    results = extract_results(page, settings, source="browser_search")

    assert len(results) == 1
    result = results[0]
    assert result.title == "Ada Lovelace promoted"
    assert result.url == "https://search.example.org/a"
    assert result.snippet == "snippet text"
    assert result.source == "browser_search"
    assert result.rank == 1


def test_relative_url_is_resolved_against_the_page_url() -> None:
    page = FakePage(
        containers=[result_container("Title", "/relative/path")],
        url="https://search.example.org/search?q=x",
    )
    settings = build_settings()

    results = extract_results(page, settings, source="browser_search")

    assert results[0].url == "https://search.example.org/relative/path"


def test_absolute_url_is_preserved() -> None:
    page = FakePage(
        containers=[result_container("Title", "https://other.example/page")]
    )
    settings = build_settings()

    results = extract_results(page, settings, source="browser_search")

    assert results[0].url == "https://other.example/page"


def test_container_missing_title_is_skipped() -> None:
    page = FakePage(
        containers=[
            result_container(None, "/a"),
            result_container("Real Title", "/b"),
        ]
    )
    settings = build_settings()

    results = extract_results(page, settings, source="browser_search")

    assert len(results) == 1
    assert results[0].title == "Real Title"


def test_container_missing_url_is_skipped() -> None:
    page = FakePage(
        containers=[
            result_container("Title Only", None),
            result_container("Real Title", "/b"),
        ]
    )
    settings = build_settings()

    results = extract_results(page, settings, source="browser_search")

    assert len(results) == 1
    assert results[0].title == "Real Title"


def test_missing_snippet_selector_configuration_yields_blank_snippet() -> None:
    page = FakePage(containers=[result_container("Title", "/a", snippet="ignored")])
    settings = build_settings(snippet_selector="")

    results = extract_results(page, settings, source="browser_search")

    assert results[0].snippet == ""


def test_container_missing_snippet_element_yields_blank_snippet() -> None:
    page = FakePage(containers=[result_container("Title", "/a", snippet=None)])
    settings = build_settings()

    results = extract_results(page, settings, source="browser_search")

    assert results[0].snippet == ""


def test_stops_at_max_results_counting_only_successful_extractions() -> None:
    containers = [
        result_container(None, "/skip-1"),  # missing title, not counted
        result_container("First", "/a"),
        result_container("Second", "/b"),
        result_container("Third", "/c"),
    ]
    page = FakePage(containers=containers)
    settings = build_settings(max_results=2)

    results = extract_results(page, settings, source="browser_search")

    assert [r.title for r in results] == ["First", "Second"]
    assert [r.rank for r in results] == [1, 2]


def test_no_containers_yields_no_results() -> None:
    page = FakePage(containers=[])
    settings = build_settings()

    assert extract_results(page, settings, source="browser_search") == ()


def test_blank_title_text_is_treated_as_missing() -> None:
    container = FakeElement(
        children={"h3": FakeElement(text="   "), "a": FakeElement(attrs={"href": "/a"})}
    )
    page = FakePage(containers=[container])
    settings = build_settings()

    assert extract_results(page, settings, source="browser_search") == ()
