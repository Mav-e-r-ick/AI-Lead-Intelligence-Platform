"""score_confidence: the Search Layer's one, shared source-trust table.

WHY THIS EXISTS, SEPARATE FROM EVERY PROVIDER:
Per the Federated Search redesign, several independent providers now run
on every request and their results are merged, deduplicated, and ranked
by `SearchCoordinator` (see `result_merging.py`). Ranking needs a single,
consistent notion of "how much do we trust this result" that does not
depend on which provider happens to import it — a `reuters.com` article
is exactly as trustworthy whether `NewsProvider` or `GoogleSearchProvider`
happened to surface its URL. Centralizing the table here (rather than
letting each provider hardcode its own guess) is what makes that
consistent and independently testable/tunable in one place.

WHY DOMAIN OVERRIDES TAKE PRIORITY OVER THE PROVIDER'S OWN BASE SCORE:
A trusted-news domain found *via* GoogleSearchProvider (a generic web
search) is still a Reuters article — it deserves Reuters' trust level, not
GoogleSearchProvider's generic 0.80 floor. Domain overrides only cover
sources this platform has an explicit opinion about (LinkedIn, and the
short list of newswire/press domains the RFC named); anything else falls
back to the finding provider's own base confidence.

WHY THESE EXACT NUMBERS:
Taken directly from this task's own specification: a company's own
website is the single most authoritative source for who currently works
there (1.00); a LinkedIn profile is self-reported by the person it's
about (0.98); an official press release is the company speaking for
itself, one step removed from its own website (0.95); Reuters/Bloomberg
are primary wire services with their own editorial verification (0.94);
BusinessWire/PRNewswire/GlobeNewswire (and other press-distribution/
aggregator outlets grouped with them below — see `_TIER_2_NEWS_DOMAINS`'s
own docstring) are themselves reprinting a company's own announcement, one
step further removed (0.92); a generic web search result has no
source-specific signal at all (0.80); anything else is a genuine unknown
(0.50).
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Base confidence for a result, keyed by the *provider* that found it —
#: used only when the result's own domain isn't covered by a more specific
#: override below (see `_DOMAIN_OVERRIDES`).
PROVIDER_BASE_CONFIDENCE: dict[str, float] = {
    "company_crawler": 1.00,
    "linkedin_search": 0.98,
    "press_release": 0.95,
    "news_search": 0.92,
    "google_web_search": 0.80,
}

#: A result with no recognized provider_id and no domain override falls
#: back to this — "we genuinely don't know how much to trust this."
DEFAULT_CONFIDENCE = 0.50

#: Reuters/Bloomberg: primary wire services, each with their own
#: editorial/fact-checking process, not merely reprinting a company's
#: self-issued announcement.
_TIER_1_NEWS_DOMAINS = frozenset({"reuters.com", "bloomberg.com"})

#: BusinessWire/PRNewswire/GlobeNewswire are press-distribution services —
#: they publish a company's own announcement verbatim, one step further
#: from primary reporting than Tier 1. Yahoo Finance is grouped here too:
#: it is itself a wire-service aggregator (largely reprinting the same
#: newswire content), not an independent newsroom — the task's own
#: confidence table names only BusinessWire explicitly (0.92); grouping
#: the other wire/aggregator outlets it lists (PRNewswire, GlobeNewswire,
#: Yahoo Finance) at the same tier is a documented, reasonable
#: extrapolation from that one given example, not a separately specified
#: number.
_TIER_2_NEWS_DOMAINS = frozenset(
    {"businesswire.com", "prnewswire.com", "globenewswire.com", "finance.yahoo.com"}
)

#: A LinkedIn profile URL, however it was found (LinkedInSearchProvider's
#: own site-restricted search, or incidentally via GoogleSearchProvider),
#: is self-reported by the person it's about — see module docstring.
_LINKEDIN_DOMAIN = "linkedin.com"


def score_confidence(url: str, provider_id: str) -> float:
    """How much a result found at `url` by `provider_id` should be
    trusted, in [0.0, 1.0].

    Args:
        url: The result's own URL — its registrable domain is checked
            against the domain-override table before falling back to
            `provider_id`'s own base confidence.
        provider_id: The `SearchProviderPort.provider_id` that produced
            this result (e.g. "company_crawler", "google_web_search").
            Falls back to `DEFAULT_CONFIDENCE` if unrecognized.
    """

    domain = _registrable_domain(url)

    if domain == _LINKEDIN_DOMAIN:
        return 0.98
    if domain in _TIER_1_NEWS_DOMAINS:
        return 0.94
    if domain in _TIER_2_NEWS_DOMAINS:
        return 0.92

    return PROVIDER_BASE_CONFIDENCE.get(provider_id, DEFAULT_CONFIDENCE)


def _registrable_domain(url: str) -> str:
    """`url`'s host, lowercased, with a leading "www." stripped — good
    enough for the small, explicit domain list this module checks against
    (not a full public-suffix-list registrable-domain computation, which
    this module has no need for)."""

    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[len("www.") :]
    return host
