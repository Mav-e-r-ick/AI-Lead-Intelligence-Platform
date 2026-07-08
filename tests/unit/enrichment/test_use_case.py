"""Unit tests for EnrichSubjectUseCase — a thin wrapper, tested as such."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.enrichment_models import SubjectType
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.use_cases.enrich_subject import EnrichSubjectUseCase
from tests.unit.enrichment.fixtures import FakeEnrichmentProvider


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def test_execute_returns_a_coordination_result_from_the_coordinator() -> None:
    provider = FakeEnrichmentProvider("news")
    coordinator = EnrichmentCoordinator(
        ProviderRegistry([provider]), EnrichmentProfile(name="t"), clock=_fixed_clock
    )
    use_case = EnrichSubjectUseCase(coordinator)

    result = use_case.execute(
        SubjectType.PERSON, "twin-1", {"full_name": "Ada Lovelace"}
    )

    assert result.subject_id == "twin-1"
    assert result.subject_type is SubjectType.PERSON
    assert result.metrics.providers_executed == 1
