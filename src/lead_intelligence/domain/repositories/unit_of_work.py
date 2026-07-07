"""The Unit of Work contract: one atomic transaction boundary.

WHY THIS FILE EXISTS:
Some operations touch more than one repository and must succeed or fail
together — the Persistence Architecture's own example is the resolution
cycle (an Observation is ingested, Resolved Values are updated, and a new
Snapshot may be materialized), which must never leave Resolved Values and
Snapshots disagreeing about current state. A Unit of Work is the seam that
makes "all of this, or none of this" possible without every use case
having to know anything about how transactions actually work.

WHY THIS IS PURE, WITH NO SQLALCHEMY (OR EVEN "SESSION") IN SIGHT:
This lives in `domain/`, which — per this project's Clean Architecture rule
since the foundation task — must never import from `infrastructure/`. The
concrete implementation (infrastructure/database/unit_of_work.py) wraps a
real SQLAlchemy Session internally; this interface only describes the
*lifecycle* every Unit of Work must support: begin (via context-manager
entry), commit, rollback, end (via context-manager exit). It deliberately
does not expose named repository properties (e.g. `.digital_twins`) —
which repositories exist is a concern for the concrete implementation to
add once those repositories themselves exist, not something this contract
should hardcode today.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType


class UnitOfWork(ABC):
    """A single atomic transaction boundary, used as a context manager.

    Typical usage (once concrete repositories exist):
        with some_unit_of_work as uow:
            ...  # do work through uow's repositories
            uow.commit()
        # if commit() was never called, __exit__ rolls back automatically.
    """

    @abstractmethod
    def __enter__(self) -> "UnitOfWork":
        """Begin the transaction and return self."""

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """End the transaction.

        If an exception propagated out of the `with` block, or if commit()
        was never called, the transaction must be rolled back — a Unit of
        Work never silently commits a partially-completed operation.
        """

    @abstractmethod
    def commit(self) -> None:
        """Make this transaction's changes permanent."""

    @abstractmethod
    def rollback(self) -> None:
        """Discard this transaction's changes."""
