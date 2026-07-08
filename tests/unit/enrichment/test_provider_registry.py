"""Unit tests for ProviderRegistry."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.enrichment_models import SubjectType
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.domain.exceptions import DuplicateProviderError
from tests.unit.enrichment.fixtures import FakeEnrichmentProvider


def test_get_returns_registered_provider() -> None:
    provider = FakeEnrichmentProvider("news")
    registry = ProviderRegistry([provider])

    assert registry.get("news") is provider


def test_get_returns_none_for_unregistered_provider() -> None:
    registry = ProviderRegistry([])

    assert registry.get("news") is None


def test_all_providers_returns_every_registered_provider() -> None:
    a = FakeEnrichmentProvider("a")
    b = FakeEnrichmentProvider("b")
    registry = ProviderRegistry([a, b])

    assert set(registry.all_providers()) == {a, b}


def test_duplicate_provider_id_raises() -> None:
    with pytest.raises(DuplicateProviderError):
        ProviderRegistry(
            [FakeEnrichmentProvider("news"), FakeEnrichmentProvider("news")]
        )


def test_providers_supporting_excludes_unsupported_subject_type() -> None:
    person_only = FakeEnrichmentProvider(
        "leadership_page", supported_subject_types=frozenset({SubjectType.PERSON})
    )
    company_only = FakeEnrichmentProvider(
        "dnb", supported_subject_types=frozenset({SubjectType.COMPANY})
    )
    registry = ProviderRegistry([person_only, company_only])

    assert registry.providers_supporting(SubjectType.PERSON) == (person_only,)
    assert registry.providers_supporting(SubjectType.COMPANY) == (company_only,)


def test_providers_supporting_includes_providers_supporting_both() -> None:
    both = FakeEnrichmentProvider(
        "web_search",
        supported_subject_types=frozenset({SubjectType.PERSON, SubjectType.COMPANY}),
    )
    registry = ProviderRegistry([both])

    assert registry.providers_supporting(SubjectType.PERSON) == (both,)
    assert registry.providers_supporting(SubjectType.COMPANY) == (both,)
