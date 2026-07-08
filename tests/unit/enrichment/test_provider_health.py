"""Unit tests for provider_health's pure transition functions and
ProviderHealthTracker."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.enrichment_models import ProviderHealthStatus
from lead_intelligence.application.enrichment.provider_health import (
    ProviderHealthTracker,
    initial_health,
    record_failure,
    record_success,
)


def _now() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_initial_health_is_unknown_with_no_history() -> None:
    health = initial_health("news")

    assert health.status is ProviderHealthStatus.UNKNOWN
    assert health.consecutive_failures == 0
    assert health.last_success_at is None
    assert health.last_failure_at is None


def test_record_success_resets_failure_streak_and_marks_healthy() -> None:
    health = initial_health("news")
    failed_once = record_failure(health, _now(), "boom")

    healthy = record_success(failed_once, _now())

    assert healthy.status is ProviderHealthStatus.HEALTHY
    assert healthy.consecutive_failures == 0
    assert healthy.last_error is None
    assert healthy.last_success_at == _now()


def test_record_success_preserves_last_failure_at() -> None:
    health = initial_health("news")
    failure_time = _now()
    failed = record_failure(health, failure_time, "boom")

    healthy = record_success(failed, _now())

    assert healthy.last_failure_at == failure_time


def test_single_failure_is_degraded_not_unhealthy() -> None:
    health = initial_health("news")

    updated = record_failure(health, _now(), "boom", unhealthy_threshold=3)

    assert updated.status is ProviderHealthStatus.DEGRADED
    assert updated.consecutive_failures == 1


def test_failures_reaching_threshold_become_unhealthy() -> None:
    health = initial_health("news")

    for _ in range(3):
        health = record_failure(health, _now(), "boom", unhealthy_threshold=3)

    assert health.status is ProviderHealthStatus.UNHEALTHY
    assert health.consecutive_failures == 3


def test_tracker_get_defaults_to_unknown_for_unseen_provider() -> None:
    tracker = ProviderHealthTracker()

    assert tracker.get("news").status is ProviderHealthStatus.UNKNOWN
    assert tracker.is_available("news") is True


def test_tracker_is_available_becomes_false_once_unhealthy() -> None:
    tracker = ProviderHealthTracker(unhealthy_threshold=2)

    tracker.record_failure("news", _now(), "boom")
    assert tracker.is_available("news") is True

    tracker.record_failure("news", _now(), "boom")
    assert tracker.is_available("news") is False


def test_tracker_record_success_recovers_availability() -> None:
    tracker = ProviderHealthTracker(unhealthy_threshold=1)
    tracker.record_failure("news", _now(), "boom")
    assert tracker.is_available("news") is False

    tracker.record_success("news", _now())

    assert tracker.is_available("news") is True
    assert tracker.get("news").status is ProviderHealthStatus.HEALTHY


def test_tracker_tracks_providers_independently() -> None:
    tracker = ProviderHealthTracker(unhealthy_threshold=1)

    tracker.record_failure("news", _now(), "boom")

    assert tracker.is_available("news") is False
    assert tracker.is_available("dnb") is True
