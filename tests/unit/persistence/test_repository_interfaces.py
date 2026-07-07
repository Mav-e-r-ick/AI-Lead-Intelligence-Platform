"""Tests that every named repository interface is well-formed and built on
the correct base class, per the approved Persistence Architecture:
- Only LeadRepository is genuinely, generically mutable.
- DigitalTwinRepository / CompanyRepository expose a narrow update_status()
  instead of a generic update().
- Every other named interface is append-only, with no update surface at all.
"""

from __future__ import annotations

import inspect

import pytest

from lead_intelligence.domain import repositories
from lead_intelligence.domain.repositories.base_repository import (
    MutableRepository,
    Repository,
)

NAMED_INTERFACES = [
    repositories.DigitalTwinRepository,
    repositories.CompanyRepository,
    repositories.ObservationRepository,
    repositories.SnapshotRepository,
    repositories.RelationshipRepository,
    repositories.VerificationRepository,
    repositories.AIInsightRepository,
    repositories.LeadRepository,
    repositories.OutreachHistoryRepository,
    repositories.AuditLogRepository,
]

APPEND_ONLY_INTERFACES = [
    repositories.ObservationRepository,
    repositories.SnapshotRepository,
    repositories.RelationshipRepository,
    repositories.VerificationRepository,
    repositories.AIInsightRepository,
    repositories.OutreachHistoryRepository,
    repositories.AuditLogRepository,
]


@pytest.mark.parametrize("interface", NAMED_INTERFACES)
def test_named_interface_is_an_abstract_repository(interface: type) -> None:
    assert issubclass(interface, Repository)
    assert inspect.isabstract(interface)


@pytest.mark.parametrize("interface", APPEND_ONLY_INTERFACES)
def test_append_only_interfaces_do_not_expose_update(interface: type) -> None:
    assert not hasattr(interface, "update")


def test_lead_repository_is_the_only_named_interface_built_on_mutable_repository() -> (
    None
):
    assert issubclass(repositories.LeadRepository, MutableRepository)

    for interface in NAMED_INTERFACES:
        if interface is not repositories.LeadRepository:
            assert not issubclass(interface, MutableRepository)


def test_digital_twin_and_company_expose_narrow_update_status_not_generic_update() -> (
    None
):
    assert hasattr(repositories.DigitalTwinRepository, "update_status")
    assert not hasattr(repositories.DigitalTwinRepository, "update")

    assert hasattr(repositories.CompanyRepository, "update_status")
    assert not hasattr(repositories.CompanyRepository, "update")


def test_unit_of_work_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        repositories.UnitOfWork()  # type: ignore[abstract]
