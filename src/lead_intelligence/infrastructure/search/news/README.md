# News Provider

`NewsProvider` — one of the five federated Search Layer providers (see
`application/search/README.md`'s "Federated Search" section). Searches
trusted business-news outlets for executive-movement news. Implements
`SearchProviderPort` — returns `SearchResult`s only.

## Trusted domains

`settings.py`'s `TRUSTED_NEWS_DOMAINS` — the exact outlets this task
names: Reuters, Bloomberg, Yahoo Finance, BusinessWire, PRNewswire,
GlobeNewswire.

## Why a `(site:a OR site:b OR ...)` query clause instead of `site_restrict`

`GoogleCustomSearchClient.search(..., site_restrict=...)` (used by
`LinkedInSearchProvider`) only accepts one domain — Google's own
`siteSearch` API parameter has no multi-domain form. This provider instead
builds the restriction directly into the query text via Google's `site:`
operator, joined with `OR` (`settings.site_restriction_clause`) — ordinary
query syntax, not a special parameter. Computed from
`settings.trusted_domains` at search time, so overriding that field
actually changes which domains are searched (not baked into a static
template — see `settings.py`'s own docstring for why that distinction
matters).

## Confidence

Every result's confidence comes from `application/search/confidence.py`'s
domain tables, not this provider itself: Reuters/Bloomberg score `0.94`;
BusinessWire/PRNewswire/GlobeNewswire/Yahoo Finance score `0.92` — the
same regardless of which provider happened to find that URL (see that
module's own docstring for why domain overrides take priority over a
provider's base score, and why the wire-service outlets are grouped at
one tier while Reuters/Bloomberg sit at another).

## Configuration (`settings.py`)

Shares `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` with
`infrastructure/search/google/` — same underlying credential.

| Setting | Default | Purpose |
|---|---|---|
| `trusted_domains` | `TRUSTED_NEWS_DOMAINS` | Domains every query is restricted to. |
| `query_templates` | See `DEFAULT_QUERY_TEMPLATES` | Executive-movement keyword combinations (appointed/named/promoted/resigns/steps down/board). |
| `max_results` | `5` | Results requested per query. |

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `NewsProvider` — the `SearchProviderPort` implementation. |
| `settings.py` | `NewsProviderSettings`, `TRUSTED_NEWS_DOMAINS`, `site_restriction_clause()`. |

## Testing

`tests/unit/news_search/` — mocked `httpx` transport only. Covers
settings validation, `site_restriction_clause`'s output, every query
actually carrying the trusted-domain restriction, a custom
`trusted_domains` override actually changing the query sent, confidence
assignment for a Reuters vs. a BusinessWire result, missing-name handling,
and every-query-failing status.
