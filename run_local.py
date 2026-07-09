#!/usr/bin/env python
"""Run the Executive Processing Orchestrator on a developer laptop with
real internet access: load .env.local, verify the environment is ready,
then delegate entirely to run_pipeline.py.

Usage:
    cp .env.local.example .env.local   # once, then edit if needed
    python run_local.py sample.xlsx [any run_pipeline.py argument...]

Every argument except --skip-checks is passed straight through to
run_pipeline.main() unchanged — see `python run_pipeline.py --help` for
the full list (--sheet, --limit, --output-dir, --dev-mode, etc.).

WHY THIS SCRIPT HAS NO PIPELINE LOGIC OF ITS OWN:
Its entire job is two things run_pipeline.py does not already do:
loading .env.local (a local-development convenience; run_pipeline.py
reads only the real process environment, unaware .env.local exists), and
running setup_local.py's pre-flight checks first. Importing/cleaning
records, building providers, and running the orchestrator all remain
exactly one implementation, in run_pipeline.py, called via its public
main(argv) — this script never touches CleaningPipeline,
ExecutiveProcessingOrchestrator, or any other pipeline collaborator
directly.

WHY setup_local.py RUNS AS A SUBPROCESS, NOT AN IN-PROCESS IMPORT:
setup_local.py's browser check starts and stops a real Playwright sync
driver session to resolve the Chromium executable path. Playwright's sync
API does not support a second, independent session cleanly starting later
in the same process/thread — running it in-process here left the *next*
Playwright session (the real one BrowserSearchProvider starts inside
run_pipeline.main()) failing with "using Playwright Sync API inside the
asyncio loop." A subprocess gives setup_local.py's own Playwright session
a clean process to start and exit in, so it can never affect the one
run_pipeline.py starts afterwards in this process.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_LOCAL_PATH = Path(__file__).resolve().parent / ".env.local"
SETUP_LOCAL_PATH = Path(__file__).resolve().parent / "setup_local.py"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        description=__doc__, add_help=False, allow_abbrev=False
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip setup_local.py's pre-flight checks and run immediately.",
    )
    known_args, remaining_argv = parser.parse_known_args(argv)

    if ENV_LOCAL_PATH.exists():
        load_dotenv(ENV_LOCAL_PATH)
        print(f"Loaded {ENV_LOCAL_PATH}")
    else:
        print(
            f"No {ENV_LOCAL_PATH.name} found at {ENV_LOCAL_PATH} — running with "
            "the process environment only. Copy .env.local.example to "
            ".env.local for a working Browser Search default (see "
            "LOCAL_SETUP.md)."
        )

    if not known_args.skip_checks:
        output_dir = os.environ.get("PIPELINE_OUTPUT_DIR", "run_output")
        check = subprocess.run(
            [
                sys.executable,
                str(SETUP_LOCAL_PATH),
                "--output-dir",
                output_dir,
            ],
            env=os.environ,
        )
        print()
        if check.returncode != 0:
            print(
                "Aborting: fix the FAILed check(s) above, or re-run with "
                "--skip-checks to proceed anyway."
            )
            return 1

    import run_pipeline

    return run_pipeline.main(remaining_argv)


if __name__ == "__main__":
    sys.exit(main())
