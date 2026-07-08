# Company Website Provider

The Enrichment Provider Framework's first concrete provider: given a
company's own website, collect publicly available information about its
executives, ready to be compared against the platform's existing records
by a future Identity Resolution / Observation Pipeline run.

Implements `application/ports/enrichment_provider_port.py`'s
`EnrichmentProviderPort`, exactly like every other provider will. Nothing
in `application/enrichment/` (the framework) knows this class exists —
it's wired in by whatever future orchestration layer constructs a
`ProviderRegistry`.

## Scope: what Version 1 does and does not do

**Does:** fetch a company's homepage, respect `robots.txt`, find
candidate leadership/about/team page links, fetch those pages, extract
each listed executive's name/title/biography/contact info via DOM
heuristics, retry transient failures, time out slow requests, cache
fetched pages, log every step, and return `ObservationCandidate`s through
the existing framework.

**Does not:** call an AI/LLM (extraction is pure DOM heuristics — see
`extraction.py`), integrate with LinkedIn, perform a Google/web search, or
detect changes between runs (no "this page changed since last time"
logic — that is Version 2+ scope, once real enrichment history exists to
compare against).

## How the pieces communicate

```
CompanyWebsiteProvider.fetch(EnrichmentRequest)     (provider.py)
        |
        |-- known_attributes[fc.URL]  ->  the company's website
        |
        v
  _load_robots()  ->  RobotFileParser        (robots.txt, via the same cached _get())
        |
        v
  _get(homepage_url)                          (retry + timeout + cache)
        |
        v
  discover_leadership_pages(html, base_url)    (page_discovery.py)
        |                                       -> candidate leadership/about/team URLs,
        |                                          same-domain only, keyword-ranked
        v
  for each candidate page (robots-checked, capped at settings.max_leadership_pages):
        _get(page_url)                         (retry + timeout + cache)
        extract_executives(html)                (extraction.py)
        |                                        -> name/title/biography/email/phone
        v
  ObservationCandidate per fact, grouped by
  raw_context["person_ref"]
        |
        v
EnrichmentResponse                              (application/dto/enrichment_models.py)
```

## Why this provider supports only `SubjectType.COMPANY`

This provider answers "who does this company say its leaders are?" — a
fact about the company as a whole, not about one already-identified
person. `ProviderRegistry.providers_supporting()` will never route a
Person enrichment request to it. Each person found is still reported as
its own group of `ObservationCandidate`s, tied together by a shared
`raw_context["person_ref"]` (e.g. `"leadership-0"`) rather than by
`subject_id` — `ObservationCandidate` only carries one `(attribute,
value)` pair per candidate, so grouping the several facts about one
person found on a Company-scoped page needs this extra key. A future
Observation Pipeline is responsible for turning "company X's website says
person Y holds title Z" into that person's own Digital Twin evidence; this
provider only reports what it found.

## Why `known_attributes[fc.URL]`, not a new vocabulary

`EnrichmentRequest.known_attributes` is "canonical field name -> value,"
and `field_contract.py` (`application/cleaning/`) is this platform's one
established canonical vocabulary today. This provider reads
`known_attributes[fc.URL]` (falling back to nothing — a missing URL is
reported as `EnrichmentStatus.FAILURE`, not a raised exception) and logs
`known_attributes[fc.COMPANY_NAME]` if present, rather than inventing a
second, parallel vocabulary for the same concepts.

## robots.txt

Fetched once per run via the same cached, retried `_get()` used for every
other page (so a slow or flaky robots.txt fetch gets the same retry
protection). If it can't be fetched at all (missing, 404, unreachable),
this provider proceeds as if there were no restrictions — the standard
crawler convention. If it disallows the homepage entirely, this provider
reports `EnrichmentStatus.SUCCESS` with zero observations (respecting
`robots.txt` is correct behavior, not a failure); if it disallows only
specific candidate pages, those are skipped individually and the rest
still run.

## Retry, timeout, and caching (`provider.py`, `cache.py`, `settings.py`)

- Every fetch (robots.txt, homepage, each candidate page) goes through one
  `_get()` that checks the cache first, then attempts the request with a
  per-request timeout (`settings.timeout_seconds`).
- A timeout, connection error, or `5xx` response is retried up to
  `settings.max_retries` additional times, with linear backoff
  (`settings.retry_backoff_seconds * attempt`). A `4xx` response is never
  retried — retrying a "Not Found" cannot succeed.
- A successfully fetched page is cached (`InMemoryPageCache`, keyed by
  URL) for `settings.cache_ttl`, so multiple executives at the same
  company (each triggering its own `EnrichmentRequest`) don't repeatedly
  re-fetch and re-parse the same homepage/leadership page.

## Extraction heuristics (`extraction.py`)

No AI/LLM call. Leadership pages overwhelmingly follow one of a small
number of common patterns: a repeated "card" per person — an element
whose class/id names the concept (`team-member`, `leadership`, `bio`,
`staff`, `person`, `member`, ...) — containing a heading for the name, a
smaller element hinting `title`/`position`/`role`/`job` for the title, and
optionally a paragraph biography and `mailto:`/`tel:` contact links (with
a plain-text regex fallback for both). This module looks for exactly that
shape. It will miss unconventional layouts — an honestly-scoped Version 1
limitation, not a bug papered over with a model call.

## `EnrichmentStatus` outcomes

| Status | When |
|---|---|
| `FAILURE` | No website URL was provided, or the homepage itself could not be fetched. |
| `PARTIAL` | The homepage succeeded, but at least one candidate leadership page genuinely failed to fetch (after retries) — not counting pages skipped by `robots.txt`, which is compliant behavior, not failure. |
| `SUCCESS` | The homepage succeeded and every attempted candidate page either succeeded or was robots-skipped — including the legitimate empty case of "no leadership page found" or "no executives listed." |

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `CompanyWebsiteProvider` — the `EnrichmentProviderPort` implementation; orchestrates robots.txt, fetching, discovery, extraction, and `ObservationCandidate` assembly. |
| `settings.py` | `CompanyWebsiteProviderSettings` — user agent, timeout, retries, backoff, page cap, cache TTL. |
| `cache.py` | `PageCache`, `InMemoryPageCache` — TTL-based fetched-page reuse. |
| `page_discovery.py` | `discover_leadership_pages` — homepage HTML -> ranked, same-domain candidate URLs. |
| `extraction.py` | `ExtractedExecutive`, `extract_executives` — leadership page HTML -> people found on it. |

Tests: `tests/unit/company_website/` — settings validation, cache TTL
behavior, page-discovery ranking/domain-filtering/link-cleanup, extraction
heuristics (multiple people, missing fields, dedup, fallback email/phone
regex, innermost-container selection), and an end-to-end provider suite
against `httpx.MockTransport` (never a real network call) covering
robots.txt allow/disallow at both the homepage and per-page level, retry
and timeout behavior, caching, all three `EnrichmentStatus` outcomes, and
one integration test proving this provider runs correctly through the
real `EnrichmentCoordinator`/`ProviderRegistry`.
