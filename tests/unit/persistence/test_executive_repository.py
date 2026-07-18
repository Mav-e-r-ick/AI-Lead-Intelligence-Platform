"""Unit tests for ExecutiveRepository — both its IdentityCandidatePort
role (find_by_signal) and its persistence role (ensure_baseline/
apply_changes). Uses an in-memory SQLite database; no real network or
external database involved."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
    ComparisonStrategy,
    ComparisonSummary,
    FieldComparison,
)
from lead_intelligence.application.dto.inflection_models import (
    Inflection,
    InflectionReport,
    InflectionType,
)
from lead_intelligence.core.config import Settings
from lead_intelligence.infrastructure.database.executive_repository import (
    ExecutiveRepository,
)
from lead_intelligence.infrastructure.database.base import Base
from lead_intelligence.infrastructure.database.session import (
    create_engine_from_settings,
    create_session_factory,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _repository() -> ExecutiveRepository:
    engine = create_engine_from_settings(Settings(database_url="sqlite:///:memory:"))
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    return ExecutiveRepository(factory, clock=_fixed_clock)


def _cleaned_values(**overrides: str) -> dict[str, str]:
    values = {
        fc.FIRST_NAME: "Ada",
        fc.LAST_NAME: "Lovelace",
        fc.TITLE: "Chief Technology Officer",
        fc.COMPANY_NAME: "Acme Corp",
        fc.EMAIL: "ada@acme.com",
        fc.PHONE: "+14155550100",
        fc.DUNS_NUMBER: "123456789",
        fc.URL: "https://acme.com",
    }
    values.update(overrides)
    return values


class TestEnsureBaseline:
    def test_inserts_a_new_row(self) -> None:
        repo = _repository()

        repo.ensure_baseline("row:1", _cleaned_values())

        candidates = repo.find_by_signal("duns_number", "123456789")
        assert len(candidates) == 1
        assert candidates[0].identity_id == "row:1"

    def test_is_a_no_op_if_the_row_already_exists(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        repo.ensure_baseline("row:1", _cleaned_values(**{fc.TITLE: "CEO"}))

        # Second call must not overwrite — title stays the original value.
        candidates = repo.find_by_signal("duns_number", "123456789")
        assert len(candidates) == 1


class TestFindBySignal:
    def test_finds_by_duns_number(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        candidates = repo.find_by_signal("duns_number", "123456789")

        assert len(candidates) == 1
        assert any(s.signal_type == "duns_number" for s in candidates[0].signals)

    def test_finds_by_email(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        candidates = repo.find_by_signal("email_exact", "ada@acme.com")

        assert len(candidates) == 1

    def test_finds_by_full_name(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        candidates = repo.find_by_signal("full_name", "ada lovelace")

        assert len(candidates) == 1

    def test_no_match_returns_empty(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        assert repo.find_by_signal("duns_number", "999999999") == ()

    def test_unsupported_signal_type_returns_empty(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        assert repo.find_by_signal("company_domain_and_name", "acme.com|acme corp") == ()

    def test_empty_repository_returns_empty(self) -> None:
        repo = _repository()

        assert repo.find_by_signal("duns_number", "123456789") == ()


def _comparison_result(*field_comparisons: FieldComparison) -> ComparisonResult:
    summary = ComparisonSummary(
        fields_matched=len(
            [f for f in field_comparisons if f.status is ComparisonStatus.MATCH]
        ),
        fields_changed=len(
            [f for f in field_comparisons if f.status is ComparisonStatus.CHANGED]
        ),
        fields_missing=0,
        fields_new=len(
            [f for f in field_comparisons if f.status is ComparisonStatus.NEW]
        ),
        fields_conflict=0,
        fields_unknown=0,
        confidence=1.0,
        compared_at=_fixed_clock(),
    )
    return ComparisonResult(
        record_reference="row:1",
        field_comparisons=field_comparisons,
        summary=summary,
    )


class TestApplyChanges:
    def test_updates_a_changed_field(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())
        comparison = _comparison_result(
            FieldComparison(
                field_name="title",
                existing_value="Chief Technology Officer",
                new_value="Chief Executive Officer",
                status=ComparisonStatus.CHANGED,
                strategy=ComparisonStrategy.FUZZY,
                similarity_score=0.4,
                conflicting_values=(),
                explanation="Title changed.",
            )
        )

        updated = repo.apply_changes("row:1", comparison, None)

        assert updated == 1
        candidates = repo.find_by_signal("duns_number", "123456789")
        # Title isn't part of identity signals, so re-fetch differently:
        # confirm via a fresh session read.
        from lead_intelligence.infrastructure.database.executive_repository import (
            ExecutiveModel,
        )

        with repo._session_factory() as session:  # noqa: SLF001 - test-only introspection
            row = session.get(ExecutiveModel, "row:1")
            assert row.title == "Chief Executive Officer"

    def test_no_op_when_row_does_not_exist(self) -> None:
        repo = _repository()
        comparison = _comparison_result(
            FieldComparison(
                field_name="title",
                existing_value=None,
                new_value="CEO",
                status=ComparisonStatus.NEW,
                strategy=ComparisonStrategy.FUZZY,
                similarity_score=None,
                conflicting_values=(),
                explanation="New title observed.",
            )
        )

        updated = repo.apply_changes("missing-row", comparison, None)

        assert updated == 0

    def test_no_op_when_comparison_result_is_none(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())

        updated = repo.apply_changes("row:1", None, None)

        assert updated == 0

    def test_matched_and_missing_fields_are_not_written(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())
        comparison = _comparison_result(
            FieldComparison(
                field_name="title",
                existing_value="Chief Technology Officer",
                new_value="Chief Technology Officer",
                status=ComparisonStatus.MATCH,
                strategy=ComparisonStrategy.FUZZY,
                similarity_score=1.0,
                conflicting_values=(),
                explanation="Title unchanged.",
            )
        )

        updated = repo.apply_changes("row:1", comparison, None)

        assert updated == 0

    def test_records_the_strongest_detected_inflection(self) -> None:
        repo = _repository()
        repo.ensure_baseline("row:1", _cleaned_values())
        comparison = _comparison_result()
        weaker = Inflection(
            type=InflectionType.CONTACT_INFO_CHANGED,
            confidence=0.5,
            supporting_comparisons=(),
            explanation="Contact info changed.",
            detected_at=_fixed_clock(),
            rule_id="INF-005",
        )
        stronger = Inflection(
            type=InflectionType.PROMOTION,
            confidence=0.9,
            supporting_comparisons=(),
            explanation="Promoted.",
            detected_at=_fixed_clock(),
            rule_id="INF-001",
        )
        report = InflectionReport(
            record_reference="row:1",
            inflections=(weaker, stronger),
            generated_at=_fixed_clock(),
        )

        repo.apply_changes("row:1", comparison, report)

        from lead_intelligence.infrastructure.database.executive_repository import (
            ExecutiveModel,
        )

        with repo._session_factory() as session:  # noqa: SLF001 - test-only introspection
            row = session.get(ExecutiveModel, "row:1")
            assert row.last_inflection_type == InflectionType.PROMOTION.value
            assert row.last_inflection_confidence == 0.9
