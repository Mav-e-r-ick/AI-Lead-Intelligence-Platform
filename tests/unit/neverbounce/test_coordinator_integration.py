"""Integration test proving NeverBounceEmailProvider works through the
real Contact Verification Framework (VerificationCoordinator), not just in
isolation."""

from __future__ import annotations

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationStatus,
)
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.provider import (
    NeverBounceEmailProvider,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NeverBounceSettings,
)
from tests.unit.neverbounce.fixtures import (
    build_client,
    fixed_clock,
    json_router,
    success_body,
)


def test_coordinator_runs_the_neverbounce_provider_and_collects_its_result() -> None:
    handler = json_router({"ada@example.com": (200, success_body("valid"))})
    provider = NeverBounceEmailProvider(
        settings=NeverBounceSettings(api_key="test-key"),
        http_client=build_client(handler),
        clock=fixed_clock,
        sleep_fn=lambda seconds: None,
    )
    coordinator = VerificationCoordinator(
        [provider], VerificationProfile(name="t"), clock=fixed_clock
    )

    report = coordinator.verify(ContactType.EMAIL, "twin-1", "ada@example.com")

    assert report.metrics.providers_executed == 1
    assert report.metrics.providers_succeeded == 1
    assert report.provider_results[0].status is VerificationStatus.VALID


def test_coordinator_never_routes_a_phone_request_to_the_neverbounce_provider() -> None:
    def unreachable_handler(request: object) -> object:
        raise AssertionError("NeverBounce should never be called for a phone request")

    provider = NeverBounceEmailProvider(
        settings=NeverBounceSettings(api_key="test-key"),
        http_client=build_client(unreachable_handler),  # type: ignore[arg-type]
    )
    coordinator = VerificationCoordinator(
        [provider], VerificationProfile(name="t"), clock=fixed_clock
    )

    report = coordinator.verify(ContactType.PHONE, "twin-1", "+15550100")

    assert report.metrics.providers_considered == 0
    assert report.provider_results == ()
