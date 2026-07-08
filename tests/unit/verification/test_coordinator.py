"""End-to-end unit tests for VerificationCoordinator, using
FakeVerificationProvider instead of any real (not-yet-built) provider."""

from __future__ import annotations

from typing import Callable

import pytest

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationRequest,
    VerificationResult,
    VerificationSkipReason,
    VerificationStatus,
)
from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.application.verification.config import (
    VerificationProfile,
    VerificationProviderConfiguration,
)
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.domain.exceptions import (
    DuplicateVerificationProviderError,
    InvalidVerificationConfigurationError,
)
from tests.unit.verification.fixtures import FakeVerificationProvider, fixed_clock


def _id_factory() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def factory() -> str:
        return f"req-{next(counter)}"

    return factory


def _coordinator(
    providers: list[FakeVerificationProvider], profile: VerificationProfile
) -> VerificationCoordinator:
    return VerificationCoordinator(
        providers, profile, id_factory=_id_factory(), clock=fixed_clock
    )


def test_executes_providers_in_ascending_priority_order() -> None:
    order: list[str] = []

    def handler(
        provider_id: str,
    ) -> Callable[[VerificationRequest], VerificationResult]:
        def _handler(request: VerificationRequest) -> VerificationResult:
            order.append(provider_id)
            return VerificationResult(
                provider_id=provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                contact_type=request.contact_type,
                value=request.value,
                status=VerificationStatus.VALID,
                confidence=None,
                reason=None,
                error_message=None,
                started_at=request.requested_at,
                completed_at=request.requested_at,
            )

        return _handler

    low = FakeVerificationProvider("low", handler=handler("low"))
    high = FakeVerificationProvider("high", handler=handler("high"))
    medium = FakeVerificationProvider("medium", handler=handler("medium"))
    profile = VerificationProfile(
        name="t",
        provider_configurations={
            "low": VerificationProviderConfiguration(priority=ProviderPriority.LOW),
            "high": VerificationProviderConfiguration(priority=ProviderPriority.HIGH),
            "medium": VerificationProviderConfiguration(
                priority=ProviderPriority.MEDIUM
            ),
        },
    )
    coordinator = _coordinator([low, high, medium], profile)

    coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert order == ["high", "medium", "low"]


def test_same_priority_providers_break_ties_by_provider_id() -> None:
    order: list[str] = []

    def make_handler(
        provider_id: str,
    ) -> Callable[[VerificationRequest], VerificationResult]:
        def _handler(request: VerificationRequest) -> VerificationResult:
            order.append(provider_id)
            return VerificationResult(
                provider_id=provider_id,
                request_id=request.request_id,
                subject_id=request.subject_id,
                contact_type=request.contact_type,
                value=request.value,
                status=VerificationStatus.VALID,
                confidence=None,
                reason=None,
                error_message=None,
                started_at=request.requested_at,
                completed_at=request.requested_at,
            )

        return _handler

    zeta = FakeVerificationProvider("zeta", handler=make_handler("zeta"))
    alpha = FakeVerificationProvider("alpha", handler=make_handler("alpha"))
    coordinator = _coordinator([zeta, alpha], VerificationProfile(name="t"))

    coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert order == ["alpha", "zeta"]


def test_disabled_provider_is_skipped_and_never_called() -> None:
    provider = FakeVerificationProvider("neverbounce")
    profile = VerificationProfile(
        name="t",
        provider_configurations={
            "neverbounce": VerificationProviderConfiguration(enabled=False)
        },
    )
    coordinator = _coordinator([provider], profile)

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert provider.calls == []
    assert len(report.skipped_providers) == 1
    assert report.skipped_providers[0].provider_id == "neverbounce"
    assert report.skipped_providers[0].reason is VerificationSkipReason.DISABLED
    assert report.metrics.providers_executed == 0
    assert report.metrics.providers_skipped == 1


def test_unsupported_contact_type_provider_is_never_considered_or_skipped() -> None:
    email_only = FakeVerificationProvider(
        "neverbounce", supported_contact_types=frozenset({ContactType.EMAIL})
    )
    coordinator = _coordinator([email_only], VerificationProfile(name="t"))

    report = coordinator.verify(ContactType.PHONE, "twin-1", "+15550100")

    assert email_only.calls == []
    assert report.skipped_providers == ()
    assert report.metrics.providers_considered == 0


def test_provider_raising_is_treated_as_error_and_does_not_stop_others() -> None:
    broken = FakeVerificationProvider("broken", raises=RuntimeError("boom"))
    working = FakeVerificationProvider("working")
    profile = VerificationProfile(
        name="t",
        provider_configurations={
            "broken": VerificationProviderConfiguration(priority=ProviderPriority.HIGH),
            "working": VerificationProviderConfiguration(priority=ProviderPriority.LOW),
        },
    )
    coordinator = _coordinator([broken, working], profile)

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert len(report.provider_results) == 2
    broken_result = next(
        r for r in report.provider_results if r.provider_id == "broken"
    )
    assert broken_result.status is VerificationStatus.ERROR
    assert broken_result.error_message == "boom"
    assert report.metrics.providers_succeeded == 1
    assert report.metrics.providers_failed == 1


