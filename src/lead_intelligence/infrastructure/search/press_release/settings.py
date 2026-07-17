"""PressReleaseProviderSettings: every knob PressReleaseProvider needs.

WHY THIS HAS SENSIBLE BUILT-IN DEFAULTS, NO from_env():
Same reasoning as `company_crawler/settings.py`'s own docstring: this
provider crawls each dataset row's *own* company website (its press/
newsroom/media/investor-relations section specifically) — the same
"no authorization decision to make" target CompanyWebsiteProvider and
CompanyCrawlerProvider already crawl today.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PressReleaseProviderSettings:
    """Immutable, typed configuration for one PressReleaseProvider
    instance.

    Attributes:
        user_agent: Sent as the browser's User-Agent, and checked against
            the target company's robots.txt.
        timeout_seconds: Per-page-navigation timeout.
        max_retries: How many additional attempts are made after an
            initial failed navigation before giving up on that one page.
        retry_backoff_seconds: Base delay before a retry; multiplied by
            the attempt number for simple linear backoff.
        max_pages: Upper bound on how many pages (beyond the homepage,
            never itself returned as a result) are visited per crawl.
        max_depth: How many link-hops beyond the homepage are followed —
            a company's press index often links out to individual release
            pages one hop further than the homepage itself.
        max_results: Maximum number of SearchResults returned per crawl.
        headless: Whether the browser runs without a visible window.
        executable_path: Optional explicit path to a Chromium/Chrome
            executable, overriding Playwright's own resolution.
    """

    user_agent: str = (
        "AILeadIntelligenceBot/1.0 (+https://example.com/bot; crawler research)"
    )
    timeout_seconds: float = 15.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    max_pages: int = 8
    max_depth: int = 2
    max_results: int = 10
    headless: bool = True
    executable_path: str | None = None

    def validate(self) -> None:
        """Raise ValueError if this settings object is self-contradictory.

        Called once, at provider construction time.
        """

        if not self.user_agent.strip():
            raise ValueError(
                "PressReleaseProviderSettings.user_agent must not be blank."
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                "PressReleaseProviderSettings.timeout_seconds must be > 0, "
                f"got {self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "PressReleaseProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "PressReleaseProviderSettings.retry_backoff_seconds must be "
                f">= 0, got {self.retry_backoff_seconds}."
            )
        if self.max_pages < 1:
            raise ValueError(
                "PressReleaseProviderSettings.max_pages must be >= 1, got "
                f"{self.max_pages}."
            )
        if self.max_depth < 1:
            raise ValueError(
                "PressReleaseProviderSettings.max_depth must be >= 1, got "
                f"{self.max_depth}."
            )
        if self.max_results < 1:
            raise ValueError(
                "PressReleaseProviderSettings.max_results must be >= 1, got "
                f"{self.max_results}."
            )
