"""RefreshPolicy, ProviderConfiguration, and EnrichmentProfile: the
Enrichment Provider Framework's single configuration surface.

WHY THIS FILE EXISTS:
Mirrors CleaningProfile / IdentityResolutionProfile's role: every knob a
caller might reasonably want to turn (which providers run, in what order,
how often, with what timeout) lives here, not scattered as literals
through the coordinator. Profiles are supplied per-run, never read from
global/environment state, so two callers can run different profiles
concurrently and every provider's behavior stays independently testable
with a fake profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping

from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.domain.exceptions import InvalidEnrichmentConfigurationError


@dataclass(frozen=True)
class RefreshPolicy:
    """How long previously collected data from one provider stays "fresh"
    enough that re-fetching it isn't worthwhile.

    Attributes:
        max_age: Once this much time has passed since a provider was last
            fetched for a given subject, it's considered stale and eligible
            to run again.
    """

    max_age: timedelta = timedelta(days=30)

    def should_refresh(self, last_fetched_at: datetime | None, now: datetime) -> bool:
        """Whether a provider should run again.

        Args:
            last_fetched_at: When this provider last successfully ran for
                this subject, or None if it has never run.
            now: The current time, for a deterministic, testable comparison
                (never reads the wall clock itself).

        Returns:
            True if the provider has never run, or its last run is older
            than `max_age`.
        """

        if last_fetched_at is None:
            return True
        return (now - last_fetched_at) >= self.max_age


DEFAULT_REFRESH_POLICY = RefreshPolicy(max_age=timedelta(days=30))


@dataclass(frozen=True)
class ProviderConfiguration:
    """Per-provider configuration, looked up by `provider_id` from an
    EnrichmentProfile.

    Attributes:
        enabled: Whether this provider may run at all.
        priority: Execution ordering among enabled, applicable providers
            (lower value runs first).
        refresh_policy: How often this provider's data should be refreshed.
        timeout_seconds: The budget the coordinator (or, in a future
            infrastructure adapter, the provider itself) should allow this
            provider's fetch() call. Not enforced by this framework's pure
            in-memory coordinator today — that requires real I/O, which is
            explicitly out of Version 1 scope — but is still validated and
            carried so a future infrastructure task has a place to read it
            from, without a later profile-shape change.
        parameters: Provider-specific configuration (e.g. an API base URL,
            a search-result limit). Kept fully generic and opaque here —
            this framework never interprets a provider's own parameters,
            which is what "no provider-specific business logic" requires.
    """

    enabled: bool = True
    priority: ProviderPriority = ProviderPriority.MEDIUM
    refresh_policy: RefreshPolicy = field(
        default_factory=lambda: DEFAULT_REFRESH_POLICY
    )
    timeout_seconds: float = 10.0
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


DEFAULT_PROVIDER_CONFIGURATION = ProviderConfiguration()


@dataclass(frozen=True)
class EnrichmentProfile:
    """Immutable, typed configuration for one EnrichmentCoordinator run.

    Attributes:
        name: Profile name (e.g. "default", "conservative").
        version: Profile version string, independent of any code version.
        provider_configurations: provider_id -> ProviderConfiguration.
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
    provider_configurations: Mapping[str, ProviderConfiguration] = field(
        default_factory=dict
    )
    default_configuration: ProviderConfiguration = field(
        default_factory=lambda: DEFAULT_PROVIDER_CONFIGURATION
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_configurations",
            MappingProxyType(dict(self.provider_configurations)),
        )

    def configuration_for(self, provider_id: str) -> ProviderConfiguration:
        """This provider's configuration, or `default_configuration` if
        the profile has no explicit entry for it."""

        return self.provider_configurations.get(provider_id, self.default_configuration)

    def is_enabled(self, provider_id: str) -> bool:
        """Whether `provider_id` may run at all under this profile."""

        return self.configuration_for(provider_id).enabled

    def validate(self) -> None:
        """Raise InvalidEnrichmentConfigurationError if this profile is
        self-contradictory. Called once, before any provider is executed —
        a broken profile must fail the whole run immediately, not degrade
        into per-provider failures.
        """

        all_configurations = list(self.provider_configurations.values()) + [
            self.default_configuration
        ]
        for configuration in all_configurations:
            if configuration.timeout_seconds <= 0:
                raise InvalidEnrichmentConfigurationError(
                    f"Profile '{self.name}' has a non-positive "
                    f"timeout_seconds={configuration.timeout_seconds}; must be > 0."
                )
            if configuration.refresh_policy.max_age < timedelta(0):
                raise InvalidEnrichmentConfigurationError(
                    f"Profile '{self.name}' has a negative refresh_policy.max_age="
                    f"{configuration.refresh_policy.max_age}."
                )


def default_profile() -> EnrichmentProfile:
    """The platform's conservative, out-of-the-box Enrichment profile."""

    return EnrichmentProfile(name="default", version="1.0.0")
