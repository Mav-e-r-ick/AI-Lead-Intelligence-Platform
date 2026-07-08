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
            SearchResult(
                title="t",
                url="https://example.com",
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
