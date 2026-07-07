"""LeadRepository — the thin, campaign-specific wrapper referencing a
Digital Twin. Per the Digital Twin architecture, this is what makes
multi-campaign support possible without duplicating any factual data.

Unlike every other repository in this module, Lead is genuinely,
generically mutable, operational CRM-style state (status: new -> contacted
-> replied), not part of the executive's evidentiary history — which is
exactly why this is the one repository built on MutableRepository.

TLead is a placeholder type parameter, bound to the concrete Lead domain
entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import MutableRepository

TLead = TypeVar("TLead")


class LeadRepository(MutableRepository[TLead, str], Generic[TLead]):
    """Create, update, and query campaign-specific Lead records."""

    @abstractmethod
    def find_by_twin(self, twin_id: str) -> Sequence[TLead]:
        """Every campaign this Digital Twin is currently referenced by."""

    @abstractmethod
    def find_by_campaign(self, campaign_id: str) -> Sequence[TLead]:
        """Every Lead enrolled in one campaign — the shape a campaign
        dashboard query needs."""
