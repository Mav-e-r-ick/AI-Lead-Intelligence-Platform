"""dedup_and_rank: turns the concatenated SearchResults of every provider
`SearchCoordinator` executed into one deduplicated, confidence-ranked
sequence.

WHY THIS IS ITS OWN MODULE, NOT INLINE IN coordinator.py:
Same reasoning this codebase already applies elsewhere (e.g.
`company_crawler/link_prioritization.py` living apart from `crawler.py`):
merge/dedup/rank is a pure, independently testable transformation with no
dependency on provider execution, health tracking, or profiles — keeping
it separate lets it be tested directly against plain `SearchResult` tuples
instead of through a full coordinator run.

WHY "DUPLICATE" MEANS "SAME NORMALIZED URL", NOT "SAME PROVIDER" OR
"SAME TITLE":
Per the Federated Search redesign, several independent providers now run
on every request, and it is expected (not a bug) for two of them to
surface the exact same underlying page — e.g. NewsProvider and
GoogleSearchProvider both finding the same Reuters article, or
CompanyCrawlerProvider and PressReleaseProvider both reaching the same
press page via different link paths. `SearchExtractionEngine` fetching
that URL twice would waste a request and produce duplicate
ObservationCandidates for the same evidence, so this module collapses
same-URL results to one before extraction ever runs.

WHY THE SURVIVOR OF A DUPLICATE IS THE HIGHEST-CONFIDENCE COPY, NOT THE
FIRST-SEEN ONE:
Two providers reporting the same URL may disagree on `confidence` (e.g. a
generic GoogleSearchProvider result happens to point at a company's own
site, versus CompanyCrawlerProvider finding that same URL directly) — see
`confidence.py`. Keeping the highest-confidence copy means the surviving
`SearchResult.source`/`confidence` always reflects the most trustworthy
way this evidence was actually found, which downstream consumers (and any
future confidence-weighted decision) rely on.

WHY RANKING IS BY confidence DESCENDING, WITH A DETERMINISTIC TIE-BREAK:
The whole point of running multiple independent providers is to surface
the most trustworthy evidence first — `SearchExtractionEngine` (and any
future stage with a results budget) should spend it on the
highest-confidence pages first. Ties are broken by `source` then `rank`,
never by dict/insertion order, so the same input always produces the same
output (see `test_result_merging.py`'s determinism test).
"""

from __future__ import annotations

from typing import Sequence
from urllib.parse import ParseResult, urlparse

from lead_intelligence.application.dto.search_models import SearchResult


def dedup_and_rank(results: Sequence[SearchResult]) -> tuple[SearchResult, ...]:
    """Deduplicate `results` by normalized URL (keeping the
    highest-confidence copy of each) and return them sorted by
    `confidence` descending.

    Args:
        results: Every SearchResult collected across every executed
            provider, in execution order. Order does not affect the
            output beyond determinism — see module docstring.

    Returns:
        One SearchResult per distinct normalized URL, most-trustworthy
        first.
    """

    best_by_url: dict[str, SearchResult] = {}
    first_seen_order: list[str] = []

    for result in results:
        key = _normalize_url(result.url)
        existing = best_by_url.get(key)
        if existing is None:
            best_by_url[key] = result
            first_seen_order.append(key)
        elif result.confidence > existing.confidence:
            best_by_url[key] = result

    deduped = [best_by_url[key] for key in first_seen_order]
    return tuple(
        sorted(deduped, key=lambda result: (-result.confidence, result.source, result.rank))
    )


def _normalize_url(url: str) -> str:
    """`url` with its host lowercased and its fragment/trailing slash
    stripped — "https://Example.com/x/" and "https://example.com/x#y" are
    the same result for deduplication purposes."""

    parsed = urlparse(url)
    path = parsed.path
    if path.endswith("/") and path != "/":
        path = path[:-1]
    query = _query(parsed)
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}{query}"


def _query(parsed: ParseResult) -> str:
    return f"?{parsed.query}" if parsed.query else ""
