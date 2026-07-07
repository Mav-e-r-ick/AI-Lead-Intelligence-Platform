"""Application configuration, loaded once from environment variables / .env.

WHY THIS FILE EXISTS:
Scattering `os.environ["SOME_KEY"]` calls throughout the codebase makes it
hard to know what configuration the app needs, and easy to typo a variable
name with no warning until runtime. Instead, this module defines a single
`Settings` object: a typed, validated description of every configurable
value the app uses. pydantic-settings reads `.env` (see `.env.example` at
the project root) and environment variables into this object automatically.

This is foundation-only plumbing, not business logic: it does not decide
*what* the app does, only *how it finds out* what's been configured.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, populated from environment variables.

    Every field here mirrors a key in `.env.example`. Add a field here
    whenever a new environment variable is introduced, so the app fails
    fast (at startup) instead of failing confusingly later.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-to-a-long-random-string"
    database_url: str = "sqlite:///./local_dev.db"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    `lru_cache` ensures the .env file is parsed once per process, and every
    part of the app that calls `get_settings()` shares the same object
    instead of re-reading the environment repeatedly.
    """

    return Settings()
