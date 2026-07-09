"""CompanyWebsiteProvider: the Enrichment Provider Framework's first
concrete provider — fetches a company's own website, finds its
leadership/about/team page(s), and extracts publicly listed executives.

WHY THIS SUPPORTS ONLY SubjectType.COMPANY:
This provider answers "who does this company say its leaders are?" — a
fact about the company as a whole, not about one already-identified
person. It is registered against the Company subject_type; the framework
(ProviderRegistry.providers_supporting) will never route a Person
enrichment request to it. Each person found is still reported as its own
set of ObservationCandidates (see `_person_ref` below), grouped by a
shared `raw_context["person_ref"]` rather than by `subject_id` — a future
Observation Pipeline is responsible for turning "company X's website says
person Y holds title Z" into that person's own Digital Twin evidence.

WHY known_attributes[fc.URL], NOT A NEW VOCABULARY:
EnrichmentRequest.known_attributes is "canonical field name -> value," and
`field_contract.py` (application/cleaning/) is this platform's one
established canonical vocabulary today. Reusing `fc.URL`/`fc.COMPANY_NAME`
avoids inventing a second, parallel vocabulary for the same concepts.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ObservationCandidate,
    SubjectType,
)
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.infrastructure.enrichment.company_website.cache import (
    InMemoryPageCache,
    PageCache,
)
from lead_intelligence.infrastructure.enrichment.company_website.extraction import (
    ExtractedExecutive,
    extract_executives,
)
from lead_intelligence.infrastructure.enrichment.company_website.page_discovery import (
    discover_leadership_pages,
)
from lead_intelligence.infrastructure.enrichment.company_website.settings import (
    CompanyWebsiteProviderSettings,
)

PROVIDER_ID = "company_website"
_ROBOTS_PATH = "/robots.txt"

#: Response fields this provider can emit per person found, in the order
#: they're written (name is always present; the rest only when found).
_OBSERVED_ATTRIBUTES = (
    "full_name",
    "title",
    "biography",
    "leadership_page_url",
    "email",
    "phone",
)


class CompanyWebsiteProvider(EnrichmentProviderPort):
    """Collects publicly available executive information from a company's
    own website (Version 1 — see module docstring and README.md)."""

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        cache: PageCache | None = None,
        settings: CompanyWebsiteProviderSettings | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """Configure a provider instance.

        Args:
            http_client: The httpx.Client used for every request. Defaults
                to a real client; tests inject one built with
                `transport=httpx.MockTransport(...)`.
            cache: Where fetched page content is reused from. Defaults to
                a fresh InMemoryPageCache sized from `settings.cache_ttl`.
            settings: This provider's own configuration. Defaults to
                CompanyWebsiteProviderSettings()'s conservative defaults.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps and cache
                behavior.
            sleep_fn: Called between retry attempts. Override with a no-op
                in tests to avoid real delays.
        """

        self._settings = settings or CompanyWebsiteProviderSettings()
        self._settings.validate()
        self._http_client = http_client or httpx.Client()
        self._cache = cache or InMemoryPageCache(ttl=self._settings.cache_ttl)
        self._clock = clock
        self._sleep = sleep_fn
        # Set by _get() immediately before it returns None, so fetch() can
        # report *why* a fetch failed (connection error vs. HTTP status)
        # instead of just that it did — see _get()'s docstring. Read once,
        # right after the call that set it; never meant to outlive that.
        self._last_fetch_failure: str | None = None

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Company Website"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.COMPANY})

    def fetch(self, request: EnrichmentRequest) -> EnrichmentResponse:
        """Fetch `request`'s company website and report every executive
        found on its leadership/about/team page(s).

        Never raises for ordinary failure modes (unreachable site, no
        leadership page found, robots.txt disallows access) — those are
        reported via `EnrichmentResponse.status`/`error_message`, per
        EnrichmentProviderPort's contract.
        """

        website_url = (request.known_attributes.get(fc.URL) or "").strip()
        company_name = request.known_attributes.get(fc.COMPANY_NAME, request.subject_id)

        if not website_url:
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=(
                    f"No company website URL provided in known_attributes['{fc.URL}']."
                ),
            )

        homepage_url = _normalize_url(website_url)
        logger.info(
            "Company Website provider starting: company='{}', url={}",
            company_name,
            homepage_url,
        )

        robots = self._load_robots(homepage_url)
        if robots is not None and not robots.can_fetch(
            self._settings.user_agent, homepage_url
        ):
            logger.info(
                "robots.txt disallows fetching {}; reporting nothing.", homepage_url
            )
            return self._response(request, EnrichmentStatus.SUCCESS, ())

        homepage_html = self._get(homepage_url)
        if homepage_html is None:
            reason = (
                f" ({self._last_fetch_failure})" if self._last_fetch_failure else ""
            )
            return self._response(
                request,
                EnrichmentStatus.FAILURE,
                (),
                error_message=f"Failed to fetch homepage: {homepage_url}{reason}",
            )

        candidate_pages = discover_leadership_pages(
            homepage_html, homepage_url, self._settings.max_leadership_pages
        )
        logger.debug(
            "Discovered {} candidate leadership page(s) for {}: {}",
            len(candidate_pages),
            homepage_url,
            candidate_pages,
        )

        observations: list[ObservationCandidate] = []
        pages_fetched = 0
        pages_failed = 0
        observed_at = self._clock()
        person_index = 0

        for page_url in candidate_pages:
            if robots is not None and not robots.can_fetch(
                self._settings.user_agent, page_url
            ):
                logger.info("robots.txt disallows fetching {}; skipping.", page_url)
                continue

            page_html = self._get(page_url)
            if page_html is None:
                pages_failed += 1
                continue
            pages_fetched += 1

            for executive in extract_executives(page_html):
                observations.extend(
                    self._to_observations(
                        request.subject_id,
                        executive,
                        page_url,
                        person_index,
                        observed_at,
                    )
                )
                person_index += 1

        if pages_failed > 0:
            # A page that genuinely failed to fetch (after retries) makes this
            # run incomplete. A page skipped because robots.txt disallows it
            # is not a failure — it's policy-compliant behavior, and (like
            # finding zero candidate pages at all) still counts as SUCCESS.
            status = EnrichmentStatus.PARTIAL
        else:
            status = EnrichmentStatus.SUCCESS

        logger.info(
            "Company Website provider finished: company='{}', {} page(s) fetched, "
            "{} page(s) failed, {} executive(s) found",
            company_name,
            pages_fetched,
            pages_failed,
            person_index,
        )
        return self._response(request, status, tuple(observations))

    def _to_observations(
        self,
        subject_id: str,
        executive: ExtractedExecutive,
        page_url: str,
        person_index: int,
        observed_at: datetime,
    ) -> list[ObservationCandidate]:
        """One ObservationCandidate per known fact about `executive`, all
        sharing a `raw_context["person_ref"]` so a future consumer can
        regroup them into one person even though each candidate here only
        carries a single (attribute, value) pair.
        """

        raw_context = {
            "person_ref": f"leadership-{person_index}",
            "source_page": page_url,
        }
        values: dict[str, str | None] = {
            "full_name": executive.name,
            "title": executive.title,
            "biography": executive.biography,
            "leadership_page_url": page_url,
            "email": executive.email,
            "phone": executive.phone,
        }
        return [
            ObservationCandidate(
                subject_id=subject_id,
                attribute=attribute,
                value=values[attribute] or "",
                provider_id=self.provider_id,
                observed_at=observed_at,
                source_url=page_url,
                raw_context=raw_context,
            )
            for attribute in _OBSERVED_ATTRIBUTES
            if values[attribute]
        ]

    def _response(
        self,
        request: EnrichmentRequest,
        status: EnrichmentStatus,
        observations: tuple[ObservationCandidate, ...],
        error_message: str | None = None,
    ) -> EnrichmentResponse:
        return EnrichmentResponse(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=status,
            observations=observations,
            error_message=error_message,
            started_at=request.requested_at,
            completed_at=self._clock(),
        )

    def _load_robots(self, homepage_url: str) -> RobotFileParser | None:
        """The site's robots.txt rules, or None if it couldn't be fetched
        (treated as "no restrictions," the standard crawler convention for
        a missing/unreachable robots.txt).
        """

        robots_url = urljoin(homepage_url, _ROBOTS_PATH)
        text = self._get(robots_url)
        if text is None:
            logger.debug(
                "No robots.txt available at {}; proceeding as allowed.", robots_url
            )
            return None
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return parser

    def _get(self, url: str) -> str | None:
        """Fetch `url`'s text content, via cache first, then retrying
        transient failures (timeouts, connection errors, 5xx responses) up
        to `settings.max_retries` additional times. 4xx responses are
        never retried. Returns None if the content could not be obtained.
        """

        cached = self._cache.get(url, self._clock())
        if cached is not None:
            logger.debug("Cache hit for {}", url)
            return cached

        attempts = self._settings.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._http_client.get(
                    url,
                    headers={"User-Agent": self._settings.user_agent},
                    timeout=self._settings.timeout_seconds,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Request error fetching {} (attempt {}/{}): {}",
                    url,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt == attempts:
                    self._last_fetch_failure = f"connection error: {exc}"
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 500:
                logger.warning(
                    "Server error {} fetching {} (attempt {}/{})",
                    response.status_code,
                    url,
                    attempt,
                    attempts,
                )
                if attempt == attempts:
                    self._last_fetch_failure = (
                        f"HTTP {response.status_code} (server error, retries exhausted)"
                    )
                    return None
                self._sleep(self._settings.retry_backoff_seconds * attempt)
                continue

            if response.status_code >= 400:
                logger.info(
                    "Client error {} fetching {}; not retrying.",
                    response.status_code,
                    url,
                )
                self._last_fetch_failure = f"HTTP {response.status_code}"
                return None

            self._cache.set(url, response.text, self._clock())
            return response.text

        return None


def _normalize_url(url: str) -> str:
    """Ensure `url` has a scheme, defaulting to https for a bare domain
    (e.g. an executive dataset's "acme.com" column value)."""

    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url
