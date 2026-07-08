"""Tests for VerifyContactUseCase."""

from __future__ import annotations

from typing import Callable

from lead_intelligence.application.dto.verification_models import ContactType
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.application.use_cases.verify_contact import VerifyContactUseCase
from tests.unit.verification.fixtures import FakeVerificationProvider, fixed_clock


def _id_factory() -> Callable[[], str]:
    counter = iter(range(1, 1000))

    def factory() -> str:
        return f"req-{next(counter)}"

    return factory


def _use_case(providers: list[FakeVerificationProvider]) -> VerifyContactUseCase:
    coordinator = VerificationCoordinator(
        providers,
        VerificationProfile(name="t"),
        id_factory=_id_factory(),
        clock=fixed_clock,
    )
    return VerifyContactUseCase(coordinator)


class TestVerifyContactUseCase:
    def test_delegates_to_coordinator_and_returns_report(self) -> None:
        provider = FakeVerificationProvider("neverbounce")
        use_case = _use_case([provider])

        report = use_case.execute(ContactType.EMAIL, "twin-1", "ada@example.com")

        assert report.subject_id == "twin-1"
        assert report.value == "ada@example.com"
        assert report.contact_type is ContactType.EMAIL
        assert len(provider.calls) == 1

    def test_report_reflects_no_applicable_providers(self) -> None:
        phone_only = FakeVerificationProvider(
            "twilio_lookup",
            supported_contact_types=frozenset({ContactType.PHONE}),
        )
        use_case = _use_case([phone_only])

        report = use_case.execute(ContactType.EMAIL, "twin-1", "ada@example.com")

        assert report.provider_results == ()
        assert report.metrics.providers_considered == 0
