"""End-to-end unit tests for SearchExtractionEngine, against a mocked
httpx transport — no test here ever touches the real network."""

from __future__ import annotations

import httpx

from lead_intelligence.infrastructure.search.extraction.engine import (
    ENGINE_ID,
    SearchExtractionEngine,
)
from lead_intelligence.infrastructure.search.extraction.settings import (
    SearchExtractionSettings,
)
from tests.unit.search_extraction.fixtures import (
    announcement_page,
    build_http_client,
    fixed_clock,
    html_response,
    make_search_result,
    pdf_response,
)


def _engine(
    client: httpx.Client, settings: SearchExtractionSettings | None = None
) -> SearchExtractionEngine:
    return SearchExtractionEngine(
        settings=settings or SearchExtractionSettings(retry_backoff_seconds=0),
        http_client=client,
        clock=fixed_clock,
    )


class TestSuccessfulExtraction:
    def test_announcement_page_yields_page_and_fact_candidates(self) -> None:
        client = build_http_client(
            pages={"/article": html_response(announcement_page())}
        )
        engine = _engine(client)

        observations = engine.extract(
            "row:1", (make_search_result("https://news.example.com/article"),)
        )

        by_attribute = {o.attribute: o for o in observations}
        assert set(by_attribute) == {
            "web_page",
            "full_name",
            "title",
            "company_name",
            "published_at",
        }
        assert by_attribute["full_name"].value == "Ada Lovelace"
        assert by_attribute["title"].value == "CTO"
        assert by_attribute["company_name"].value == "Acme Corp"
        assert by_attribute["published_at"].value == "2024-05-30T09:00:00Z"
        assert by_attribute["web_page"].value == "Ada Lovelace named CTO of Acme Corp"

    def test_every_candidate_carries_subject_id_engine_id_and_source_url(
        self,
    ) -> None:
        client = build_http_client(
            pages={"/article": html_response(announcement_page())}
        )
        engine = _engine(client)

        observations = engine.extract(
            "row:42", (make_search_result("https://news.example.com/article"),)
        )

        assert observations
        for observation in observations:
            assert observation.subject_id == "row:42"
            assert observation.provider_id == ENGINE_ID
            assert observation.source_url == "https://news.example.com/article"
            assert observation.observed_at == fixed_clock()

    def test_snippet_is_preserved_verbatim_in_raw_context(self) -> None:
        client = build_http_client(
            pages={"/article": html_response(announcement_page())}
        )
        engine = _engine(client)

        observations = engine.extract(
            "row:1",
            (
                make_search_result(
                    "https://news.example.com/article",
                    snippet="  The Original Snippet, verbatim.  ",
                ),
            ),
        )

        for observation in observations:
            assert (
                observation.raw_context["snippet"]
                == "  The Original Snippet, verbatim.  "
            )

    def test_raw_context_carries_provenance_and_page_metadata(self) -> None:
        client = build_http_client(
            pages={"/article": html_response(announcement_page())}
        )
        engine = _engine(client)

        observations = engine.extract(
            "row:1",
            (
                make_search_result(
                    "https://news.example.com/article", source="browser_search", rank=3
                ),
            ),
        )

        raw_context = observations[0].raw_context
        assert raw_context["search_source"] == "browser_search"
        assert raw_context["search_rank"] == "3"
        assert raw_context["page_title"] == "Ada Lovelace named CTO of Acme Corp"
        assert raw_context["published_at"] == "2024-05-30T09:00:00Z"
        assert raw_context["matched_pattern"] == "FACT-001-appointed-role-of-company"
        assert "appointed" in raw_context["text_excerpt"]

    def test_text_excerpt_is_bounded_by_excerpt_chars(self) -> None:
        client = build_http_client(
            pages={"/article": html_response(announcement_page())}
        )
        engine = _engine(
            client,
            settings=SearchExtractionSettings(
                excerpt_chars=20, retry_backoff_seconds=0
            ),
        )

        observations = engine.extract(
            "row:1", (make_search_result("https://news.example.com/article"),)
        )

        assert len(observations[0].raw_context["text_excerpt"]) <= 20


class TestPagesWithoutFacts:
    def test_unmatched_page_still_yields_the_web_page_candidate(self) -> None:
        html = (
            "<html><head><title>Quarterly market overview</title></head>"
            "<body><p>General industry commentary, no announcements.</p>"
            "</body></html>"
        )
        client = build_http_client(pages={"/article": html_response(html)})
        engine = _engine(client)

        observations = engine.extract(
            "row:1", (make_search_result("https://news.example.com/article"),)
        )

        assert [o.attribute for o in observations] == ["web_page"]
        assert observations[0].value == "Quarterly market overview"
        assert "matched_pattern" not in observations[0].raw_context

    def test_untitled_page_falls_back_to_the_search_result_title(self) -> None:
        client = build_http_client(
            pages={"/article": html_response("<html><body>text</body></html>")}
        )
        engine = _engine(client)

        observations = engine.extract(
            "row:1",
            (
                make_search_result(
                    "https://news.example.com/article", title="Result Title"
                ),
            ),
        )

        assert observations[0].attribute == "web_page"
        assert observations[0].value == "Result Title"


class TestSkippedAndFailedPages:
    def test_unreachable_page_yields_no_candidates(self) -> None:
        client = build_http_client(default=httpx.Response(500))
        engine = _engine(
            client,
            settings=SearchExtractionSettings(max_retries=0, retry_backoff_seconds=0),
        )

        observations = engine.extract(
            "row:1", (make_search_result("https://news.example.com/article"),)
        )

        assert observations == ()

    def test_pdf_result_yields_no_candidates(self) -> None:
        client = build_http_client(pages={"/report.pdf": pdf_response()})
        engine = _engine(client)

        observations = engine.extract(
            "row:1", (make_search_result("https://news.example.com/report.pdf"),)
        )

        assert observations == ()

    def test_one_bad_result_never_stops_the_remaining_results(self) -> None:
        client = build_http_client(
            pages={"/good": html_response(announcement_page())},
            default=httpx.Response(500),
        )
        engine = _engine(
            client,
            settings=SearchExtractionSettings(max_retries=0, retry_backoff_seconds=0),
        )

        observations = engine.extract(
            "row:1",
            (
                make_search_result("https://news.example.com/bad", rank=1),
                make_search_result("https://news.example.com/good", rank=2),
            ),
        )

        assert observations
        assert all(
            o.source_url == "https://news.example.com/good" for o in observations
        )


class TestAggregation:
    def test_candidates_from_multiple_results_are_aggregated_in_order(self) -> None:
        client = build_http_client(
            pages={
                "/first": html_response(
                    announcement_page(headline="Ada Lovelace named CTO of Acme Corp")
                ),
                "/second": html_response(
                    announcement_page(
                        headline="Grace Hopper named CEO of Contoso",
                        body="Grace Hopper has been appointed CEO of Contoso.",
                    )
                ),
            }
        )
        engine = _engine(client)

        observations = engine.extract(
            "row:1",
            (
                make_search_result("https://news.example.com/first", rank=1),
                make_search_result("https://news.example.com/second", rank=2),
            ),
        )

        names = [o.value for o in observations if o.attribute == "full_name"]
        assert names == ["Ada Lovelace", "Grace Hopper"]

    def test_no_results_yields_no_candidates(self) -> None:
        engine = _engine(build_http_client())

        assert engine.extract("row:1", ()) == ()
