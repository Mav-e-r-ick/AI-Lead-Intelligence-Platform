"""Shared test fixtures for the Identity Resolution Engine's tests."""

from __future__ import annotations

from typing import Any, Sequence

from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.identity_resolution_models import IdentityRecord
from lead_intelligence.application.dto.models import RawRecord
from lead_intelligence.application.ports.identity_candidate_port import (
    IdentityCandidatePort,
)


def make_cleaned_record(row_number: int, **cleaned_values: Any) -> CleanedLeadRecord:
    """A minimal CleanedLeadRecord carrying only `cleaned_values` — enough
    for signal extraction, which never reads raw_record.values directly.
    """

    raw_record = RawRecord(row_number=row_number, sheet_name="Sheet1", values={})
    return CleanedLeadRecord(
        raw_record=raw_record,
        cleaned_values=cleaned_values,
        field_changes=(),
        warnings=(),
        execution_failures=(),
    )


class FakeIdentityCandidatePort(IdentityCandidatePort):
    """An in-memory IdentityCandidatePort, indexed by (signal_type, value).

    Stands in for the real infrastructure adapter (future work, backed by
    DigitalTwinRepository/CompanyRepository) so the engine's logic can be
    tested without any database.
    """

    def __init__(self, records: Sequence[IdentityRecord] = ()) -> None:
        self._records: list[IdentityRecord] = list(records)

    def add(self, record: IdentityRecord) -> None:
        self._records.append(record)

    def find_by_signal(self, signal_type: str, value: str) -> Sequence[IdentityRecord]:
        return [
            record
            for record in self._records
            if any(
                signal.signal_type == signal_type and signal.value == value
                for signal in record.signals
            )
        ]
