"""CompanyCrawlerProviderSettings: every knob CompanyCrawlerProvider needs.

WHY THIS HAS SENSIBLE BUILT-IN DEFAULTS, UNLIKE BrowserSearchProviderSettings:
BrowserSearchProviderSettings requires every value explicitly (see that
module's own docstring) because automating a browser against a *third-party
search engine's* own web UI is a decision only the operator can make.
CompanyCrawlerProvider instead crawls each dataset row's *own* company
website — the same target CompanyWebsiteProvider already crawls today, with
the same "no authorization decision to make" reasoning. This mirrors
CompanyWebsiteProviderSettings' own precedent: typed defaults, no
`from_env()`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyCrawlerProviderSettings:
    """Immutable, typed configuration for one CompanyCrawlerProvider instance.

    Attributes:
        user_agent: Sent as the browser's User-Agent, and checked against
            the target company's robots.txt via the same
            `RobotFileParser.can_fetch(user_agent, url)` pattern
            CompanyWebsiteProvider/BrowserSearchProvider already use.
        timeout_seconds: Per-page-navigation timeout.
        max_retries: How many additional attempts are made after an
            initial failed navigation before giving up on that one page.
        retry_backoff_seconds: Base delay before a retry; multiplied by
            the attempt number for simple linear backoff.
        max_pages: Upper bound on how many pages (beyond the homepage,
            which is only ever used to discover links, never itself
            returned as a result) are visited per company crawl —
            keeps one run's cost and duration bounded and deterministic.
        max_depth: How many link-hops beyond the homepage are followed
            when looking for priority pages (1 = only links found
            directly on the homepage; 2 = also links found on those
            pages — e.g. a "Team" link that only appears on the "About"
            page, not the homepage itself — commonly needed in practice).
        max_results: Maximum number of SearchResults returned per crawl
            (independent of max_pages — a crawl may visit more pages than
            it ultimately reports, if some visited pages score zero).
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

        Called once, at provider construction time — a misconfigured
        provider should fail immediately, not on its first crawl.
        """

        if not self.user_agent.strip():
            raise ValueError(
                "CompanyCrawlerProviderSettings.user_agent must not be blank."
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                "CompanyCrawlerProviderSettings.timeout_seconds must be > 0, "
                f"got {self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "CompanyCrawlerProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "CompanyCrawlerProviderSettings.retry_backoff_seconds must be "
                f">= 0, got {self.retry_backoff_seconds}."
            )
        if self.max_pages < 1:
            raise ValueError(
                "CompanyCrawlerProviderSettings.max_pages must be >= 1, got "
                f"{self.max_pages}."
            )
        if self.max_depth < 1:
            raise ValueError(
                "CompanyCrawlerProviderSettings.max_depth must be >= 1, got "
                f"{self.max_depth}."
            )
        if self.max_results < 1:
            raise ValueError(
                "CompanyCrawlerProviderSettings.max_results must be >= 1, got "
                f"{self.max_results}."
            )
