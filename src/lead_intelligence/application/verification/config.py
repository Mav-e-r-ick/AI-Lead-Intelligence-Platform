"""VerificationProviderConfiguration and VerificationProfile: the Contact
Verification Framework's single configuration surface.

WHY THIS FILE EXISTS:
Mirrors EnrichmentProfile's role: which providers run, in what order, and
with what timeout is a per-run configuration decision, not a literal
buried in coordinator.py. Profiles are supplied per-run, never read from
global/environment state, so two callers can run different profiles
concurrently and every provider's behavior stays independently testable
with a fake profile.

WHY THERE IS NO RefreshPolicy OR ProviderHealth HERE (UNLIKE THE
ENRICHMENT PROVIDER FRAMEWORK):
Version 1 scope for this framework is deliberately narrower — refresh
staleness and circuit-breaker health tracking were not requested, and
adding them now would be scope creep beyond "implement only the
verification framework." A future task can add either without changing
this profile's public shape, the same way EnrichmentProfile's shape did
not need to change when ProviderHealth was introduced alongside it.

WHY ProviderPriority IS REUSED FROM enrichment_models.py:
"Lower value runs first" execution ordering is not enrichment-specific —
it is the same generic concept EnrichmentProfile already uses. Reusing it
here avoids defining an identical enum twice, the same reuse precedent
SubjectType already set (defined once in identity_resolution_models.py,
reused by enrichment_models.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.domain.exceptions import InvalidVerificationConfigurationError


@dataclass(frozen=True)
class VerificationProviderConfiguration:
    """Per-provider configuration, looked up by `provider_id` from a
    VerificationProfile.

    Attributes:
        enabled: Whether this provider may run at all.
        priority: Execution ordering among enabled, applicable providers
            (lower value runs first).
        timeout_seconds: The budget the coordinator (or, in a future
            infrastructure adapter, the provider itself) should allow this
            provider's verify() call. Not enforced by this framework's
            pure in-memory coordinator today — that requires real I/O,
            which is explicitly out of Version 1 scope — but is still
            validated and carried so a future infrastructure task has a
            place to read it from, without a later profile-shape change.
        parameters: Provider-specific configuration (e.g. an API key
            reference, a strictness threshold). Kept fully generic and
            opaque here — this framework never interprets a provider's own
            parameters, which is what "no provider-specific business
            logic" requires.
    """

    enabled: bool = True
    priority: ProviderPriority = ProviderPriority.MEDIUM
    timeout_seconds: float = 10.0
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


DEFAULT_PROVIDER_CONFIGURATION = VerificationProviderConfiguration()


@dataclass(frozen=True)
class VerificationProfile:
    """Immutable, typed configuration for one VerificationCoordinator run.

    Attributes:
        name: Profile name (e.g. "default", "conservative").
        version: Profile version string, independent of any code version.
        provider_configurations: provider_id -> VerificationProviderConfiguration.
            A provider with no explicit entry falls back to
            `default_configuration`.
        default_configuration: The configuration used for any registered
            provider not explicitly listed in `provider_configurations` —
            this is what lets a brand-new provider be registered and run
            under sane defaults without the profile needing to know about
            it in advance.
    """

    name: str
    version: str = "1.0.0"
    provider_configurations: Mapping[str, VerificationProviderConfiguration] = field(
        default_factory=dict
    )
    default_configuration: VerificationProviderConfiguration = field(
        default_factory=lambda: DEFAULT_PROVIDER_CONFIGURATION
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_configurations",
            MappingProxyType(dict(self.provider_configurations)),
        )

    def configuration_for(self, provider_id: str) -> VerificationProviderConfiguration:
        """This provider's configuration, or `default_configuration` if
        the profile has no explicit entry for it."""

        return self.provider_configurations.get(provider_id, self.default_configuration)

    def is_enabled(self, provider_id: str) -> bool:
        """Whether `provider_id` may run at all under this profile."""

        return self.configuration_for(provider_id).enabled

    def validate(self) -> None:
        """Raise InvalidVerificationConfigurationError if this profile is
        self-contradictory. Called once, before any provider is executed —
        a broken profile must fail the whole run immediately, not degrade
        into per-provider failures.
        """

        all_configurations = list(self.provider_configurations.values()) + [
            self.default_configuration
        ]
        for configuration in all_configurations:
            if configuration.timeout_seconds <= 0:
                raise InvalidVerificationConfigurationError(
                    f"Profile '{self.name}' has a non-positive "
                    f"timeout_seconds={configuration.timeout_seconds}; must be > 0."
                )


def default_profile() -> VerificationProfile:
    """The platform's conservative, out-of-the-box Verification profile."""

    return VerificationProfile(name="default", version="1.0.0")
