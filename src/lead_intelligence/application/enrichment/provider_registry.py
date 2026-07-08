"""ProviderRegistry: the set of enrichment providers known to one
EnrichmentCoordinator, built once via dependency injection.

WHY THIS IS SEPARATE FROM EnrichmentProfile:
The registry answers "which provider *objects* exist and what can they do"
(a structural, code-level question — supported_subject_types is a fact
about the provider itself); the profile answers "which of them are
*enabled*, in what order, how often" (a per-run, configuration-level
question). Keeping them apart means the same registry can be reused across
many differently-configured runs (e.g. one profile per campaign) without
rebuilding provider instances each time.
"""

from __future__ import annotations

from typing import Sequence

from lead_intelligence.application.dto.enrichment_models import SubjectType
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.domain.exceptions import DuplicateProviderError


class ProviderRegistry:
    """A lookup of every registered EnrichmentProviderPort, keyed by its
    `provider_id`."""

    def __init__(self, providers: Sequence[EnrichmentProviderPort]) -> None:
        """Register every provider in `providers`.

        Args:
            providers: Every provider this registry should know about
                (dependency injection — not a hardcoded list). Order does
                not matter here; EnrichmentCoordinator determines execution
                order from each provider's configured ProviderPriority.

        Raises:
            DuplicateProviderError: If two providers report the same
                `provider_id`.
        """

        by_id: dict[str, EnrichmentProviderPort] = {}
        for provider in providers:
            if provider.provider_id in by_id:
                raise DuplicateProviderError(
                    f"Provider id '{provider.provider_id}' is registered more "
                    "than once; provider ids must be unique."
                )
            by_id[provider.provider_id] = provider
        self._providers = by_id

    def get(self, provider_id: str) -> EnrichmentProviderPort | None:
        """The provider registered under `provider_id`, or None if there
        isn't one."""

        return self._providers.get(provider_id)

    def all_providers(self) -> tuple[EnrichmentProviderPort, ...]:
        """Every registered provider, in registration order."""

        return tuple(self._providers.values())

    def providers_supporting(
        self, subject_type: SubjectType
    ) -> tuple[EnrichmentProviderPort, ...]:
        """Every registered provider that declares support for
        `subject_type`, in registration order. A Leadership Page provider
        that only supports Person, for example, is excluded entirely from
        a Company enrichment run — never even considered, let alone
        skipped-with-a-reason."""

        return tuple(
            provider
            for provider in self._providers.values()
            if subject_type in provider.supported_subject_types
        )
