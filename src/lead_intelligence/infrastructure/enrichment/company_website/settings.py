"""CompanyWebsiteProviderSettings: every knob this one provider needs.

WHY THIS ISN'T PART OF THE FRAMEWORK'S ProviderConfiguration:
ProviderConfiguration (application/enrichment/config.py) is deliberately
generic — enabled/priority/refresh policy/a timeout the framework itself
doesn't enforce — plus a fully opaque `parameters` mapping the framework
never interprets. Real per-provider behavior (retry counts, backoff, how
many candidate pages to visit, the crawler's User-Agent string) is exactly
what "no provider-specific business logic in the framework" pushes down
into the provider itself. This dataclass is where that lives, fully typed
rather than pulled out of `parameters` at call time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class CompanyWebsiteProviderSettings:
    """Immutable, typed configuration for one CompanyWebsiteProvider instance.

    Attributes:
        user_agent: Sent on every request, and checked against robots.txt
            rules via `RobotFileParser.can_fetch(user_agent, url)` — must
            be the same string used for both, or robots.txt enforcement
            would silently check the wrong identity.
        timeout_seconds: Per-request timeout, applied to every fetch
            (homepage, robots.txt, and each candidate leadership page).
        max_retries: How many additional attempts are made after an
            initial failed fetch (timeout, connection error, or 5xx
            response) before giving up on that one URL. 4xx responses are
            never retried — retrying a "Not Found" cannot succeed.
        retry_backoff_seconds: Base delay before a retry; multiplied by the
            attempt number for simple linear backoff.
        max_leadership_pages: Upper bound on how many candidate leadership/
            about/team pages are fetched per company, keeping one run's
            cost and duration both bounded and deterministic.
        cache_ttl: How long a successfully fetched page is reused from
            cache before being considered stale and re-fetched.
    """

    user_agent: str = (
        "AILeadIntelligenceBot/1.0 (+https://example.com/bot; enrichment research)"
    )
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    max_leadership_pages: int = 3
    cache_ttl: timedelta = timedelta(hours=6)

    def validate(self) -> None:
        """Raise ValueError if this settings object is self-contradictory.

        Called once, at provider construction time — a misconfigured
        provider should fail immediately, not on its first request.
        """

        if not self.user_agent.strip():
            raise ValueError(
                "CompanyWebsiteProviderSettings.user_agent must not be blank."
            )
        if self.timeout_seconds <= 0:
            raise ValueError(
                "CompanyWebsiteProviderSettings.timeout_seconds must be > 0, got "
                f"{self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "CompanyWebsiteProviderSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "CompanyWebsiteProviderSettings.retry_backoff_seconds must be >= 0, got "
                f"{self.retry_backoff_seconds}."
            )
        if self.max_leadership_pages < 1:
            raise ValueError(
                "CompanyWebsiteProviderSettings.max_leadership_pages must be >= 1, got "
                f"{self.max_leadership_pages}."
            )
        if self.cache_ttl < timedelta(0):
            raise ValueError(
                "CompanyWebsiteProviderSettings.cache_ttl must not be negative, got "
                f"{self.cache_ttl}."
            )
