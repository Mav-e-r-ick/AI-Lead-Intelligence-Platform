"""The Enrichment Provider Framework's application-level orchestration
entry point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors CleanDatasetUseCase's and ResolveIdentityUseCase's role exactly:
this class knows nothing about providers, registries, priority, health, or
refresh policy — it only knows how to hand a Subject to an
EnrichmentCoordinator and return the EnrichmentCoordinationResult. Real
orchestration logic lives in EnrichmentCoordinator; this is the stable
seam a future API/CLI layer calls.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from loguru import logger

from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentCoordinationResult,
    SubjectType,
)
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator


class EnrichSubjectUseCase:
    """Enriches one Subject using a pre-configured coordinator."""

    def __init__(self, coordinator: EnrichmentCoordinator) -> None:
        """Bind this use case to one already-configured coordinator.

        Args:
            coordinator: An EnrichmentCoordinator already constructed with
                its ProviderRegistry and EnrichmentProfile.
        """

        self._coordinator = coordinator

    def execute(
        self,
        subject_type: SubjectType,
        subject_id: str,
        known_attributes: Mapping[str, str],
        attributes_of_interest: tuple[str, ...] = (),
        provider_last_fetched: Mapping[str, datetime] | None = None,
    ) -> EnrichmentCoordinationResult:
        """Enrich `subject_id` and return the full combined result.

        Args:
            subject_type: Person or Company.
            subject_id: The Digital Twin id (or provisional identity id)
                being enriched.
            known_attributes: Canonical field name -> known value, given to
                every executed provider.
            attributes_of_interest: An optional hint of which attributes
                matter most for this run.
            provider_last_fetched: provider_id -> when that provider was
                last successfully run for this subject, if known.

        Returns:
            An EnrichmentCoordinationResult containing every executed
            provider's response, every collected ObservationCandidate, the
            skipped-provider list, and run metrics.
        """

        logger.info(
            "Enrich subject use case starting (subject_id={}, subject_type={})",
            subject_id,
            subject_type.value,
        )
        result = self._coordinator.enrich(
            subject_type,
            subject_id,
            known_attributes,
            attributes_of_interest,
            provider_last_fetched,
        )
        logger.info(
            "Enrich subject use case finished: {} observation(s) from {} provider(s)",
            result.metrics.observations_collected,
            result.metrics.providers_executed,
        )
        return result
