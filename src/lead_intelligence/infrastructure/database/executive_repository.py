"""ExecutiveRepository: the one concrete, durable store this MVP needs —
doubles as the IdentityCandidatePort implementation (so Identity
Resolution has real previously-known identities to match against, not
nothing) and as the write-back point for detected changes (so a
Comparison/Inflection result actually updates the database, per the
business requirement).

WHY ONE CLASS FOR BOTH JOBS, NOT TWO:
Both jobs need the same underlying fact: "what do we already know about
this executive." IdentityCandidatePort answers "have we seen these
signals before" by reading that row; applying a detected change answers
"here's what's different now" by writing to that same row. Splitting
these into two separate repositories/abstractions over the same one table
would be architecture for its own sake, not a real second concern.

WHY THIS IS NOT domain/repositories/digital_twin_repository.py:
That interface (and its siblings) are reserved for the future Digital
Twin entity (domain/entities/ doesn't exist yet) — a separate, larger,
not-yet-reached task. This is a small, concrete table scoped to exactly
what this MVP's identity matching and persistence need today, matching
IdentityCandidatePort's own docstring ("no concrete implementation is
provided ... will be implemented by a future infrastructure adapter").
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
)
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityRecord,
    IdentitySignal,
    SignalTier,
    SubjectType,
)
from lead_intelligence.application.dto.inflection_models import InflectionReport
from lead_intelligence.application.ports.identity_candidate_port import (
    IdentityCandidatePort,
)
from lead_intelligence.infrastructure.database.base import Base

#: signal_type (as extracted by identity_resolution/signal_extraction.py)
#: -> the column on ExecutiveModel it corresponds to. Only signal types
#: this repository can cheaply look up by a single column are supported;
#: an unsupported signal_type (e.g. the composite "company_domain_and_name")
#: simply yields no candidates, same as any signal with no stored value.
_SIGNAL_COLUMNS: dict[str, str] = {
    "duns_number": "duns_number",
    "email_exact": "email",
    "full_name": "name",
    "phone": "phone",
}


class ExecutiveModel(Base):
    """One row per executive this platform has ever processed —
    deliberately narrow (just what identity matching and change
    persistence need), not the future Digital Twin entity."""

    __tablename__ = "executives"

    subject_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    company: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    duns_number: Mapped[str | None] = mapped_column(String, nullable=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    last_inflection_type: Mapped[str | None] = mapped_column(String, nullable=True)
    last_inflection_confidence: Mapped[float | None] = mapped_column(nullable=True)
    last_inflection_explanation: Mapped[str | None] = mapped_column(String, nullable=True)
    last_inflection_detected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False)


class ExecutiveRepository(IdentityCandidatePort):
    """Backs Identity Resolution's candidate lookups and applies detected
    comparison/inflection changes to the same `executives` table."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        clock: Any = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure a repository bound to one session factory.

        Args:
            session_factory: A sessionmaker (see
                infrastructure/database/session.py's `create_session_factory`).
                A new, short-lived Session is opened per call.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._session_factory = session_factory
        self._clock = clock

    def find_by_signal(self, signal_type: str, value: str) -> Sequence[IdentityRecord]:
        """IdentityCandidatePort: every stored executive whose column for
        `signal_type` matches `value` (already-normalized by the caller)."""

        column_name = _SIGNAL_COLUMNS.get(signal_type)
        if column_name is None:
            return ()

        column = getattr(ExecutiveModel, column_name)
        with self._session_factory() as session:
            rows = session.scalars(
                select(ExecutiveModel).where(column.is_not(None))
            ).all()
            return tuple(
                self._to_identity_record(row)
                for row in rows
                if str(getattr(row, column_name)).strip().lower() == value
            )

    def ensure_baseline(
        self, subject_id: str, cleaned_values: Mapping[str, Any]
    ) -> None:
        """Insert a row for `subject_id` if one doesn't already exist —
        the first time this executive is ever processed, there is nothing
        to compare or match against yet, so this just records the
        starting point for future runs. A no-op if the row already exists
        (an existing row is only ever changed via `apply_changes`, never
        silently overwritten by re-importing the same source file)."""

        from lead_intelligence.application.comparison.resolvers import (
            EXISTING_VALUE_RESOLVERS,
        )
        from lead_intelligence.application.cleaning import field_contract as fc

        with self._session_factory() as session:
            existing = session.get(ExecutiveModel, subject_id)
            if existing is not None:
                return

            now = self._clock()
            session.add(
                ExecutiveModel(
                    subject_id=subject_id,
                    name=EXISTING_VALUE_RESOLVERS["name"](cleaned_values),
                    title=EXISTING_VALUE_RESOLVERS["title"](cleaned_values),
                    company=EXISTING_VALUE_RESOLVERS["company"](cleaned_values),
                    email=EXISTING_VALUE_RESOLVERS["email"](cleaned_values),
                    phone=EXISTING_VALUE_RESOLVERS["phone"](cleaned_values),
                    duns_number=_stringify(cleaned_values.get(fc.DUNS_NUMBER)),
                    url=_stringify(cleaned_values.get(fc.URL)),
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()

    def apply_changes(
        self,
        subject_id: str,
        comparison_result: ComparisonResult | None,
        inflection_report: InflectionReport | None,
    ) -> int:
        """Write every CHANGED/NEW field from `comparison_result` onto
        `subject_id`'s row, and stamp the latest detected inflection, if
        any. Returns how many fields were actually updated (0 if the row
        doesn't exist yet, or nothing changed).
        """

        if comparison_result is None:
            return 0

        with self._session_factory() as session:
            row = session.get(ExecutiveModel, subject_id)
            if row is None:
                return 0

            updated_fields = 0
            for comparison in comparison_result.field_comparisons:
                if comparison.status not in (
                    ComparisonStatus.CHANGED,
                    ComparisonStatus.NEW,
                ):
                    continue
                if comparison.new_value is None:
                    continue
                if not hasattr(row, comparison.field_name):
                    continue
                setattr(row, comparison.field_name, comparison.new_value)
                updated_fields += 1

            if inflection_report is not None and inflection_report.inflections:
                strongest = max(
                    inflection_report.inflections,
                    key=lambda inflection: inflection.confidence,
                )
                row.last_inflection_type = strongest.type.value
                row.last_inflection_confidence = strongest.confidence
                row.last_inflection_explanation = strongest.explanation
                row.last_inflection_detected_at = self._clock()

            if updated_fields or inflection_report is not None:
                row.updated_at = self._clock()
                session.commit()

            return updated_fields

    def _to_identity_record(self, row: ExecutiveModel) -> IdentityRecord:
        signals: list[IdentitySignal] = []
        if row.duns_number:
            signals.append(
                IdentitySignal(
                    signal_type="duns_number",
                    value=row.duns_number.strip().lower(),
                    tier=SignalTier.STRONG,
                    source_fields=("duns_number",),
                )
            )
        if row.email:
            signals.append(
                IdentitySignal(
                    signal_type="email_exact",
                    value=row.email.strip().lower(),
                    tier=SignalTier.MODERATE,
                    source_fields=("email",),
                )
            )
        if row.name:
            signals.append(
                IdentitySignal(
                    signal_type="full_name",
                    value=row.name.strip().lower(),
                    tier=SignalTier.WEAK,
                    source_fields=("name",),
                )
            )
        if row.phone:
            signals.append(
                IdentitySignal(
                    signal_type="phone",
                    value=row.phone.strip().lower(),
                    tier=SignalTier.WEAK,
                    source_fields=("phone",),
                )
            )
        return IdentityRecord(
            identity_id=row.subject_id,
            subject_type=SubjectType.PERSON,
            signals=tuple(signals),
        )


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
