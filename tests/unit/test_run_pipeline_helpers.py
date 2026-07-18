"""Unit tests for run_pipeline.py's own helper functions (not part of the
lead_intelligence package, but plain functions in the CLI script)."""

from __future__ import annotations

from datetime import datetime, timezone

import run_pipeline
from lead_intelligence.application.dto.comparison_models import (
    ComparisonResult,
    ComparisonStatus,
    ComparisonStrategy,
    ComparisonSummary,
    FieldComparison,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


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


def _field_comparison(
    field_name: str,
    existing_value: str | None,
    new_value: str | None,
    status: ComparisonStatus,
) -> FieldComparison:
    return FieldComparison(
        field_name=field_name,
        existing_value=existing_value,
        new_value=new_value,
        status=status,
        strategy=ComparisonStrategy.FUZZY,
        similarity_score=None,
        conflicting_values=(),
        explanation="test",
    )


class TestCurrentFieldValue:
    def test_none_comparison_result_returns_fallback(self) -> None:
        assert (
            run_pipeline._current_field_value(None, "title", "Old Title")
            == "Old Title"
        )

    def test_changed_field_returns_new_value(self) -> None:
        comparison = _comparison_result(
            _field_comparison(
                "title", "Old Title", "New Title", ComparisonStatus.CHANGED
            )
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "New Title"
        )

    def test_new_field_returns_new_value(self) -> None:
        comparison = _comparison_result(
            _field_comparison("title", None, "New Title", ComparisonStatus.NEW)
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", None)
            == "New Title"
        )

    def test_matched_field_returns_fallback_not_existing_value(self) -> None:
        comparison = _comparison_result(
            _field_comparison(
                "title", "Same Title", "Same Title", ComparisonStatus.MATCH
            )
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Same Title")
            == "Same Title"
        )

    def test_missing_field_returns_fallback(self) -> None:
        comparison = _comparison_result(
            _field_comparison("title", None, None, ComparisonStatus.MISSING)
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "Old Title"
        )

    def test_field_name_not_present_returns_fallback(self) -> None:
        comparison = _comparison_result(
            _field_comparison(
                "company", "Old Co", "New Co", ComparisonStatus.CHANGED
            )
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "Old Title"
        )

    def test_changed_field_with_no_new_value_falls_back(self) -> None:
        comparison = _comparison_result(
            _field_comparison("title", "Old Title", None, ComparisonStatus.CHANGED)
        )

        assert (
            run_pipeline._current_field_value(comparison, "title", "Old Title")
            == "Old Title"
        )


def _clear_provider_env(monkeypatch) -> None:
    for var in (
        "GOOGLE_SEARCH_API_KEY",
        "GOOGLE_SEARCH_ENGINE_ID",
        "NEVERBOUNCE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


class TestProviderStatusReporting:
    """The platform must run with any combination of optional providers
    configured, disabling — never crashing on — whichever ones aren't."""

    def test_enrichment_providers_disable_google_when_unconfigured(
        self, monkeypatch
    ) -> None:
        _clear_provider_env(monkeypatch)

        providers, statuses = run_pipeline._build_enrichment_providers()

        assert len(providers) == 1  # CompanyWebsiteProvider only
        google_status = next(s for s in statuses if "Google" in s.display_name)
        assert google_status.enabled is False
        assert "GOOGLE_SEARCH_API_KEY" in google_status.reason

    def test_enrichment_providers_enable_google_when_configured(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "fake-key")
        monkeypatch.setenv("GOOGLE_SEARCH_ENGINE_ID", "fake-cx")

        providers, statuses = run_pipeline._build_enrichment_providers()

        assert len(providers) == 2
        google_status = next(s for s in statuses if "Google" in s.display_name)
        assert google_status.enabled is True

    def test_search_collaborators_disable_three_google_backed_providers_together(
        self, monkeypatch
    ) -> None:
        _clear_provider_env(monkeypatch)

        coordinator, extraction, statuses = run_pipeline._build_search_collaborators(
            dev_mode=True
        )

        disabled = {s.display_name for s in statuses if not s.enabled}
        assert disabled == {
            "Google Search Provider (search)",
            "LinkedIn Search Provider (search)",
            "News Provider (search)",
        }
        enabled = {s.display_name for s in statuses if s.enabled}
        assert enabled == {
            "Company Crawler Provider (search)",
            "Press Release Provider (search)",
        }

    def test_search_collaborators_never_raises_with_no_providers_configured(
        self, monkeypatch
    ) -> None:
        _clear_provider_env(monkeypatch)

        coordinator, extraction, statuses = run_pipeline._build_search_collaborators(
            dev_mode=True
        )

        assert coordinator is not None
        assert any(s.enabled for s in statuses)  # crawler-based providers still run

    def test_verification_coordinator_disabled_when_unconfigured(
        self, monkeypatch
    ) -> None:
        _clear_provider_env(monkeypatch)

        coordinator, statuses = run_pipeline._build_verification_coordinator()

        assert coordinator is None
        assert statuses[0].enabled is False
        assert "NEVERBOUNCE_API_KEY" in statuses[0].reason

    def test_verification_coordinator_enabled_when_configured(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("NEVERBOUNCE_API_KEY", "fake-key")

        coordinator, statuses = run_pipeline._build_verification_coordinator()

        assert coordinator is not None
        assert statuses[0].enabled is True

    def test_build_orchestrator_never_raises_with_zero_optional_providers_configured(
        self, monkeypatch, tmp_path
    ) -> None:
        _clear_provider_env(monkeypatch)
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

        orchestrator, extraction, statuses = run_pipeline.build_orchestrator(
            dev_mode=True
        )

        assert orchestrator is not None
        assert len(statuses) == 8  # every provider this platform knows about
        assert sum(1 for s in statuses if s.enabled) == 3  # always-on ones only
