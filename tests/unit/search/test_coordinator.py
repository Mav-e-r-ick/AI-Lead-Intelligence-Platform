"""End-to-end unit tests for SearchCoordinator, using FakeSearchProvider
instead of any real provider."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pytest

from lead_intelligence.application.dto.enrichment_models import (
    ProviderHealthStatus,
    ProviderPriority,
    SkipReason,
)
from lead_intelligence.application.dto.search_models import (
    EnrichmentStatus,
    ProviderSkip,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SubjectType,
)
from lead_intelligence.application.enrichment.provider_health import (
    ProviderHealthTracker,
)
from lead_intelligence.application.search.config import (
    SearchProfile,
    SearchProviderConfiguration,
)
from lead_intelligence.application.search.coordinator import SearchCoordinator
from lead_intelligence.application.search.provider_registry import (
    SearchProviderRegistry,
)
from lead_intelligence.domain.exceptions import InvalidSearchConfigurationError
from tests.unit.search.fixtures import FakeSearchProvider


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _id_factory() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def factory() -> str:
        return f"req-{next(counter)}"

    return factory


def _coordinator(
    providers: list[FakeSearchProvider],
    profile: SearchProfile,
    health_tracker: ProviderHealthTracker | None = None,
) -> SearchCoordinator:
    return SearchCoordinator(
        SearchProviderRegistry(providers),
        profile,
        health_tracker=health_tracker,
        id_factory=_id_factory(),
        clock=_fixed_clock,
    )


def _result_response(provider_id: str, request: SearchRequest) -> SearchResponse:
    return SearchResponse(
        provider_id=provider_id,
        request_id=request.request_id,
        subject_id=request.subject_id,
        status=EnrichmentStatus.SUCCESS,
        results=(
            # Distinct URL per provider_id: two different real providers
            # finding two different pages is the normal case this fixture
            # models. A test that specifically wants two providers to
            # report the *same* URL (to exercise dedup_and_rank via the
            # coordinator) builds that overlap explicitly instead — see
            # TestMergeDedupAndRank below.
            SearchResult(
                title="t",
                url=f"https://example.com/{provider_id}",
                snippet="s",
                source=provider_id,
                rank=1,
            ),
        ),
        error_message=None,
        started_at=request.requested_at,
        completed_at=request.requested_at,
    )


def test_executes_providers_in_ascending_priority_order() -> None:
    order: list[str] = []

    def handler(provider_id: str) -> Callable[[SearchRequest], SearchResponse]:
        def _handler(request: SearchRequest) -> SearchResponse:
            order.append(provider_id)
            return _result_response(provider_id, request)

        return _handler

    low = FakeSearchProvider("low", handler=handler("low"))
    high = FakeSearchProvider("high", handler=handler("high"))
    medium = FakeSearchProvider("medium", handler=handler("medium"))
    profile = SearchProfile(
        name="t",
        provider_configurations={
            "low": SearchProviderConfiguration(priority=ProviderPriority.LOW),
            "high": SearchProviderConfiguration(priority=ProviderPriority.HIGH),
            "medium": SearchProviderConfiguration(priority=ProviderPriority.MEDIUM),
        },
    )
    coordinator = _coordinator([low, high, medium], profile)

    coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert order == ["high", "medium", "low"]


def test_same_priority_providers_break_ties_by_provider_id() -> None:
    order: list[str] = []

    def make_handler(provider_id: str) -> Callable[[SearchRequest], SearchResponse]:
        def _handler(request: SearchRequest) -> SearchResponse:
            order.append(provider_id)
            return _result_response(provider_id, request)

        return _handler

    zeta = FakeSearchProvider("zeta", handler=make_handler("zeta"))
    alpha = FakeSearchProvider("alpha", handler=make_handler("alpha"))
    profile = SearchProfile(name="t")
    coordinator = _coordinator([zeta, alpha], profile)

    coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert order == ["alpha", "zeta"]


def test_disabled_provider_is_skipped_and_never_called() -> None:
    provider = FakeSearchProvider("browser_search")
    profile = SearchProfile(
        name="t",
        provider_configurations={
            "browser_search": SearchProviderConfiguration(enabled=False)
        },
    )
    coordinator = _coordinator([provider], profile)

    result = coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert provider.calls == []
    assert len(result.skipped_providers) == 1
    assert result.skipped_providers[0].provider_id == "browser_search"
    assert result.skipped_providers[0].reason is SkipReason.DISABLED
    assert result.metrics.providers_executed == 0
    assert result.metrics.providers_skipped == 1


def test_unsupported_subject_type_provider_is_never_considered_or_skipped() -> None:
    person_only = FakeSearchProvider(
        "browser_search", supported_subject_types=frozenset({SubjectType.PERSON})
    )
    profile = SearchProfile(name="t")
    coordinator = _coordinator([person_only], profile)

    result = coordinator.search(SubjectType.COMPANY, "company-1", {})

    assert person_only.calls == []
    assert result.skipped_providers == ()
    assert result.metrics.providers_considered == 0


def test_provider_skipped_when_unhealthy() -> None:
    provider = FakeSearchProvider("browser_search")
    profile = SearchProfile(name="t")
    tracker = ProviderHealthTracker(unhealthy_threshold=1)
    tracker.record_failure("browser_search", _fixed_clock(), "boom")
    coordinator = _coordinator([provider], profile, health_tracker=tracker)

    result = coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert provider.calls == []
    assert result.skipped_providers[0].reason is SkipReason.UNHEALTHY


def test_provider_raising_is_treated_as_failure_and_does_not_stop_others() -> None:
    broken = FakeSearchProvider("broken", raises=RuntimeError("boom"))
    working = FakeSearchProvider(
        "working", handler=lambda request: _result_response("working", request)
    )
    profile = SearchProfile(
        name="t",
        provider_configurations={
            "broken": SearchProviderConfiguration(priority=ProviderPriority.HIGH),
            "working": SearchProviderConfiguration(priority=ProviderPriority.LOW),
        },
    )
    coordinator = _coordinator([broken, working], profile)

    result = coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert len(result.provider_responses) == 2
    broken_response = next(
        r for r in result.provider_responses if r.provider_id == "broken"
    )
    assert broken_response.status is EnrichmentStatus.FAILURE
    assert broken_response.error_message == "boom"
    assert len(result.results) == 1
    assert result.metrics.providers_succeeded == 1
    assert result.metrics.providers_failed == 1


def test_results_are_aggregated_across_providers() -> None:
    a = FakeSearchProvider("a", handler=lambda request: _result_response("a", request))
    b = FakeSearchProvider("b", handler=lambda request: _result_response("b", request))
    coordinator = _coordinator([a, b], SearchProfile(name="t"))

    result = coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert len(result.results) == 2
    assert {r.source for r in result.results} == {"a", "b"}


def test_health_tracker_updated_after_success_and_failure() -> None:
    broken = FakeSearchProvider("broken", raises=RuntimeError("boom"))
    working = FakeSearchProvider("working")
    tracker = ProviderHealthTracker()
    coordinator = _coordinator([broken, working], SearchProfile(name="t"), tracker)

    coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert tracker.get("working").status is ProviderHealthStatus.HEALTHY
    assert tracker.get("broken").status is ProviderHealthStatus.DEGRADED
    assert tracker.get("broken").last_error == "boom"


def test_invalid_profile_raises_before_any_provider_executes() -> None:
    provider = FakeSearchProvider("browser_search")
    invalid_profile = SearchProfile(
        name="broken",
        default_configuration=SearchProviderConfiguration(timeout_seconds=0),
    )
    coordinator = _coordinator([provider], invalid_profile)

    with pytest.raises(InvalidSearchConfigurationError):
        coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert provider.calls == []


def test_known_attributes_are_passed_through() -> None:
    provider = FakeSearchProvider("browser_search")
    coordinator = _coordinator([provider], SearchProfile(name="t"))

    coordinator.search(
        SubjectType.PERSON, "subject-1", {"first_name": "Ada", "last_name": "Lovelace"}
    )

    assert len(provider.calls) == 1
    request = provider.calls[0]
    assert request.known_attributes == {"first_name": "Ada", "last_name": "Lovelace"}
    assert request.subject_id == "subject-1"
    assert request.subject_type is SubjectType.PERSON


def test_metrics_reflect_a_mixed_run() -> None:
    executed = FakeSearchProvider("executed")
    disabled = FakeSearchProvider("disabled")
    profile = SearchProfile(
        name="t",
        provider_configurations={
            "disabled": SearchProviderConfiguration(enabled=False)
        },
    )
    coordinator = _coordinator([executed, disabled], profile)

    result = coordinator.search(SubjectType.PERSON, "subject-1", {})

    assert result.metrics.providers_considered == 2
    assert result.metrics.providers_executed == 1
    assert result.metrics.providers_succeeded == 1
    assert result.metrics.providers_failed == 0
    assert result.metrics.providers_skipped == 1
    assert result.metrics.execution_time_total_ms >= 0.0
    assert result.duration_ms >= 0.0


def test_coordination_is_deterministic_given_the_same_inputs() -> None:
    def build() -> SearchCoordinator:
        provider = FakeSearchProvider(
            "a", handler=lambda request: _result_response("a", request)
        )
        return _coordinator([provider], SearchProfile(name="t"))

    result_a = build().search(SubjectType.PERSON, "subject-1", {"first_name": "Ada"})
    result_b = build().search(SubjectType.PERSON, "subject-1", {"first_name": "Ada"})

    assert result_a.results == result_b.results
    assert result_a.provider_responses == result_b.provider_responses
    # execution_time_total_ms is a real wall-clock measurement (time.perf_counter)
    # and is deliberately excluded from the determinism guarantee, exactly like
    # the Enrichment Provider Framework's own metrics.execution_time_total_ms.
    assert result_a.metrics.providers_executed == result_b.metrics.providers_executed
    assert result_a.metrics.results_collected == result_b.metrics.results_collected


def _empty_response(provider_id: str, request: SearchRequest) -> SearchResponse:
    return SearchResponse(
        provider_id=provider_id,
        request_id=request.request_id,
        subject_id=request.subject_id,
        status=EnrichmentStatus.SUCCESS,
        results=(),
        error_message=None,
        started_at=request.requested_at,
        completed_at=request.requested_at,
    )


class TestFallbackOnly:
    """SearchProviderConfiguration.fallback_only — a provider configured
    with it only runs when no higher-priority provider already produced a
    result in the same search() call (CompanyCrawlerProvider/
    BrowserSearchProvider's real-world use of this)."""

    def test_fallback_provider_is_skipped_when_primary_already_has_results(
        self,
    ) -> None:
        primary = FakeSearchProvider(
            "primary", handler=lambda request: _result_response("primary", request)
        )
        fallback = FakeSearchProvider("fallback")
        profile = SearchProfile(
            name="t",
            provider_configurations={
                "primary": SearchProviderConfiguration(priority=ProviderPriority.HIGH),
                "fallback": SearchProviderConfiguration(
                    priority=ProviderPriority.LOW, fallback_only=True
                ),
            },
        )
        coordinator = _coordinator([primary, fallback], profile)

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert fallback.calls == []
        assert result.skipped_providers == (
            ProviderSkip(
                provider_id="fallback",
                reason=SkipReason.FALLBACK_NOT_NEEDED,
                detail=(
                    "1 result(s) already collected from higher-priority "
                    "provider(s); this fallback provider was not needed."
                ),
            ),
        )

    def test_fallback_provider_runs_when_primary_yields_nothing(self) -> None:
        primary = FakeSearchProvider(
            "primary", handler=lambda request: _empty_response("primary", request)
        )
        fallback = FakeSearchProvider(
            "fallback", handler=lambda request: _result_response("fallback", request)
        )
        profile = SearchProfile(
            name="t",
            provider_configurations={
                "primary": SearchProviderConfiguration(priority=ProviderPriority.HIGH),
                "fallback": SearchProviderConfiguration(
                    priority=ProviderPriority.LOW, fallback_only=True
                ),
            },
        )
        coordinator = _coordinator([primary, fallback], profile)

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert len(fallback.calls) == 1
        assert len(result.results) == 1
        assert result.results[0].source == "fallback"

    def test_fallback_provider_runs_when_it_is_the_only_provider(self) -> None:
        fallback = FakeSearchProvider(
            "fallback", handler=lambda request: _result_response("fallback", request)
        )
        profile = SearchProfile(
            name="t",
            provider_configurations={
                "fallback": SearchProviderConfiguration(fallback_only=True),
            },
        )
        coordinator = _coordinator([fallback], profile)

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert len(fallback.calls) == 1
        assert len(result.results) == 1

    def test_default_fallback_only_is_false_and_never_skips(self) -> None:
        """Backward compatibility: a provider with no explicit
        fallback_only configuration always runs, exactly like before this
        field existed."""

        primary = FakeSearchProvider(
            "primary", handler=lambda request: _result_response("primary", request)
        )
        other = FakeSearchProvider(
            "other", handler=lambda request: _result_response("other", request)
        )
        profile = SearchProfile(
            name="t",
            provider_configurations={
                "primary": SearchProviderConfiguration(priority=ProviderPriority.HIGH),
                "other": SearchProviderConfiguration(priority=ProviderPriority.LOW),
            },
        )
        coordinator = _coordinator([primary, other], profile)

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert len(other.calls) == 1
        assert result.skipped_providers == ()


def _confident_response(
    provider_id: str, url: str, confidence: float, request: SearchRequest
) -> SearchResponse:
    return SearchResponse(
        provider_id=provider_id,
        request_id=request.request_id,
        subject_id=request.subject_id,
        status=EnrichmentStatus.SUCCESS,
        results=(
            SearchResult(
                title="t", url=url, snippet="s", source=provider_id, rank=1,
                confidence=confidence,
            ),
        ),
        error_message=None,
        started_at=request.requested_at,
        completed_at=request.requested_at,
    )


class TestMergeDedupAndRank:
    """SearchCoordinator.search() merges every executed provider's
    results, deduplicates same-URL results (keeping the highest-confidence
    copy), and ranks the survivors by confidence descending — the
    Federated Search redesign's replacement for the old "first provider
    wins" fallback architecture. See application/search/result_merging.py
    for the pure logic under test here through the coordinator."""

    def test_two_providers_reporting_the_same_url_collapse_to_one_result(self) -> None:
        low = FakeSearchProvider(
            "google_web_search",
            handler=lambda request: _confident_response(
                "google_web_search", "https://reuters.com/x", 0.80, request
            ),
        )
        high = FakeSearchProvider(
            "news_search",
            handler=lambda request: _confident_response(
                "news_search", "https://reuters.com/x", 0.94, request
            ),
        )
        coordinator = _coordinator([low, high], SearchProfile(name="t"))

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert len(result.results) == 1
        assert result.results[0].source == "news_search"
        assert result.results[0].confidence == 0.94
        # Both providers still ran and both are still reflected individually
        # in provider_responses — only the merged `.results` view collapses.
        assert len(result.provider_responses) == 2

    def test_distinct_urls_from_every_provider_are_all_kept_and_ranked_by_confidence(
        self,
    ) -> None:
        crawler = FakeSearchProvider(
            "company_crawler",
            handler=lambda request: _confident_response(
                "company_crawler", "https://acme.com/team", 1.00, request
            ),
        )
        google = FakeSearchProvider(
            "google_web_search",
            handler=lambda request: _confident_response(
                "google_web_search", "https://example.com/article", 0.80, request
            ),
        )
        press = FakeSearchProvider(
            "press_release",
            handler=lambda request: _confident_response(
                "press_release", "https://acme.com/press/1", 0.95, request
            ),
        )
        coordinator = _coordinator([crawler, google, press], SearchProfile(name="t"))

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert [r.source for r in result.results] == [
            "company_crawler",
            "press_release",
            "google_web_search",
        ]

    def test_results_collected_metric_reflects_the_deduplicated_count(self) -> None:
        a = FakeSearchProvider(
            "a",
            handler=lambda request: _confident_response(
                "a", "https://acme.com/x", 0.80, request
            ),
        )
        b = FakeSearchProvider(
            "b",
            handler=lambda request: _confident_response(
                "b", "https://acme.com/x", 0.90, request
            ),
        )
        coordinator = _coordinator([a, b], SearchProfile(name="t"))

        result = coordinator.search(SubjectType.PERSON, "subject-1", {})

        assert result.metrics.results_collected == 1
        assert len(result.results) == 1
