"""Central logging setup so every part of the app logs the same way.

WHY THIS FILE EXISTS:
Without a shared setup, different modules could end up configuring Python's
logging system inconsistently (or not at all), making logs hard to read
and correlate. This module configures `loguru` once, using the log level
from `core.config.Settings`, and every other module simply does:

    from loguru import logger
    logger.info("something happened")

This is foundation-only plumbing: it has no opinion on *what* gets logged,
only on how logging is set up.
"""

import sys

from loguru import logger

from lead_intelligence.core.config import get_settings


def configure_logging() -> None:
    """Configure loguru's output format and level from application settings."""

    settings = get_settings()
    logger.remove()  # Remove loguru's default handler before adding ours.
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
    )
