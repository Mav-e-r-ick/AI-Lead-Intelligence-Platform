"""Plain data shapes produced by the Search Layer.

WHY THIS FILE EXISTS (SEPARATE FROM enrichment_models.py):
Per the approved Search Layer RFC, "search" and "extraction" are two
distinct stages: a search provider answers "what URLs exist for this
query," never "what does this page mean." Reusing `EnrichmentRequest`/
`EnrichmentResponse`/`ObservationCandidate` for that would re-couple the
two concerns the RFC exists to separate. This file is the Search Layer's
own vocabulary — deliberately small, since a search provider's job is
narrow: turn a query into a list of results.

WHY SearchResult NOW ALSO CARRIES `confidence` (REVISITING THE ORIGINAL
"EXACTLY title/url/snippet/source/rank" RULE):
The original RFC's Version 1 scope deliberately excluded any field beyond
the literal five (see the RFC's Open Question 3) — adding more would have
been an unauthorized redesign at the time. The Federated Search redesign
(replacing the single-primary-provider architecture with multiple
independent providers run every time, per-request) is a different,
explicitly authorized task: with several providers now legitimately
finding the same underlying evidence (a news article, a press release, a
LinkedIn profile), `SearchCoordinator` needs a way to both deduplicate
overlapping results and prefer the most trustworthy source among
survivors — see `application/search/confidence.py` and
`application/search/result_merging.py`. `confidence` defaults to `1.0` so
any code constructing a `SearchResult` without naming it (existing tests,
a future minimal provider) keeps behaving exactly as if every result were
maximally trusted — the same "unset means don't change today's behavior"
rule this platform already applies to `fallback_only`.

WHY status/health/skip TYPES ARE REUSED FROM enrichment_models.py, NOT
REDEFINED:
`EnrichmentStatus`, `ProviderHealth`, `ProviderHealthStatus`, `ProviderSkip`,
and `SkipReason` are already generic, provider-family-agnostic vocabulary —
none of them mention enrichment-specific concepts. Per the same "no second
parallel vocabulary for the same concept" principle already applied to
`SubjectType`, the Search Layer reuses them directly rather than defining
byte-for-byte identical duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping

from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentStatus,
    ProviderSkip,
    SubjectType,
)

__all__ = [
    "SubjectType",
    "EnrichmentStatus",
    "ProviderSkip",
    "SearchResult",
    "SearchRequest",
    "SearchResponse",
    "SearchCoordinationMetrics",
    "SearchCoordinationResult",
]


@dataclass(frozen=True)
class SearchResult:
    """One result a search provider found for one query.

    Attributes:
        title: The result's page title, as reported by the search
            provider — never fetched or re-derived from the page itself.
        url: The result's URL.
        snippet: The result's search-snippet excerpt, as reported by the
            search provider.
        source: Which search provider produced this result (e.g.
            "google_search", "browser_search") — not the result's own
            destination domain, which stays derivable from `url` by
            whichever downstream stage needs it.
        rank: 1-indexed position of this result within the query that
            produced it (the provider's own ranking, never re-sorted here
            by the provider itself — `SearchCoordinator` is the one place
            results from *different* providers get reordered, by
            `confidence`).
        confidence: How much this result should be trusted relative to
            results from other providers, in [0.0, 1.0] — assigned by the
            provider that produced it (see `application/search/
            confidence.py` for the shared, documented scoring table every
            federated provider uses). Defaults to `1.0`: a provider or
            test that never sets this is unaffected by
            `SearchCoordinator`'s confidence-based dedup/ranking, exactly
            as if that step didn't exist.
    """

    title: str
    url: str
    snippet: str
    source: str
    rank: int
    confidence: float = 1.0


@dataclass(frozen=True)
class SearchRequest:
    """What the coordinator asks every applicable search provider to fulfill.

    Deliberately the same shape as `EnrichmentRequest` — a search provider
    needs to know exactly what an enrichment provider needs to know (which
    subject, what's already known about them), just not what to do with
    the answer.

    Attributes:
        request_id: Opaque, traceable id for this request.
        subject_type: Person or Company.
        subject_id: The Digital Twin id (or provisional identity id) this
            request is about. Opaque to this framework.
        known_attributes: Canonical field name -> known value (e.g.
            {"first_name": "Ada", "last_name": "Lovelace", "company_name":
            "Acme Corp"}), giving a provider enough to build queries from.
        requested_at: When this request was built.
    """

    request_id: str
    subject_type: SubjectType
    subject_id: str
    known_attributes: Mapping[str, str]
    requested_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "known_attributes", MappingProxyType(dict(self.known_attributes))
        )


@dataclass(frozen=True)
class SearchResponse:
    """One provider's answer to one SearchRequest."""

    provider_id: str
    request_id: str
    subject_id: str
    status: EnrichmentStatus
    results: tuple[SearchResult, ...]
    error_message: str | None
    started_at: datetime
    completed_at: datetime

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of this provider's search() call, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass(frozen=True)
class SearchCoordinationMetrics:
    """Aggregate metrics for one SearchCoordinator.search() run."""

    providers_considered: int
    providers_executed: int
    providers_succeeded: int
    providers_failed: int
    providers_skipped: int
    results_collected: int
    execution_time_total_ms: float


@dataclass(frozen=True)
class SearchCoordinationResult:
    """The Search Layer's single combined output type for one subject.

    Attributes:
        subject_id: The Digital Twin (or provisional identity) id searched.
        subject_type: Person or Company.
        provider_responses: Every executed provider's individual response,
            in execution order.
        results: Every SearchResult from every executed provider,
            flattened into one run-wide sequence — a convenience view; the
            same results also live on each response.
        skipped_providers: Every applicable-but-not-executed provider,
            with why. Reuses `ProviderSkip`/`SkipReason` from
            enrichment_models.py.
        started_at: When coordination began.
        completed_at: When coordination finished.
        metrics: The raw numbers this result's shape is built from.
    """

    subject_id: str
    subject_type: SubjectType
    provider_responses: tuple[SearchResponse, ...]
    results: tuple[SearchResult, ...]
    skipped_providers: tuple[ProviderSkip, ...]
    started_at: datetime
    completed_at: datetime
    metrics: SearchCoordinationMetrics

    @property
    def duration_ms(self) -> float:
        """Wall-clock duration of the whole coordination run, in milliseconds."""

        return (self.completed_at - self.started_at).total_seconds() * 1000
