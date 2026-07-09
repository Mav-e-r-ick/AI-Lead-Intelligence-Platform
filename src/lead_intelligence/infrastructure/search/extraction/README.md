# Search Extraction Engine

`SearchExtractionEngine` (Version 1) — converts `SearchResult` URLs into
structured `ObservationCandidate`s, completing the pipeline the approved
Search Layer RFC drew:

```
SearchResult (URLs only)
      |
      v
Page Fetcher            (page_fetcher.py — download, robots.txt, PDF skip, retry, cache)
      |
      v
Content Extractor       (content_extraction.py — page title, visible text, publication date)
      |
      v
Observation Extraction  (fact_extraction.py + engine.py — rule-based facts -> candidates)
      |
      v
ObservationCandidate    (application/dto/enrichment_models.py — the existing type, unchanged)
```

## Scope: what Version 1 does and does not do

**Does:** download each result's destination page (respecting that
domain's own `robots.txt`, with retry/timeout/caching), extract the
page's title, visible text, and declared publication date via
deterministic HTML parsing (BeautifulSoup), extract executive
name/title/company via a small, named set of rule-based regex patterns
over common announcement phrasings, and produce `ObservationCandidate`s —
one `web_page` candidate per successfully fetched page, plus one
candidate per extracted fact — each carrying the source URL and the raw
search snippet, preserved verbatim in `raw_context`.

**Does not:** use AI or an LLM anywhere. Does not parse PDFs (a `.pdf`
URL is never requested; a response declaring `application/pdf` is
discarded — both logged). Does not guess: a page phrased outside the
known patterns yields its `web_page` candidate and nothing more. Not yet
wired into `ExecutiveProcessingOrchestrator` — the same deliberate
built-standalone-first sequencing every prior engine followed.

## Why robots.txt is checked per destination domain

Unlike `BrowserSearchProvider` (one configured search engine, one
robots.txt), this engine visits arbitrary third-party domains — whatever
the search surfaced. Each domain's robots.txt is fetched once per
`PageFetcher` instance, parsed, and consulted before any page on that
domain is requested — the same `RobotFileParser.can_fetch(user_agent, url)`
convention `CompanyWebsiteProvider` established. Missing/unreachable
robots.txt is treated as "no restrictions," the standard crawler
convention. A disallowed page is skipped with a log line, never an error.

## Why every fetched page yields a `web_page` candidate

"This page exists, was reachable, and says this in its title" is itself
evidence — the same reasoning behind `GoogleSearchProvider`'s
`web_mention` candidates. If candidates were only emitted on a
fact-pattern match, every page phrased outside the known patterns would
silently vanish from the evidence trail. The `web_page` candidate's
value is the page's own title (falling back to the search result's
title), and its `raw_context` carries the snippet, publication date,
originating search provider/rank, and a bounded text excerpt.

## The fact patterns (`fact_extraction.py`)

Deterministic, named, first-match-wins (page title scanned before body
text). Every extracted fact is traceable to the exact rule that produced
it via `raw_context["matched_pattern"]`.

| Pattern id | Phrasing it matches | Yields |
|---|---|---|
| `FACT-001-appointed-role-of-company` | "*Name* [has been/was] appointed/named [as] *Role* of/at *Company*" (auxiliary verb optional, so headlines match) | name, title, company |
| `FACT-002-promoted-to-role-of-company` | "*Name* was promoted to *Role* of/at *Company*" | name, title, company |
| `FACT-003-joins-company-as-role` | "*Name* joins/has joined *Company* as *Role*" | name, company, title |
| `FACT-004-name-comma-role-of-company` | "*Name*, *Role* of/at *Company*" (byline style) | name, title, company |
| `FACT-005-promoted-to-role` | "*Name* was promoted to *Role*" (no company stated) | name, title |

**Known, accepted Version 1 limitations** (documented in the module
docstring, deliberately not hidden): names are recognized as 2–4
consecutive capitalized words (a capitalized phrase immediately before a
real name can over-capture; lowercase name particles aren't recognized);
one page yields at most one fact set; English phrasings only.

## What each candidate looks like

Every candidate: `subject_id` (caller-supplied, same opaque-id convention
as every other stage), `provider_id="search_extraction"` (the component
that *observed* the fact — the originating search provider stays
traceable as `raw_context["search_source"]`), `source_url` (the result's
URL), `observed_at`, and a shared `raw_context`:

| `raw_context` key | Content |
|---|---|
| `search_source` / `search_rank` | Which search provider found this URL, and at what rank. |
| `search_result_title` / `snippet` | The search result's own title and snippet — the snippet preserved verbatim. |
| `page_title` | The fetched page's own title. |
| `text_excerpt` | The first `excerpt_chars` of the page's visible text. |
| `published_at` | The page's declared publication date, raw and unparsed (only when present). |
| `matched_pattern` | Which fact pattern fired (only when one did). |

## Files

| File | Responsibility |
|---|---|
| `engine.py` | `SearchExtractionEngine` — orchestrates fetch → content → facts → candidates; per-result fail-safe; logging. |
| `page_fetcher.py` | `PageFetcher` — per-domain robots.txt, PDF skip (URL suffix and Content-Type), retry/backoff, page cache (reusing `company_website`'s `InMemoryPageCache`). |
| `content_extraction.py` | `extract_page_content` — page title (with `og:title` fallback), visible text (script/style/noscript/template stripped, whitespace collapsed, bounded), publication date from `<meta>` tags (raw string, never parsed). |
| `fact_extraction.py` | `extract_facts` — the named rule-based patterns above. |
| `settings.py` | `SearchExtractionSettings` — user agent, timeout/retry/backoff, cache TTL, text bounds. All defaults are safe; no environment variables required. |

## Usage

```python
from lead_intelligence.infrastructure.search.extraction.engine import (
    SearchExtractionEngine,
)

engine = SearchExtractionEngine()
observations = engine.extract("row:1", search_results)  # tuple[ObservationCandidate, ...]
```

Tests: `tests/unit/search_extraction/` — settings validation, page
fetcher behavior (PDF skip both ways, robots.txt allow/disallow/missing,
robots.txt fetched once per domain, retry-then-succeed/exhausted, 4xx
never retried, cache reuse), content extraction (title/og:title
fallback, script-style stripping, whitespace collapse, truncation,
publication-date meta variants reported verbatim, malformed HTML), every
fact pattern's fire and no-fire behavior plus scan order and
determinism, and an end-to-end engine suite against `httpx.MockTransport`
(never a real network call).
