"""End-to-end unit tests for EnrichmentCoordinator, using
FakeEnrichmentProvider instead of any real (not-yet-built) provider."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest

from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ProviderHealthStatus,
    ProviderPriority,
    SkipReason,
    SubjectType,
)
from lead_intelligence.application.enrichment.config import (
    EnrichmentProfile,
    ProviderConfiguration,
    RefreshPolicy,
)
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_health import (
    ProviderHealthTracker,
)
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.domain.exceptions import InvalidEnrichmentConfigurationError
from tests.unit.enrichment.fixtures import FakeEnrichmentProvider, make_observation


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _id_factory() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def factory() -> str:
        return f"req-{next(counter)}"

    return factory


def _coordinator(
    providers: list[FakeEnrichmentProvider],
    profile: EnrichmentProfile,
    health_tracker: ProviderHealthTracker | None = None,
) -> EnrichmentCoordinator:
    return EnrichmentCoordinator(
        ProviderRegistry(providers),
        profile,
        health_tracker=health_tracker,
        id_factory=_id_factory(),
        clock=_fixed_clock,
    )


def test_executes_providers_in_ascending_priority_order() -> None:
    order: list[str] = []

    def handler(provider_id: str) -> Callable[[EnrichmentRequest], EnrichmentResponse]:
        def _handler(request: EnrichmentRequest) -> EnrichmentResponse:
            order.append(provider_id)
            return EnrichmentResponse(
                provider_id=provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                status=EnrichmentStatus.SUCCESS,
                observations=(),
                error_message=None,
                started_at=request.requested_at,
                completed_at=request.requested_at,
            )

        return _handler

    low = FakeEnrichmentProvider("low", handler=handler("low"))
    high = FakeEnrichmentProvider("high", handler=handler("high"))
    medium = FakeEnrichmentProvider("medium", handler=handler("medium"))
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={
            "low": ProviderConfiguration(priority=ProviderPriority.LOW),
            "high": ProviderConfiguration(priority=ProviderPriority.HIGH),
            "medium": ProviderConfiguration(priority=ProviderPriority.MEDIUM),
        },
    )
    coordinator = _coordinator([low, high, medium], profile)

    coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert order == ["high", "medium", "low"]


def test_same_priority_providers_break_ties_by_provider_id() -> None:
    order: list[str] = []

    def make_handler(
        provider_id: str,
    ) -> Callable[[EnrichmentRequest], EnrichmentResponse]:
        def _handler(request: EnrichmentRequest) -> EnrichmentResponse:
            order.append(provider_id)
            return EnrichmentResponse(
                provider_id=provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                status=EnrichmentStatus.SUCCESS,
                observations=(),
                error_message=None,
                started_at=request.requested_at,
                completed_at=request.requested_at,
            )

        return _handler

    zeta = FakeEnrichmentProvider("zeta", handler=make_handler("zeta"))
    alpha = FakeEnrichmentProvider("alpha", handler=make_handler("alpha"))
    profile = EnrichmentProfile(name="t")
    coordinator = _coordinator([zeta, alpha], profile)

    coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert order == ["alpha", "zeta"]


def test_disabled_provider_is_skipped_and_never_called() -> None:
    provider = FakeEnrichmentProvider("news")
    profile = EnrichmentProfile(
        name="t", provider_configurations={"news": ProviderConfiguration(enabled=False)}
    )
    coordinator = _coordinator([provider], profile)

    result = coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert provider.calls == []
    assert len(result.skipped_providers) == 1
    assert result.skipped_providers[0].provider_id == "news"
    assert result.skipped_providers[0].reason is SkipReason.DISABLED
    assert result.metrics.providers_executed == 0
    assert result.metrics.providers_skipped == 1


def test_unsupported_subject_type_provider_is_never_considered_or_skipped() -> None:
    person_only = FakeEnrichmentProvider(
        "leadership_page", supported_subject_types=frozenset({SubjectType.PERSON})
    )
    profile = EnrichmentProfile(name="t")
    coordinator = _coordinator([person_only], profile)

    result = coordinator.enrich(SubjectType.COMPANY, "company-1", {})

    assert person_only.calls == []
    assert result.skipped_providers == ()
    assert result.metrics.providers_considered == 0


def test_provider_skipped_when_not_yet_stale() -> None:
    provider = FakeEnrichmentProvider("news")
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={
            "news": ProviderConfiguration(
                refresh_policy=RefreshPolicy(max_age=timedelta(days=30))
            )
        },
    )
    coordinator = _coordinator([provider], profile)
    recently_fetched = _fixed_clock() - timedelta(days=1)

    result = coordinator.enrich(
        SubjectType.PERSON,
        "twin-1",
        {},
        provider_last_fetched={"news": recently_fetched},
    )

    assert provider.calls == []
    assert result.skipped_providers[0].reason is SkipReason.NOT_STALE


def test_provider_runs_when_stale() -> None:
    provider = FakeEnrichmentProvider("news")
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={
            "news": ProviderConfiguration(
                refresh_policy=RefreshPolicy(max_age=timedelta(days=30))
            )
        },
    )
    coordinator = _coordinator([provider], profile)
    long_ago = _fixed_clock() - timedelta(days=31)

    result = coordinator.enrich(
        SubjectType.PERSON, "twin-1", {}, provider_last_fetched={"news": long_ago}
    )

    assert len(provider.calls) == 1
    assert result.metrics.providers_executed == 1


def test_provider_skipped_when_unhealthy() -> None:
    provider = FakeEnrichmentProvider("news")
    profile = EnrichmentProfile(name="t")
    tracker = ProviderHealthTracker(unhealthy_threshold=1)
    tracker.record_failure("news", _fixed_clock(), "boom")
    coordinator = _coordinator([provider], profile, health_tracker=tracker)

    result = coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert provider.calls == []
    assert result.skipped_providers[0].reason is SkipReason.UNHEALTHY


def test_provider_raising_is_treated_as_failure_and_does_not_stop_others() -> None:
    broken = FakeEnrichmentProvider("broken", raises=RuntimeError("boom"))
    working = FakeEnrichmentProvider(
        "working",
        handler=lambda request: EnrichmentResponse(
            provider_id="working",
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=EnrichmentStatus.SUCCESS,
            observations=(
                make_observation("twin-1", "title", "CEO", "working", _fixed_clock()),
            ),
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={
            "broken": ProviderConfiguration(priority=ProviderPriority.HIGH),
            "working": ProviderConfiguration(priority=ProviderPriority.LOW),
        },
    )
    coordinator = _coordinator([broken, working], profile)

    result = coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert len(result.provider_responses) == 2
    broken_response = next(
        r for r in result.provider_responses if r.provider_id == "broken"
    )
    assert broken_response.status is EnrichmentStatus.FAILURE
    assert broken_response.error_message == "boom"
    assert len(result.observations) == 1
    assert result.metrics.providers_succeeded == 1
    assert result.metrics.providers_failed == 1


def test_observations_are_aggregated_across_providers() -> None:
    a = FakeEnrichmentProvider(
        "a",
        handler=lambda request: EnrichmentResponse(
            provider_id="a",
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=EnrichmentStatus.SUCCESS,
            observations=(
                make_observation("twin-1", "title", "CEO", "a", _fixed_clock()),
            ),
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    b = FakeEnrichmentProvider(
        "b",
        handler=lambda request: EnrichmentResponse(
            provider_id="b",
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=EnrichmentStatus.SUCCESS,
            observations=(
                make_observation("twin-1", "company_name", "Acme", "b", _fixed_clock()),
            ),
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    coordinator = _coordinator([a, b], EnrichmentProfile(name="t"))

    result = coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert len(result.observations) == 2
    assert {o.attribute for o in result.observations} == {"title", "company_name"}


def test_health_tracker_updated_after_success_and_failure() -> None:
    broken = FakeEnrichmentProvider("broken", raises=RuntimeError("boom"))
    working = FakeEnrichmentProvider("working")
    tracker = ProviderHealthTracker()
    coordinator = _coordinator([broken, working], EnrichmentProfile(name="t"), tracker)

    coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert tracker.get("working").status is ProviderHealthStatus.HEALTHY
    assert tracker.get("broken").status is ProviderHealthStatus.DEGRADED
    assert tracker.get("broken").last_error == "boom"


def test_invalid_profile_raises_before_any_provider_executes() -> None:
    provider = FakeEnrichmentProvider("news")
    invalid_profile = EnrichmentProfile(
        name="broken", default_configuration=ProviderConfiguration(timeout_seconds=0)
    )
    coordinator = _coordinator([provider], invalid_profile)

    with pytest.raises(InvalidEnrichmentConfigurationError):
        coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert provider.calls == []


def test_known_attributes_and_attributes_of_interest_are_passed_through() -> None:
    provider = FakeEnrichmentProvider("news")
    coordinator = _coordinator([provider], EnrichmentProfile(name="t"))

    coordinator.enrich(
        SubjectType.PERSON,
        "twin-1",
        {"full_name": "Ada Lovelace"},
        attributes_of_interest=("title", "email"),
    )

    assert len(provider.calls) == 1
    request = provider.calls[0]
    assert request.known_attributes == {"full_name": "Ada Lovelace"}
    assert request.attributes_of_interest == ("title", "email")
    assert request.subject_id == "twin-1"
    assert request.subject_type is SubjectType.PERSON


def test_metrics_reflect_a_mixed_run() -> None:
    executed = FakeEnrichmentProvider("executed")
    disabled = FakeEnrichmentProvider("disabled")
    profile = EnrichmentProfile(
        name="t",
        provider_configurations={"disabled": ProviderConfiguration(enabled=False)},
    )
    coordinator = _coordinator([executed, disabled], profile)

    result = coordinator.enrich(SubjectType.PERSON, "twin-1", {})

    assert result.metrics.providers_considered == 2
    assert result.metrics.providers_executed == 1
    assert result.metrics.providers_succeeded == 1
    assert result.metrics.providers_failed == 0
    assert result.metrics.providers_skipped == 1
    assert result.metrics.execution_time_total_ms >= 0.0
    assert result.duration_ms >= 0.0


def test_coordination_is_deterministic_given_the_same_inputs() -> None:
    def build() -> EnrichmentCoordinator:
        provider = FakeEnrichmentProvider(
            "a",
            handler=lambda request: EnrichmentResponse(
                provider_id="a",
                request_id=request.request_id,
                subject_id=request.subject_id,
                status=EnrichmentStatus.SUCCESS,
                observations=(
                    make_observation("twin-1", "title", "CEO", "a", _fixed_clock()),
                ),
                error_message=None,
                started_at=request.requested_at,
                completed_at=request.requested_at,
            ),
        )
        return _coordinator([provider], EnrichmentProfile(name="t"))

    result_a = build().enrich(SubjectType.PERSON, "twin-1", {"full_name": "Ada"})
    result_b = build().enrich(SubjectType.PERSON, "twin-1", {"full_name": "Ada"})

    assert result_a.observations == result_b.observations
    assert result_a.provider_responses == result_b.provider_responses
    # execution_time_total_ms is a real wall-clock measurement (time.perf_counter)
    # and is deliberately excluded from the determinism guarantee, exactly like
    # the Identity Resolution Engine's own metrics.execution_time_total_ms.
    assert result_a.metrics.providers_executed == result_b.metrics.providers_executed
    assert (
        result_a.metrics.observations_collected
        == result_b.metrics.observations_collected
    )
