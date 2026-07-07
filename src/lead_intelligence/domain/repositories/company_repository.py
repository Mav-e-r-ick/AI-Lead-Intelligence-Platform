"""CompanyRepository — the Subject anchor for a Company, mirroring
DigitalTwinRepository's shape for the same reasons (see that file's
docstring for why this is not a MutableRepository).

TCompany is a placeholder type parameter, bound to the concrete Company
domain entity once domain/entities/ is implemented in a future task.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import Repository

TCompany = TypeVar("TCompany")


class CompanyRepository(Repository[TCompany, str], Generic[TCompany]):
    """Create, resolve, and manage the status of Company entities."""

    @abstractmethod
    def add(self, entity: TCompany) -> None:
        """Create a new Company."""

    @abstractmethod
    def find_by_duns_number(self, duns_number: str) -> TCompany | None:
        """Find an existing Company by its D-U-N-S number, when known.

        DUNS numbers must be matched as the exact string they were
        preserved as by the Import Engine (leading zeros intact) — never
        coerced to a number for comparison.
        """

    @abstractmethod
    def find_by_name(self, normalized_name: str) -> TCompany | None:
        """Find an existing Company by normalized name, for identity
        resolution when no D-U-N-S number is available."""

    @abstractmethod
    def update_status(self, company_id: str, *, active: bool | None = None) -> None:
        """Update the narrow mutable status-flag surface on a Company
        (e.g. marking it inactive after an acquisition/dissolution)."""