def test_results_are_collected_from_every_executed_provider() -> None:
    a = FakeVerificationProvider(
        "a",
        handler=lambda request: VerificationResult(
            provider_id="a",
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=VerificationStatus.VALID,
            confidence=0.9,
            reason=None,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    b = FakeVerificationProvider(
        "b",
        handler=lambda request: VerificationResult(
            provider_id="b",
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=VerificationStatus.RISKY,
            confidence=0.4,
            reason="catch-all domain",
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    coordinator = _coordinator([a, b], VerificationProfile(name="t"))

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert {r.provider_id for r in report.provider_results} == {"a", "b"}
    assert {r.status for r in report.provider_results} == {
        VerificationStatus.VALID,
        VerificationStatus.RISKY,
    }


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.VALID,
        VerificationStatus.INVALID,
        VerificationStatus.RISKY,
        VerificationStatus.UNKNOWN,
    ],
)
def test_non_technical_statuses_count_as_succeeded(status: VerificationStatus) -> None:
    def handler(request: VerificationRequest) -> VerificationResult:
        return VerificationResult(
            provider_id="p",
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=status,
            confidence=None,
            reason=None,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )

    provider = FakeVerificationProvider("p", handler=handler)
    coordinator = _coordinator([provider], VerificationProfile(name="t"))

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert report.metrics.providers_succeeded == 1
    assert report.metrics.providers_failed == 0


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.ERROR,
        VerificationStatus.TIMEOUT,
        VerificationStatus.RATE_LIMITED,
    ],
)
def test_technical_statuses_count_as_failed(status: VerificationStatus) -> None:
    def handler(request: VerificationRequest) -> VerificationResult:
        return VerificationResult(
            provider_id="p",
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=status,
            confidence=None,
            reason=None,
            error_message="failure",
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )

    provider = FakeVerificationProvider("p", handler=handler)
    coordinator = _coordinator([provider], VerificationProfile(name="t"))

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert report.metrics.providers_succeeded == 0
    assert report.metrics.providers_failed == 1


def test_invalid_profile_raises_before_any_provider_executes() -> None:
    provider = FakeVerificationProvider("neverbounce")
    invalid_profile = VerificationProfile(
        name="broken",
        default_configuration=VerificationProviderConfiguration(timeout_seconds=0),
    )
    coordinator = _coordinator([provider], invalid_profile)

    with pytest.raises(InvalidVerificationConfigurationError):
        coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert provider.calls == []


def test_duplicate_provider_id_raises() -> None:
    with pytest.raises(DuplicateVerificationProviderError):
        VerificationCoordinator(
            [FakeVerificationProvider("dup"), FakeVerificationProvider("dup")],
            VerificationProfile(name="t"),
        )


def test_request_context_is_passed_through_to_provider() -> None:
    provider = FakeVerificationProvider("neverbounce")
    coordinator = _coordinator([provider], VerificationProfile(name="t"))

    coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert len(provider.calls) == 1
    request = provider.calls[0]
    assert request.subject_id == "twin-1"
    assert request.value == "ada@example.com"
    assert request.contact_type is ContactType.EMAIL


def test_metrics_reflect_a_mixed_run() -> None:
    executed = FakeVerificationProvider("executed")
    disabled = FakeVerificationProvider("disabled")
    profile = VerificationProfile(
        name="t",
        provider_configurations={
            "disabled": VerificationProviderConfiguration(enabled=False)
        },
    )
    coordinator = _coordinator([executed, disabled], profile)

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert report.metrics.providers_considered == 2
    assert report.metrics.providers_executed == 1
    assert report.metrics.providers_succeeded == 1
    assert report.metrics.providers_failed == 0
    assert report.metrics.providers_skipped == 1
    assert report.metrics.execution_time_total_ms >= 0.0
    assert report.duration_ms >= 0.0


def test_report_never_picks_a_winning_verdict() -> None:
    a = FakeVerificationProvider(
        "a",
        handler=lambda request: VerificationResult(
            provider_id="a",
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=VerificationStatus.VALID,
            confidence=None,
            reason=None,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    b = FakeVerificationProvider(
        "b",
        handler=lambda request: VerificationResult(
            provider_id="b",
            request_id=request.request_id,
            subject_id=request.subject_id,
            contact_type=request.contact_type,
            value=request.value,
            status=VerificationStatus.INVALID,
            confidence=None,
            reason=None,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        ),
    )
    coordinator = _coordinator([a, b], VerificationProfile(name="t"))

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    # No "final_status" or similar field exists on VerificationReport —
    # the framework surfaces both disagreeing results, unresolved.
    assert not hasattr(report, "final_status")
    assert len(report.provider_results) == 2


def test_coordination_is_deterministic_given_the_same_inputs() -> None:
    def build() -> VerificationCoordinator:
        provider = FakeVerificationProvider("a")
        return _coordinator([provider], VerificationProfile(name="t"))

    report_a = build().verify(ContactType.EMAIL, "twin-1", "ada@example.com")
    report_b = build().verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert report_a.provider_results == report_b.provider_results
    assert report_a.metrics.providers_executed == report_b.metrics.providers_executed
