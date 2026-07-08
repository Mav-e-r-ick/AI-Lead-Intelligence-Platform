"""Tests for extraction.parse_search_response."""

from __future__ import annotations

from lead_intelligence.infrastructure.enrichment.google_search.extraction import (
    parse_search_response,
)
from tests.unit.google_search.fixtures import search_item, search_response_body


class TestParseSearchResponse:
    def test_extracts_title_url_snippet_and_domain(self) -> None:
        body = search_response_body(
            search_item(
                "Ada Lovelace promoted to CTO",
                "https://news.example.com/ada",
                snippet="Acme Corp announced today...",
                display_link="news.example.com",
            )
        )

        results = parse_search_response(body)

        assert len(results) == 1
        result = results[0]
        assert result.title == "Ada Lovelace promoted to CTO"
        assert result.url == "https://news.example.com/ada"
        assert result.snippet == "Acme Corp announced today..."
        assert result.source_domain == "news.example.com"
        assert result.published_at is None

    def test_extracts_published_at_from_metatags(self) -> None:
        body = search_response_body(
            search_item(
                "Ada Lovelace promoted to CTO",
                "https://news.example.com/ada",
                published_time="2024-05-01T00:00:00Z",
            )
        )

        results = parse_search_response(body)

        assert results[0].published_at == "2024-05-01T00:00:00Z"

    def test_falls_back_to_url_domain_when_display_link_missing(self) -> None:
        item = search_item("Title", "https://example.com/page")
        del item["displayLink"]
        body = search_response_body(item)

        results = parse_search_response(body)

        assert results[0].source_domain == "example.com"

    def test_multiple_items_are_all_extracted(self) -> None:
        body = search_response_body(
            search_item("First", "https://a.example.com/1"),
            search_item("Second", "https://b.example.com/2"),
        )

        results = parse_search_response(body)

        assert [r.title for r in results] == ["First", "Second"]

    def test_item_missing_title_is_skipped(self) -> None:
        item = search_item("", "https://example.com/page")
        body = search_response_body(item)

        results = parse_search_response(body)

        assert results == ()

    def test_item_missing_url_is_skipped(self) -> None:
        item = search_item("Title", "")
        body = search_response_body(item)

        results = parse_search_response(body)

        assert results == ()

    def test_no_items_key_returns_empty_tuple(self) -> None:
        assert parse_search_response({}) == ()

    def test_empty_items_list_returns_empty_tuple(self) -> None:
        assert parse_search_response({"items": []}) == ()
