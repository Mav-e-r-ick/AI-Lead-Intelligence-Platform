"""SearchProviderRegistry: the set of search providers known to one
SearchCoordinator, built once via dependency injection.

WHY THIS MIRRORS application/enrichment/provider_registry.py EXACTLY:
Same separation of concerns as that file's own docstring: the registry
answers "which provider *objects* exist and what can they do"; a
SearchProfile answers "which of them are *enabled*, in what order."
"""

from __future__ import annotations

from typing import Sequence

from lead_intelligence.application.dto.search_models import SubjectType
from lead_intelligence.application.ports.search_provider_port import SearchProviderPort
from lead_intelligence.domain.exceptions import DuplicateSearchProviderError


class SearchProviderRegistry:
    """A lookup of every registered SearchProviderPort, keyed by its
    `provider_id`."""

    def __init__(self, providers: Sequence[SearchProviderPort]) -> None:
        """Register every provider in `providers`.

        Args:
            providers: Every provider this registry should know about
                (dependency injection — not a hardcoded list). Order does
                not matter here; SearchCoordinator determines execution
                order from each provider's configured priority.

        Raises:
            DuplicateSearchProviderError: If two providers report the
                same `provider_id`.
        """

        by_id: dict[str, SearchProviderPort] = {}
        for provider in providers:
            if provider.provider_id in by_id:
                raise DuplicateSearchProviderError(
                    f"Provider id '{provider.provider_id}' is registered more "
                    "than once; provider ids must be unique."
                )
            by_id[provider.provider_id] = provider
        self._providers = by_id

    def get(self, provider_id: str) -> SearchProviderPort | None:
        """The provider registered under `provider_id`, or None if there
        isn't one."""

        return self._providers.get(provider_id)

    def all_providers(self) -> tuple[SearchProviderPort, ...]:
        """Every registered provider, in registration order."""

        return tuple(self._providers.values())

    def providers_supporting(
        self, subject_type: SubjectType
    ) -> tuple[SearchProviderPort, ...]:
        """Every registered provider that declares support for
        `subject_type`, in registration order."""

        return tuple(
            provider
            for provider in self._providers.values()
            if subject_type in provider.supported_subject_types
        )
