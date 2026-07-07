"""SQLAlchemy-backed implementation of the domain's UnitOfWork contract.

WHY THIS FILE EXISTS:
`domain/repositories/unit_of_work.py` defines *what* a Unit of Work must do
(begin/commit/rollback/end) without knowing *how* — it cannot import
SQLAlchemy at all (see that file's docstring). This is the "how": a Session
is opened on `__enter__`, `commit()`/`rollback()` delegate straight to it,
and `__exit__` guarantees that any transaction that wasn't explicitly
committed is rolled back, even if the caller raised an exception.

This class does not yet expose named repository properties (e.g.
`.digital_twins`) because no concrete repository implementations exist yet
— only the interfaces built in a prior task. Adding those properties is
deferred to whichever future task implements the first concrete
repository, per today's "only implement the persistence infrastructure"
scope.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from lead_intelligence.domain.repositories.unit_of_work import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork):
    """One atomic transaction boundary, backed by a SQLAlchemy Session.

    Usage:
        uow = SqlAlchemyUnitOfWork(session_factory)
        with uow:
            ...  # future: work through uow's repositories
            uow.commit()
        # if commit() was never called, __exit__ rolls back automatically.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    @property
    def session(self) -> Session:
        """The Session for the currently open transaction.

        Raises RuntimeError if accessed outside a `with` block — there is
        no meaningful session before `__enter__` opens one or after
        `__exit__` closes it.
        """

        if self._session is None:
            raise RuntimeError(
                "SqlAlchemyUnitOfWork.session accessed outside a 'with' block."
            )
        return self._session

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if not self._committed:
                self.rollback()
        finally:
            assert self._session is not None
            self._session.close()
            self._session = None

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()
