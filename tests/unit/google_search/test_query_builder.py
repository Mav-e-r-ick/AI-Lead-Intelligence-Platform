"""Tests for query_builder.build_queries."""

from __future__ import annotations

from lead_intelligence.infrastructure.enrichment.google_search.query_builder import (
    build_queries,
)
from lead_intelligence.infrastructure.enrichment.google_search.settings import (
    DEFAULT_QUERY_TEMPLATES,
)


class TestBuildQueries:
    def test_default_templates_with_name_and_company(self) -> None:
        queries = build_queries(
            "Ada Lovelace", "Acme Corp", None, DEFAULT_QUERY_TEMPLATES
        )

        assert queries == (
            '"Ada Lovelace" "Acme Corp"',
            '"Ada Lovelace" promotion',
            '"Ada Lovelace" appointed',
            '"Ada Lovelace" joins',
            '"Ada Lovelace" resigned',
            '"Ada Lovelace" leadership',
        )

    def test_company_template_skipped_when_company_missing(self) -> None:
        queries = build_queries("Ada Lovelace", None, None, DEFAULT_QUERY_TEMPLATES)

        assert '"Ada Lovelace" "Acme Corp"' not in queries
        assert '"Ada Lovelace" promotion' in queries
        assert len(queries) == 5

    def test_company_template_skipped_when_company_blank(self) -> None:
        queries = build_queries("Ada Lovelace", "   ", None, DEFAULT_QUERY_TEMPLATES)

        assert all("Acme" not in q for q in queries)
        assert len(queries) == 5

    def test_no_queries_when_name_blank(self) -> None:
        queries = build_queries("", "Acme Corp", None, DEFAULT_QUERY_TEMPLATES)

        assert queries == ()

    def test_title_placeholder_included_when_title_present(self) -> None:
        queries = build_queries(
            "Ada Lovelace", "Acme Corp", "CEO", ('"{name}" "{title}"',)
        )

        assert queries == ('"Ada Lovelace" "CEO"',)

    def test_title_template_skipped_when_title_missing(self) -> None:
        queries = build_queries(
            "Ada Lovelace", "Acme Corp", None, ('"{name}" "{title}"',)
        )

        assert queries == ()

    def test_duplicate_queries_are_deduplicated(self) -> None:
        queries = build_queries(
            "Ada Lovelace",
            "Acme Corp",
            None,
            ('"{name}" promotion', '"{name}" promotion'),
        )

        assert queries == ('"Ada Lovelace" promotion',)

    def test_unknown_placeholder_is_skipped(self) -> None:
        queries = build_queries(
            "Ada Lovelace", "Acme Corp", None, ('"{name}" {unknown_field}',)
        )

        assert queries == ()

    def test_template_order_is_preserved(self) -> None:
        templates = ('"{name}" leadership', '"{name}" promotion')

        queries = build_queries("Ada Lovelace", None, None, templates)

        assert queries == ('"Ada Lovelace" leadership', '"Ada Lovelace" promotion')

    def test_name_and_company_are_stripped(self) -> None:
        queries = build_queries(
            "  Ada Lovelace  ", "  Acme Corp  ", None, ('"{name}" "{company}"',)
        )

        assert queries == ('"Ada Lovelace" "Acme Corp"',)

    def test_empty_template_list_returns_empty_tuple(self) -> None:
        queries = build_queries("Ada Lovelace", "Acme Corp", "CEO", ())

        assert queries == ()
