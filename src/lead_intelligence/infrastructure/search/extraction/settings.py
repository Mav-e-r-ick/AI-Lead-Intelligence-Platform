"""SearchExtractionSettings: every knob the Search Extraction Engine needs.

WHY THIS MIRRORS CompanyWebsiteProviderSettings / BrowserSearchProviderSettings:
Same reasoning as those files' own docstrings: real per-component behavior
(timeouts, retry counts, backoff, how much text to keep) lives in one
typed, validated settings object, constructed once and injected — never
read from global state at call time.

WHY THERE IS NO from_env() HERE:
Every field has a safe, working default — unlike GoogleSearchProvider
(API credentials) or BrowserSearchProvider (an operator-supplied search
engine), nothing here *requires* operator input before the engine can
run. A caller who wants different values constructs the dataclass
directly; an env-reading factory can be added later if a real deployment
needs one field configured externally — deferred, not forgotten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class SearchExtractionSettings:
    """Immutable, typed configuration for one SearchExtractionEngine instance.

    Attributes:
        user_agent: Sent on every page fetch, and checked against each
            destination domain's robots.txt via
            `RobotFileParser.can_fetch(user_agent, url)` — must be the
            same string used for both, or robots.txt enforcement would
            silently check the wrong identity (the same rule
            CompanyWebsiteProvider documents).
        timeout_seconds: Per-request timeout, applied to every page and
            robots.txt fetch.
        max_retries: How many additional attempts are made after an
            initial failed fetch (timeout, connection error, or 5xx
            response) before giving up on that one URL. 4xx responses are
            never retried.
        retry_backoff_seconds: Base delay before a retry; multiplied by
            the attempt number for simple linear backoff.
        cache_ttl: How long a successfully fetched page is reused from
            cache before being considered stale and re-fetched.
        max_text_chars: Upper bound on how much visible text is kept from
            one page — both what the rule-based fact patterns scan and
            what any excerpt is cut from. Bounds one pathological page's
            memory/CPU cost.
        excerpt_chars: How much of the visible text is carried onto each
            ObservationCandidate's `raw_context["text_excerpt"]` — enough
            for a human (or a future stage) to see the evidence in
            context, without embedding whole pages in every candidate.
    """

    user_agent: str = (
        "AILeadIntelligenceBot/1.0 (+https://example.com/bot; search extraction)"
    )
    timeout_seconds: float = 10.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    cache_ttl: timedelta = timedelta(hours=6)
    max_text_chars: int = 20_000
    excerpt_chars: int = 500

    def validate(self) -> None:
        """Raise ValueError if this settings object is self-contradictory.

        Called once, at engine construction time — a misconfigured engine
        should fail immediately, not on its first fetch.
        """

        if not self.user_agent.strip():
            raise ValueError("SearchExtractionSettings.user_agent must not be blank.")
        if self.timeout_seconds <= 0:
            raise ValueError(
                "SearchExtractionSettings.timeout_seconds must be > 0, got "
                f"{self.timeout_seconds}."
            )
        if self.max_retries < 0:
            raise ValueError(
                "SearchExtractionSettings.max_retries must be >= 0, got "
                f"{self.max_retries}."
            )
        if self.retry_backoff_seconds < 0:
            raise ValueError(
                "SearchExtractionSettings.retry_backoff_seconds must be >= 0, "
                f"got {self.retry_backoff_seconds}."
            )
        if self.cache_ttl < timedelta(0):
            raise ValueError(
                "SearchExtractionSettings.cache_ttl must not be negative, got "
                f"{self.cache_ttl}."
            )
        if self.max_text_chars < 1:
            raise ValueError(
                "SearchExtractionSettings.max_text_chars must be >= 1, got "
                f"{self.max_text_chars}."
            )
        if self.excerpt_chars < 1:
            raise ValueError(
                "SearchExtractionSettings.excerpt_chars must be >= 1, got "
                f"{self.excerpt_chars}."
            )
