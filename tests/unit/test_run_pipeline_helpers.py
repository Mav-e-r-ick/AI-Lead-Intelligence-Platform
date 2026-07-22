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


class TestSearchBrowserExecutablePath:
    """Regression tests for Product Accuracy Audit Priority 1: real
    execution showed CompanyCrawlerProvider and PressReleaseProvider fail
    100% of launches with "BrowserType.launch: Executable doesn't exist
    at .../chromium_headless_shell-1228/..." -- a Playwright pip package
    / installed browser revision mismatch, not a network issue. Both
    settings classes already support an executable_path override; this
    wires it to a new env var, defaulting to unset (unchanged behavior)
    exactly like BrowserSearchProvider's own BROWSER_SEARCH_EXECUTABLE_PATH."""

    def test_defaults_to_none_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("SEARCH_BROWSER_EXECUTABLE_PATH", raising=False)

        assert run_pipeline._search_browser_executable_path() is None

    def test_reads_the_env_var_when_set(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "SEARCH_BROWSER_EXECUTABLE_PATH", "/opt/pw-browsers/chromium"
        )

        assert (
            run_pipeline._search_browser_executable_path()
            == "/opt/pw-browsers/chromium"
        )

    def test_search_collaborators_pass_the_executable_path_to_both_providers(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv(
            "SEARCH_BROWSER_EXECUTABLE_PATH", "/opt/pw-browsers/chromium"
        )

        coordinator, extraction, statuses = run_pipeline._build_search_collaborators(
            dev_mode=True
        )

        registry = coordinator._registry  # noqa: SLF001 - test-only introspection
        assert (
            registry.get("company_crawler")._settings.executable_path  # noqa: SLF001
            == "/opt/pw-browsers/chromium"
        )
        assert (
            registry.get("press_release")._settings.executable_path  # noqa: SLF001
            == "/opt/pw-browsers/chromium"
        )

    def test_search_collaborators_leave_executable_path_unset_by_default(
        self, monkeypatch
    ) -> None:
        monkeypatch.delenv("SEARCH_BROWSER_EXECUTABLE_PATH", raising=False)

        coordinator, extraction, statuses = run_pipeline._build_search_collaborators(
            dev_mode=True
        )

        registry = coordinator._registry  # noqa: SLF001 - test-only introspection
        assert registry.get("company_crawler")._settings.executable_path is None  # noqa: SLF001
        assert registry.get("press_release")._settings.executable_path is None  # noqa: SLF001


class TestSharedBrowserFactory:
    """Regression tests for a second, related defect found while
    validating Priority 1 above (not in the original audit, discovered
    during this fix's own real-execution validation): once the
    executable_path fix let both Playwright-based providers actually
    launch a browser, running them together -- the real, default
    configuration -- failed with "It looks like you are using Playwright
    Sync API inside the asyncio loop", because each independently kept
    its own long-lived Playwright driver alive, and Playwright's sync API
    does not support two such driver instances coexisting in one
    process. `_shared_browser_factory` shares one instead."""

    def test_launches_the_real_browser_at_most_once(self, monkeypatch) -> None:
        launch_count = 0

        class _FakeBrowser:
            def new_page(self):  # type: ignore[no-untyped-def]
                return object()

            def close(self) -> None:
                pass

        class _FakeChromium:
            def launch(self, **kwargs):  # type: ignore[no-untyped-def]
                nonlocal launch_count
                launch_count += 1
                return _FakeBrowser()

        class _FakeDriver:
            chromium = _FakeChromium()

            def stop(self) -> None:
                pass

        class _FakeSyncPlaywrightContext:
            def start(self) -> "_FakeDriver":
                return _FakeDriver()

        import playwright.sync_api

        monkeypatch.setattr(
            playwright.sync_api,
            "sync_playwright",
            lambda: _FakeSyncPlaywrightContext(),
        )

        factory = run_pipeline._shared_browser_factory(None)

        first = factory()
        second = factory()

        assert launch_count == 1
        assert first is second

    def test_company_crawler_and_press_release_share_one_browser_factory(
        self, monkeypatch
    ) -> None:
        _clear_provider_env(monkeypatch)

        coordinator, extraction, statuses = run_pipeline._build_search_collaborators(
            dev_mode=True
        )

        registry = coordinator._registry  # noqa: SLF001 - test-only introspection
        crawler = registry.get("company_crawler")
        press_release = registry.get("press_release")
        assert (
            crawler._browser_factory is press_release._browser_factory  # noqa: SLF001
        )
