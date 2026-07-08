"""SearchProviderConfiguration and SearchProfile: the Search Layer's
single configuration surface.

WHY THIS FILE MIRRORS application/enrichment/config.py:
Same reasoning as that file's own docstring: every knob a caller might
reasonably want to turn (which providers run, in what order, with what
timeout) lives here, not scattered as literals through the coordinator.
Profiles are supplied per-run, never read from global/environment state.

WHY THERE IS NO RefreshPolicy HERE, UNLIKE EnrichmentProfile:
`RefreshPolicy` answers "how long is previously collected data still
fresh" — a question that only makes sense once results are persisted
somewhere with a last-fetched timestamp. Nothing in this platform
persists search results yet (the same is true of enrichment observations
today), so carrying a refresh policy here would be unexercised
scaffolding, not a real capability. If/when search results are persisted,
this profile can grow a `refresh_policy` field the same way
`ProviderConfiguration` already has one — deferred, not omitted by
oversight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from lead_intelligence.application.dto.enrichment_models import ProviderPriority
from lead_intelligence.domain.exceptions import InvalidSearchConfigurationError


@dataclass(frozen=True)
class SearchProviderConfiguration:
    """Per-provider configuration, looked up by `provider_id` from a
    SearchProfile.

    Attributes:
        enabled: Whether this provider may run at all.
        priority: Execution ordering among enabled, applicable providers
            (lower value runs first).
        timeout_seconds: The budget this provider's search() call should
            respect. Not enforced by this framework's coordinator itself —
            enforcing it is the concrete provider's own responsibility
            (e.g. BrowserSearchProvider's own page-navigation timeout) —
            but still validated and carried so every provider's profile
            entry has one consistent place to configure it from.
        parameters: Provider-specific configuration, kept fully generic
            and opaque here — this framework never interprets a
            provider's own parameters, matching
            `enrichment.config.ProviderConfiguration`'s same rule.
    """

    enabled: bool = True
    priority: ProviderPriority = ProviderPriority.MEDIUM
    timeout_seconds: float = 10.0
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


DEFAULT_SEARCH_PROVIDER_CONFIGURATION = SearchProviderConfiguration()


@dataclass(frozen=True)
class SearchProfile:
    """Immutable, typed configuration for one SearchCoordinator run.

    Attributes:
        name: Profile name (e.g. "default", "evaluation").
        version: Profile version string, independent of any code version.
        provider_configurations: provider_id -> SearchProviderConfiguration.
            A provider with no explicit entry falls back to
            `default_configuration`.
        default_configuration: The configuration used for any registered
            provider not explicitly listed in `provider_configurations`.
    """

    name: str
    version: str = "1.0.0"
    provider_configurations: Mapping[str, SearchProviderConfiguration] = field(
        default_factory=dict
    )
    default_configuration: SearchProviderConfiguration = field(
        default_factory=lambda: DEFAULT_SEARCH_PROVIDER_CONFIGURATION
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_configurations",
            MappingProxyType(dict(self.provider_configurations)),
        )

    def configuration_for(self, provider_id: str) -> SearchProviderConfiguration:
        """This provider's configuration, or `default_configuration` if
        the profile has no explicit entry for it."""

        return self.provider_configurations.get(provider_id, self.default_configuration)

    def is_enabled(self, provider_id: str) -> bool:
        """Whether `provider_id` may run at all under this profile."""

        return self.configuration_for(provider_id).enabled

    def validate(self) -> None:
        """Raise InvalidSearchConfigurationError if this profile is
        self-contradictory. Called once, before any provider is executed —
        a broken profile must fail the whole run immediately, not degrade
        into per-provider failures.
        """

        all_configurations = list(self.provider_configurations.values()) + [
            self.default_configuration
        ]
        for configuration in all_configurations:
            if configuration.timeout_seconds <= 0:
                raise InvalidSearchConfigurationError(
                    f"Profile '{self.name}' has a non-positive "
                    f"timeout_seconds={configuration.timeout_seconds}; must be > 0."
                )


def default_profile() -> SearchProfile:
    """The platform's conservative, out-of-the-box Search profile."""

    return SearchProfile(name="default", version="1.0.0")
