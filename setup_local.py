#!/usr/bin/env python
"""Verify a developer laptop is ready to run run_local.py / run_pipeline.py
with real internet access — no business logic, this script only checks
things and reports what it found.

Usage:
    python setup_local.py [--output-dir run_output]

Checks, in order:
    1. Python version
    2. lead_intelligence package installed (editable install; see
       pyproject.toml)
    3. Playwright installed
    4. A Chromium browser Playwright can launch is installed
    5. Internet connectivity (a real TCP connection, no HTTP request)
    6. DNS resolution (the configured BrowserSearchProvider host, if any,
       else a well-known public host)
    7. BrowserSearchProvider configuration
       (BrowserSearchProviderSettings.from_env().validate())
    8. Output directory exists (or can be created) and is writable

Each check reports PASS, WARN, or FAIL with a one-line reason. FAIL means
run_local.py/run_pipeline.py cannot do meaningful work until it's fixed;
WARN means a piece of optional functionality (Browser Search, real network
calls) will be degraded or skipped, but the rest of the pipeline still
runs — the same "one missing piece never blocks the whole run" philosophy
the pipeline itself already follows for every optional provider. Exits
0 if there are zero FAILs, 1 otherwise.

WHY THIS IS A SEPARATE SCRIPT, NOT PART OF run_local.py ITSELF:
run_local.py's own job is "run the pipeline" (see its module docstring);
folding pre-flight verification into it would make one script responsible
for two different concerns. run_local.py imports and calls this module's
own `run_checks()` before it runs anything, so there is exactly one
implementation of each check, never two.

WHY THIS SCRIPT ALSO LOADS .env.local WHEN RUN DIRECTLY:
run_local.py loads .env.local before delegating to run_pipeline.py, so a
check run *through* run_local.py already reflects it. This script is also
meant to be run standalone (`python setup_local.py`, e.g. right after
`cp .env.local.example .env.local`) — without loading .env.local itself
too, its BrowserSearchProvider check would report on the wrong
environment. Both call sites end up loading .env.local exactly once
each; neither duplicates the other's actual check logic.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

MIN_PYTHON = (3, 11)
ENV_LOCAL_PATH = Path(__file__).resolve().parent / ".env.local"


@dataclass(frozen=True)
class CheckResult:
    """One setup check's outcome.

    Attributes:
        name: Short, human-readable check name.
        status: "PASS", "WARN", or "FAIL".
        detail: One-line explanation of the outcome.
    """

    name: str
    status: str
    detail: str


def check_python_version() -> CheckResult:
    version = sys.version_info
    if version >= MIN_PYTHON:
        return CheckResult(
            "Python version",
            "PASS",
            f"{version.major}.{version.minor}.{version.micro} "
            f"(>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required)",
        )
    return CheckResult(
        "Python version",
        "FAIL",
        f"{version.major}.{version.minor}.{version.micro} is older than the "
        f"required {MIN_PYTHON[0]}.{MIN_PYTHON[1]}.",
    )


def check_package_installed() -> CheckResult:
    try:
        import lead_intelligence
    except ImportError:
        return CheckResult(
            "lead_intelligence package installed",
            "FAIL",
            "Not importable. This project uses a src/ layout — install it "
            "as an editable package (one time, from the repository root): "
            "pip install -e .",
        )
    return CheckResult(
        "lead_intelligence package installed",
        "PASS",
        f"lead_intelligence=={lead_intelligence.__version__} "
        f"({Path(lead_intelligence.__file__).parent})",
    )


def check_playwright_installed() -> CheckResult:
    try:
        from importlib.metadata import version as pkg_version

        installed_version = pkg_version("playwright")
    except Exception:  # noqa: BLE001 - report as a failed check, not a crash
        return CheckResult(
            "Playwright installed",
            "FAIL",
            "The playwright package is not installed. Run: "
            "pip install -r requirements.txt",
        )
    return CheckResult(
        "Playwright installed", "PASS", f"playwright=={installed_version}"
    )


def check_browser_installed() -> CheckResult:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 - Playwright itself isn't installed
        return CheckResult(
            "Browser installed", "FAIL", "playwright is not installed (see above)."
        )

    try:
        driver = sync_playwright().start()
        try:
            executable_path = Path(driver.chromium.executable_path)
        finally:
            driver.stop()
    except Exception as exc:  # noqa: BLE001 - report, don't crash setup_local.py
        return CheckResult(
            "Browser installed",
            "FAIL",
            f"Could not resolve a Chromium executable: {exc}. Run: "
            "playwright install chromium",
        )

    if executable_path.exists():
        return CheckResult("Browser installed", "PASS", str(executable_path))

    fallback = _fallback_chromium_executable()
    if fallback is not None:
        return CheckResult(
            "Browser installed",
            "PASS",
            f"Playwright's own resolver expected {executable_path} (not "
            f"found), but a pre-installed Chromium exists at {fallback}. Set "
            f"BROWSER_SEARCH_EXECUTABLE_PATH={fallback} to use it.",
        )
    return CheckResult(
        "Browser installed",
        "FAIL",
        f"Expected Chromium at {executable_path}, but it does not exist. Run: "
        "playwright install chromium",
    )


def _fallback_chromium_executable() -> Path | None:
    """A pre-installed Chromium some sandboxed/pre-provisioned environments
    ship outside Playwright's own version-pinned resolution (see
    infrastructure/search/browser/README.md's "Running the real end-to-end
    test" for the same fallback), found via PLAYWRIGHT_BROWSERS_PATH's own
    "chromium" convenience symlink, if that environment variable is set."""

    import os

    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if not browsers_path:
        return None
    candidate = Path(browsers_path) / "chromium"
    return candidate if candidate.exists() else None


def check_internet_connectivity() -> CheckResult:
    targets = (("1.1.1.1", 443), ("8.8.8.8", 443))
    errors = []
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=3):
                return CheckResult(
                    "Internet connectivity", "PASS", f"Reached {host}:{port}"
                )
        except OSError as exc:
            errors.append(f"{host}:{port} -> {exc}")
    return CheckResult(
        "Internet connectivity",
        "WARN",
        "Could not open a TCP connection to any well-known host "
        f"({'; '.join(errors)}). Browser Search and Company Website "
        "enrichment need real internet access; the rest of the pipeline "
        "still runs against whatever the existing record already has.",
    )


def check_dns_resolution() -> CheckResult:
    host = _configured_search_host() or "html.duckduckgo.com"
    try:
        address = socket.gethostbyname(host)
    except OSError as exc:
        return CheckResult(
            "DNS resolution", "WARN", f"Could not resolve '{host}': {exc}"
        )
    return CheckResult("DNS resolution", "PASS", f"{host} -> {address}")


def check_browser_search_configuration() -> CheckResult:
    try:
        from lead_intelligence.infrastructure.search.browser.settings import (
            BrowserSearchProviderSettings,
        )
    except ImportError:
        return CheckResult(
            "BrowserSearchProvider configuration",
            "FAIL",
            "lead_intelligence is not importable (see the check above). "
            "Run: pip install -e .",
        )

    settings = BrowserSearchProviderSettings.from_env()
    if not settings.search_url_template.strip():
        return CheckResult(
            "BrowserSearchProvider configuration",
            "WARN",
            "BROWSER_SEARCH_URL_TEMPLATE is not set; Browser Search will be "
            "skipped (optional). Copy .env.local.example to .env.local for a "
            "working DuckDuckGo-based default.",
        )
    try:
        settings.validate()
    except ValueError as exc:
        return CheckResult("BrowserSearchProvider configuration", "FAIL", str(exc))
    return CheckResult(
        "BrowserSearchProvider configuration",
        "PASS",
        f"search_url_template={settings.search_url_template}",
    )


def check_output_directory(output_dir: Path) -> CheckResult:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".setup_local_write_check"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return CheckResult(
            "Output directory", "FAIL", f"{output_dir} is not writable: {exc}"
        )
    free_bytes = shutil.disk_usage(output_dir).free
    return CheckResult(
        "Output directory",
        "PASS",
        f"{output_dir.resolve()} is writable ({free_bytes // (1024 * 1024)} MiB free)",
    )


def _configured_search_host() -> str | None:
    import os

    template = os.environ.get("BROWSER_SEARCH_URL_TEMPLATE", "").strip()
    if not template:
        return None
    return urlparse(template).netloc or None


def run_checks(output_dir: Path) -> list[CheckResult]:
    """Run every check, in order, and return their results."""

    return [
        check_python_version(),
        check_package_installed(),
        check_playwright_installed(),
        check_browser_installed(),
        check_internet_connectivity(),
        check_dns_resolution(),
        check_browser_search_configuration(),
        check_output_directory(output_dir),
    ]


_STATUS_SYMBOL = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}


def print_report(results: list[CheckResult]) -> None:
    name_width = max(len(result.name) for result in results)
    for result in results:
        symbol = _STATUS_SYMBOL[result.status]
        print(f"{symbol} {result.name.ljust(name_width)}  {result.detail}")

    failures = [r for r in results if r.status == "FAIL"]
    warnings = [r for r in results if r.status == "WARN"]
    print()
    if failures:
        print(
            f"{len(failures)} check(s) FAILED — fix these before running "
            "run_local.py for meaningful results."
        )
    elif warnings:
        print(
            f"All required checks passed ({len(warnings)} optional-feature "
            "warning(s) above)."
        )
    else:
        print("All checks passed.")


def main(argv: list[str] | None = None) -> int:
    if ENV_LOCAL_PATH.exists():
        load_dotenv(ENV_LOCAL_PATH)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="run_output",
        help="Directory run_local.py/run_pipeline.py will write results into "
        "(default: run_output).",
    )
    args = parser.parse_args(argv)

    results = run_checks(Path(args.output_dir))
    print_report(results)
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
