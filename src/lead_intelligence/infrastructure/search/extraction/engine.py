"""SearchExtractionEngine: the Search Extraction Engine's single entry
point — SearchResults in, ObservationCandidates out.

Completes the pipeline the approved Search Layer RFC drew:

    SearchResult (URLs only)  ->  Page Fetcher  ->  Content Extractor
                              ->  Observation Extraction  ->  ObservationCandidate

WHY EVERY SUCCESSFULLY FETCHED PAGE YIELDS A `web_page` CANDIDATE, EVEN
WHEN NO FACT PATTERN MATCHED:
"This page exists, was reachable, and says this in its title" is itself
evidence about the executive it was searched for — the same reasoning
behind GoogleSearchProvider's `web_mention` candidates. If candidates
were only emitted on a fact-pattern match, every page phrased outside the
known patterns would silently vanish from the evidence trail. The
`web_page` candidate carries the page title as its value, and the
snippet, publication date, and a text excerpt as `raw_context` — so a
future stage (or a human) can always see what was actually found.

WHY provider_id IS "search_extraction", NOT THE ORIGINATING SEARCH
PROVIDER'S ID:
`ObservationCandidate.provider_id` answers "which component *observed*
this fact." The search provider only found the URL; this engine is what
fetched the page and read the fact off it. The originating provider is
still fully traceable — carried both as `raw_context["search_source"]`
(unchanged) and, as of the Federated Search redesign, as the candidate's
own dedicated `source_provider` field (see enrichment_models.py's
ObservationCandidate docstring) — a first-class field a downstream
consumer can filter/group on without parsing `raw_context`.

WHY EVERY CANDIDATE ALSO CARRIES confidence/raw_text/evidence_type NOW:
Per the Federated Search redesign, several independent providers now
contribute evidence, each with its own trust level
(`application/search/confidence.py`) — a candidate extracted from a
`SearchResult` with `confidence=0.50` (an unrecognized source) and one
extracted from `confidence=1.00` (the company's own website) are not
equally trustworthy, and a future stage needs that carried through rather
than re-deriving it from `source_provider`. `confidence` is inherited
verbatim from the originating `SearchResult`; `raw_text` is the same
visible-text excerpt already computed for `raw_context["text_excerpt"]`,
promoted to its own named field for consumers that only care about
evidence text, not the full raw_context bag; `evidence_type` is a short,
provider-derived label (`_EVIDENCE_TYPE_BY_SOURCE`) for filtering/weighing
by evidence kind (e.g. "a press_release is different evidence than a
web_mention") without string-matching `source_provider` values.

WHY A FAILED/SKIPPED FETCH YIELDS ZERO CANDIDATES, NOT AN ERROR:
An unreachable page, a robots.txt disallow, or a PDF (out of Version 1
scope) means there is nothing this engine can honestly assert — emitting
a candidate anyway would be manufacturing evidence. Each skip is logged
with its reason, one bad URL never stops the remaining results, and the
caller can always compare `len(results)` against the per-URL logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Sequence

import httpx
from loguru import logger

from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.search_models import SearchResult
from lead_intelligence.infrastructure.enrichment.company_website.cache import PageCache
from lead_intelligence.infrastructure.search.extraction.content_extraction import (
    PageContent,
    extract_page_content,
)
from lead_intelligence.infrastructure.search.extraction.fact_extraction import (
    ExtractedFacts,
    extract_facts,
)
from lead_intelligence.infrastructure.search.extraction.page_fetcher import PageFetcher
from lead_intelligence.infrastructure.search.extraction.settings import (
    SearchExtractionSettings,
)

ENGINE_ID = "search_extraction"

#: The always-emitted per-page attribute — see module docstring.
_PAGE_ATTRIBUTE = "web_page"

#: Fact attributes, emitted only when the corresponding fact was actually
#: extracted. Names deliberately reuse CompanyWebsiteProvider's existing
#: observation vocabulary (`full_name`, `title`, `email`, `phone`) plus
#: the canonical `company_name`, never a new parallel vocabulary.
#: `linkedin_url`/`published_at` have no CompanyWebsiteProvider
#: equivalent yet — new attribute names, handled by ComparisonEngine's
#: existing "unknown attribute" path (see comparison/engine.py) exactly
#: like any other attribute it has no explicit field mapping for.
_FACT_ATTRIBUTES = (
    "full_name",
    "title",
    "company_name",
    "email",
    "phone",
    "linkedin_url",
    "published_at",
    "event_keywords",
)

#: Maps a SearchResult.source (the originating SearchProviderPort's
#: provider_id) to a short, human-readable evidence-kind label — stamped
#: onto every candidate's new `evidence_type` metadata field (see
#: enrichment_models.py's ObservationCandidate docstring). An unrecognized
#: source (a future/unknown provider) falls back to `_DEFAULT_EVIDENCE_TYPE`
#: rather than raising — this engine must never fail because a new
#: provider it doesn't yet know about was wired in upstream.
_EVIDENCE_TYPE_BY_SOURCE: dict[str, str] = {
    "company_crawler": "company_page",
    "press_release": "press_release",
    "linkedin_search": "linkedin_profile",
    "news_search": "news_article",
    "google_web_search": "web_mention",
    "browser_search": "web_mention",
}
_DEFAULT_EVIDENCE_TYPE = "web_mention"


class SearchExtractionEngine:
    """Converts SearchResults into ObservationCandidates by fetching each
    result's destination page and applying deterministic, rule-based
    extraction (Version 1 — see module docstring and README.md)."""

    def __init__(
        self,
        settings: SearchExtractionSettings | None = None,
        http_client: httpx.Client | None = None,
        cache: PageCache | None = None,
        page_fetcher: PageFetcher | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure an engine instance.

        Args:
            settings: Timeout/retry/cache/text-bound policy. Defaults to
                SearchExtractionSettings()'s conservative defaults.
            http_client: The httpx.Client used for every page and
                robots.txt fetch. Defaults to a real client; tests inject
                one built with `transport=httpx.MockTransport(...)`.
            cache: Where fetched page content is reused from. Defaults to
                a fresh in-memory cache sized from `settings.cache_ttl`.
            page_fetcher: The fetcher to use. Defaults to a PageFetcher
                built from the arguments above; injectable so tests can
                fake fetching entirely without touching httpx.
            clock: Returns the current UTC time (stamped as each
                candidate's `observed_at`). Override with a fixed value
                in tests for reproducible timestamps.
        """

        self._settings = settings or SearchExtractionSettings()
        self._settings.validate()
        self._fetcher = page_fetcher or PageFetcher(
            self._settings, http_client=http_client, cache=cache, clock=clock
        )
        self._clock = clock

    def extract(
        self, subject_id: str, search_results: Sequence[SearchResult]
    ) -> tuple[ObservationCandidate, ...]:
        """Fetch every search result's page and return every observation
        the pages yielded.

        Args:
            subject_id: The Digital Twin (or provisional identity) id
                these search results are about — stamped onto every
                candidate, the same opaque-id convention every other
                stage uses.
            search_results: The results to extract from, in order.

        Returns:
            Every ObservationCandidate from every fetchable page, in
            input order. A result whose page couldn't or shouldn't be
            fetched (unreachable, robots.txt disallow, PDF) contributes
            nothing — logged, never raised.
        """

        logger.info(
            "Search extraction starting: subject_id={}, {} search result(s)",
            subject_id,
            len(search_results),
        )

        observations: list[ObservationCandidate] = []
        pages_extracted = 0
        pages_skipped = 0

        for result in search_results:
            candidates = self._extract_one(subject_id, result)
            if candidates:
                pages_extracted += 1
                observations.extend(candidates)
            else:
                pages_skipped += 1

        logger.info(
            "Search extraction complete: subject_id={}, {} page(s) extracted, "
            "{} skipped, {} observation(s)",
            subject_id,
            pages_extracted,
            pages_skipped,
            len(observations),
        )
        return tuple(observations)

    def _extract_one(
        self, subject_id: str, result: SearchResult
    ) -> list[ObservationCandidate]:
        html = self._fetcher.fetch(result.url)
        if html is None:
            logger.debug(
                "No content for {} (skipped or unfetchable); no observations.",
                result.url,
            )
            return []

        content = extract_page_content(html, self._settings.max_text_chars)
        facts = extract_facts(content.title, content.visible_text)
        observed_at = self._clock()
        raw_context = self._build_raw_context(result, content, facts)

        # Common Federated Search metadata (see enrichment_models.py's
        # ObservationCandidate docstring), shared by every candidate this
        # one page produces: which SearchProviderPort actually found this
        # URL (`source_provider`, distinct from `provider_id="search_extraction"`
        # above — see module docstring's own "WHY provider_id IS
        # search_extraction" section), the evidence's own confidence
        # (inherited from the SearchResult that pointed at it, per
        # `application/search/confidence.py`), a verbatim text excerpt for
        # human/audit review, and a short evidence-kind label derived from
        # that same source.
        source_provider = result.source
        confidence = result.confidence
        raw_text = content.visible_text[: self._settings.excerpt_chars]
        evidence_type = _EVIDENCE_TYPE_BY_SOURCE.get(result.source, _DEFAULT_EVIDENCE_TYPE)
        published_date = content.published_at

        candidates = [
            ObservationCandidate(
                subject_id=subject_id,
                attribute=_PAGE_ATTRIBUTE,
                # Prefer the page's own title; fall back to the search
                # result's title so the candidate always has a real value.
                value=content.title or result.title,
                provider_id=ENGINE_ID,
                observed_at=observed_at,
                source_url=result.url,
                raw_context=raw_context,
                source_provider=source_provider,
                published_date=published_date,
                confidence=confidence,
                raw_text=raw_text,
                evidence_type=evidence_type,
            )
        ]

        fact_values: dict[str, str | None] = {
            "full_name": facts.full_name,
            "title": facts.title,
            "company_name": facts.company_name,
            "email": facts.email,
            "phone": facts.phone,
            "linkedin_url": facts.linkedin_url,
            # Sourced from PageContent (content_extraction.py), not
            # ExtractedFacts — already carried in raw_context below either
            # way; promoted here to its own comparable/queryable candidate.
            "published_at": content.published_at,
            "event_keywords": facts.event_keywords,
        }
        for attribute in _FACT_ATTRIBUTES:
            value = fact_values[attribute]
            if value:
                candidates.append(
                    ObservationCandidate(
                        subject_id=subject_id,
                        attribute=attribute,
                        value=value,
                        provider_id=ENGINE_ID,
                        observed_at=observed_at,
                        source_url=result.url,
                        raw_context=raw_context,
                        source_provider=source_provider,
                        published_date=published_date,
                        confidence=confidence,
                        raw_text=raw_text,
                        evidence_type=evidence_type,
                    )
                )

        logger.debug(
            "Extracted {} observation(s) from {} (pattern: {})",
            len(candidates),
            result.url,
            facts.matched_pattern or "none",
        )
        return candidates

    def _build_raw_context(
        self, result: SearchResult, content: PageContent, facts: ExtractedFacts
    ) -> dict[str, str]:
        """Shared provenance for every candidate one page produces —
        including the raw search snippet, preserved verbatim per this
        task's own requirement."""

        raw_context = {
            "search_source": result.source,
            "search_rank": str(result.rank),
            "search_result_title": result.title,
            "snippet": result.snippet,
            "page_title": content.title,
            "text_excerpt": content.visible_text[: self._settings.excerpt_chars],
        }
        if content.published_at:
            raw_context["published_at"] = content.published_at
        if facts.matched_pattern:
            raw_context["matched_pattern"] = facts.matched_pattern
        return raw_context
