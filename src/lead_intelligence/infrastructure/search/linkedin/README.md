# LinkedIn Search Provider

`LinkedInSearchProvider` — one of the five federated Search Layer
providers (see `application/search/README.md`'s "Federated Search"
section). Searches Google's index of LinkedIn's public profile pages for
signs of a profile change: new company, promotion, designation change,
location change, or any other profile update. Implements
`SearchProviderPort` — returns `SearchResult`s only.

## Why there is no direct LinkedIn API integration

LinkedIn's own official APIs require a paid partnership tier this
platform's "no paid APIs" constraint rules out, and directly automating a
browser against linkedin.com's own search UI would face LinkedIn's
aggressive bot detection and Terms of Service in a way this platform has
no authorization to navigate — a materially different situation from
`BrowserSearchProvider`'s own "operator's real, signed-in browser" case.

Instead, this provider searches **Google's index of LinkedIn's public
profile pages**, scoped via `GoogleCustomSearchClient.search(...,
site_restrict="linkedin.com")` — the same mechanism `GoogleSearchProvider`
uses for the general web, just scoped to one domain. This finds a
person's current public LinkedIn profile (and any other indexed
linkedin.com page mentioning them) without ever contacting LinkedIn's own
servers — a legitimate, deterministic, no-AI, no-paid-API technique.

**Known Version 1 limitation:** this provider can only surface whatever
Google has already indexed and re-crawled — it has no way to force a
fresh crawl of a specific profile, and a very recent profile change may
not appear until Google's own index catches up. This is an honest,
documented gap, not a bug.

## Why query templates target profile-change signals

Per this task's own specification, this provider's purpose is detecting
*changes*, not just locating a profile URL — see `settings.py`'s
`DEFAULT_QUERY_TEMPLATES` (name+company, name+title, "new position",
"promoted", "joined \{company\}", and a bare-name fallback).

## Confidence

Every result on `linkedin.com` scores `0.98` (`application/search/
confidence.py`'s `_LINKEDIN_DOMAIN` override) — self-reported by the
person it's about, regardless of which provider happened to find the URL.

## Configuration (`settings.py`)

Shares `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` with
`infrastructure/search/google/` — same underlying Google Custom Search
account/credential (see `settings.py`'s module docstring).

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `LinkedInSearchProvider` — the `SearchProviderPort` implementation. |
| `settings.py` | `LinkedInSearchProviderSettings` — query templates, retry/timeout/cache policy, `from_env()`. |

## Testing

`tests/unit/linkedin_search/` — mocked `httpx` transport only; no test
here contacts linkedin.com or Google. Covers settings validation, the
`site_restrict="linkedin.com"` parameter on every request, missing-name
handling, successful search with `0.98` confidence, and every-query-
failing status.
