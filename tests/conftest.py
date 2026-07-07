"""Shared pytest configuration.

WHY THIS FILE EXISTS:
`integration/test_health.py` imports the FastAPI app, which (via
`interfaces/api/dependencies.py`) constructs a real database Engine at
import time from `core.config.get_settings()`. Left unconfigured, that
would default to the file-based `sqlite:///./local_dev.db`, leaving a
stray database file in the repo root after every test run. Setting
DATABASE_URL here — in the root conftest, loaded by pytest before any test
module is imported — guarantees `get_settings()` (cached for the life of
the process) never sees that file-based default, regardless of which test
file happens to trigger the first import.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
