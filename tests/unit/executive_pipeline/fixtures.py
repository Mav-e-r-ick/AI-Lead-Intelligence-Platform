"""Shared test fixtures for the Executive Processing Pipeline's tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison import config as comparison_config
from lead_intelligence.application.comparison.config import ComparisonProfile
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.models import RawRecord
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)
from lead_intelligence.application.inflection import config as inflection_config
from lead_intelligence.application.inflection.config import InflectionProfile
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.application.ports.verification_provider_port import (
    VerificationProviderPort,
)
from lead_intelligence.application.verification.config import VerificationProfile
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def make_existing_record(
    cleaned_values: Mapping[str, Any] | None = None, row_number: int = 1
) -> CleanedLeadRecord:
    """A minimal CleanedLeadRecord carrying only `cleaned_values`."""

    raw_record = RawRecord(row_number=row_number, sheet_name="Sheet1", values={})
    return CleanedLeadRecord(
        raw_record=raw_record,
        cleaned_values=cleaned_values or {},
        field_changes=(),
        warnings=(),
        execution_failures=(),
    )


def executive_record(
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    title: str = "Chief Technology Officer",
    company_name: str = "Acme Corp",
    url: str = "https://acme.com",
    email: str | None = "ada@acme.com",
) -> CleanedLeadRecord:
    values: dict[str, Any] = {
        fc.FIRST_NAME: first_name,
        fc.LAST_NAME: last_name,
        fc.TITLE: title,
        fc.COMPANY_NAME: company_name,
        fc.URL: url,
    }
    if email is not None:
        values[fc.EMAIL] = email
    return make_existing_record(values)


def build_orchestrator(
    enrichment_providers: list[EnrichmentProviderPort] | None = None,
    verification_providers: list[VerificationProviderPort] | None = None,
    enrichment_profile: EnrichmentProfile | None = None,
    comparison_profile: ComparisonProfile | None = None,
    inflection_profile: InflectionProfile | None = None,
    verification_profile: VerificationProfile | None = None,
    clock: Callable[[], datetime] = fixed_clock,
) -> ExecutiveProcessingOrchestrator:
    enrichment_coordinator = EnrichmentCoordinator(
        ProviderRegistry(enrichment_providers or []),
        enrichment_profile or EnrichmentProfile(name="t"),
        id_factory=_sequential_id_factory(),
        clock=clock,
    )
    comparison_engine = ComparisonEngine(
        comparison_profile or comparison_config.default_profile(), clock=clock
    )
    inflection_engine = InflectionDetectionEngine(
        InflectionRuleRegistry(ALL_RULES),
        inflection_profile or inflection_config.default_profile(),
        clock=clock,
    )
    verification_coordinator: VerificationCoordinator | None = None
    if verification_providers is not None:
        verification_coordinator = VerificationCoordinator(
            verification_providers,
            verification_profile or VerificationProfile(name="t"),
            id_factory=_sequential_id_factory(),
            clock=clock,
        )
    return ExecutiveProcessingOrchestrator(
        enrichment_coordinator=enrichment_coordinator,
        comparison_engine=comparison_engine,
        inflection_engine=inflection_engine,
        verification_coordinator=verification_coordinator,
        clock=clock,
    )


def _sequential_id_factory() -> Callable[[], str]:
    counter = iter(range(1, 10_000))

    def factory() -> str:
        return f"req-{next(counter)}"

    return factory
