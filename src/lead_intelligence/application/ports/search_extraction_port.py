"""SearchExtractionPort: what the application layer needs from a search
extraction engine — turning SearchResults into ObservationCandidates.

WHY THIS IS A typing.Protocol, NOT AN ABC LIKE THE OTHER PORTS:
The concrete implementation (infrastructure/search/extraction/engine.py's
SearchExtractionEngine) already exists, fully built and tested, with
exactly this method signature. A structural Protocol lets the
ExecutiveProcessingOrchestrator depend on the *shape* without the
infrastructure class having to be modified to inherit anything — which
keeps this task's "only connect the existing modules, do not redesign
any of them" constraint literal: zero lines of the extraction engine
change. (The other ports are ABCs because they were defined *before*
their implementations; this one is being defined after.)

WHY THIS PORT EXISTS AT ALL:
application/ code must never import from infrastructure/ (see
application/README.md's rule) — but the pipeline's orchestrator needs to
call the Search Extraction Engine. This port is the seam that keeps the
dependency pointing inward: the orchestrator depends on this interface,
and the infrastructure engine satisfies it structurally.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.search_models import SearchResult


class SearchExtractionPort(Protocol):
    """Anything that can turn SearchResults into ObservationCandidates."""

    def extract(
        self, subject_id: str, search_results: Sequence[SearchResult]
    ) -> tuple[ObservationCandidate, ...]:
        """Fetch every search result's page and return every observation
        the pages yielded. Must not raise for ordinary failure modes (an
        unreachable page contributes nothing); an actual raised exception
        is still handled safely by the orchestrator's own stage guard."""
        ...
