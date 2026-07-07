"""DigitalTwinRepository — the permanent identity anchor for a Person.

Per the Digital Twin architecture: mostly immutable (identity never
changes) with a small, legitimately mutable status-flag surface
(suppression, retirement). See base_repository.py for why that makes this
a MutableRepository rather than an AppendOnlyRepository.

TDigitalTwin is a placeholder type parameter, bound to the concrete
DigitalTwin domain entity once domain/entities/ is implemented in a future
task — see the approved Digital Twin Model architecture document.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import Repository

TDigitalTwin = TypeVar("TDigitalTwin")


class DigitalTwinRepository(Repository[TDigitalTwin, str], Generic[TDigitalTwin]):
    """Create, resolve, and manage the status of Digital Twins.

    Deliberately does not extend MutableRepository: a Twin's identity is
    permanent, and the only thing ever meant to change about it in place
    is a small status-flag surface — `update_status()` makes that boundary
    explicit at every call site, rather than exposing a generic `update()`
    that would invite editing fields that must never be edited.
    """

    @abstractmethod
    def add(self, entity: TDigitalTwin) -> None:
        """Create a new Digital Twin."""

    @abstractmethod
    def find_by_identity_signal(
        self, signal_type: str, signal_value: str
    ) -> TDigitalTwin | None:
        """Find an existing Twin by one identity-matching signal (e.g. a
        normalized name or an external ID), for use by IdentityResolutionStrategy.

        Returns None if no Twin matches — the caller is then responsible
        for deciding whether that means "create a new Twin."
        """

    @abstractmethod
    def update_status(
        self,
        twin_id: str,
        *,
        suppressed: bool | None = None,
        retired: bool | None = None,
    ) -> None:
        """Update the narrow mutable status-flag surface on a Twin."""
