"""Unit tests for SearchProviderRegistry."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.search_models import SubjectType
from lead_intelligence.application.search.provider_registry import (
    SearchProviderRegistry,
)
from lead_intelligence.domain.exceptions import DuplicateSearchProviderError
from tests.unit.search.fixtures import FakeSearchProvider


def test_get_returns_registered_provider() -> None:
    provider = FakeSearchProvider("browser_search")
    registry = SearchProviderRegistry([provider])

    assert registry.get("browser_search") is provider


def test_get_returns_none_for_unregistered_provider() -> None:
    registry = SearchProviderRegistry([])

    assert registry.get("browser_search") is None


def test_all_providers_returns_every_registered_provider() -> None:
    a = FakeSearchProvider("a")
    b = FakeSearchProvider("b")
    registry = SearchProviderRegistry([a, b])

    assert set(registry.all_providers()) == {a, b}


def test_duplicate_provider_id_raises() -> None:
    with pytest.raises(DuplicateSearchProviderError):
        SearchProviderRegistry(
            [FakeSearchProvider("browser_search"), FakeSearchProvider("browser_search")]
        )


def test_providers_supporting_excludes_unsupported_subject_type() -> None:
    person_only = FakeSearchProvider(
        "browser_search", supported_subject_types=frozenset({SubjectType.PERSON})
    )
    company_only = FakeSearchProvider(
        "company_lookup", supported_subject_types=frozenset({SubjectType.COMPANY})
    )
    registry = SearchProviderRegistry([person_only, company_only])

    assert registry.providers_supporting(SubjectType.PERSON) == (person_only,)
    assert registry.providers_supporting(SubjectType.COMPANY) == (company_only,)


def test_providers_supporting_includes_providers_supporting_both() -> None:
    both = FakeSearchProvider(
        "general_search",
        supported_subject_types=frozenset({SubjectType.PERSON, SubjectType.COMPANY}),
    )
    registry = SearchProviderRegistry([both])

    assert registry.providers_supporting(SubjectType.PERSON) == (both,)
    assert registry.providers_supporting(SubjectType.COMPANY) == (both,)
