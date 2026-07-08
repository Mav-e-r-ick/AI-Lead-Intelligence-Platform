"""Shared test fixtures for the Executive Comparison Engine's tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.enrichment_models import ObservationCandidate
from lead_intelligence.application.dto.models import RawRecord


def fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def make_existing_record(
    cleaned_values: Mapping[str, Any] | None = None, row_number: int = 1
) -> CleanedLeadRecord:
    """A minimal CleanedLeadRecord carrying only `cleaned_values`."""

    raw_record = RawRecord(row_number=row_number, sheet_name="Sheet1", values={})
    return CleanedLeadRecord(
        raw_record=raw_record,
        cleaned_values=cleaned_values or {},
        field_changes=(),
        warnings=(),
        execution_failures=(),
    )


def make_observation(
    attribute: str,
    value: str,
    subject_id: str = "company-1",
    provider_id: str = "company_website",
    observed_at: datetime | None = None,
) -> ObservationCandidate:
    return ObservationCandidate(
        subject_id=subject_id,
        attribute=attribute,
        value=value,
        provider_id=provider_id,
        observed_at=observed_at or fixed_clock(),
    )
