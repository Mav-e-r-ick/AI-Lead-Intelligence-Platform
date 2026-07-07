"""AuditLogRepository — the append-only, never-deleted trail of
administrative actions taken on the system itself (identity merges/splits,
erasure requests, manual corrections, configuration changes). Distinct
from Observation provenance, which records where a *business fact* came
from, not who did what to the system.

WHY THIS ISN'T CALLED DIRECTLY FROM SCATTERED BUSINESS LOGIC:
Per the Persistence Architecture, this repository's write path is meant to
be invoked by a cross-cutting concern (a decorator/interceptor around
administrative operations) in a future task, so an audit entry can never
be accidentally forgotten by a call site. This interface only defines the
contract; how it gets invoked is deliberately not decided here.

TAuditLogEntry is a placeholder type parameter, bound to the concrete
AuditLogEntry domain entity once domain/entities/ is implemented.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from typing import Generic, TypeVar

from lead_intelligence.domain.repositories.base_repository import AppendOnlyRepository

TAuditLogEntry = TypeVar("TAuditLogEntry")


class AuditLogRepository(
    AppendOnlyRepository[TAuditLogEntry, str], Generic[TAuditLogEntry]
):
    """Append and query audit log entries."""

    @abstractmethod
    def find_by_subject(self, subject_id: str) -> Sequence[TAuditLogEntry]:
        """Every administrative action ever taken affecting this Subject."""
