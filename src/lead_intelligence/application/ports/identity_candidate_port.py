"""IdentityCandidatePort: how the Identity Resolution Engine looks up
previously known identities, without knowing how or where they're stored.

WHY THIS ISN'T domain/repositories/digital_twin_repository.py:
That interface is reserved for the real, future Digital Twin entity and is
generic over a TypeVar placeholder for it (domain/entities/ is a separate,
not-yet-implemented task). This port is scoped narrowly to exactly what
identity matching needs today — an id plus its known signals
(IdentityRecord, application/dto/identity_resolution_models.py) — and will
be implemented by a future infrastructure adapter that wraps the real
DigitalTwinRepository/CompanyRepository once domain entities exist. No
concrete implementation is provided in this task; tests use an in-memory
fake (see tests/unit/identity_resolution/fixtures.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from lead_intelligence.application.dto.identity_resolution_models import IdentityRecord


class IdentityCandidatePort(ABC):
    """Read-only lookup of known identities by one identity signal."""

    @abstractmethod
    def find_by_signal(self, signal_type: str, value: str) -> Sequence[IdentityRecord]:
        """Every known IdentityRecord carrying this exact (type, value) signal.

        Args:
            signal_type: A canonical signal type name (e.g. "duns_number"),
                matching an IdentityResolutionProfile signal definition.
            value: The normalized signal value to look up (already
                normalized by the caller — this method does no matching of
                its own, only exact lookup, which is what makes it a cheap
                "blocking" step rather than a full comparison).

        Returns:
            Zero or more matching IdentityRecords. Order is not
            significant — candidate_generation.py sorts deterministically.
        """
