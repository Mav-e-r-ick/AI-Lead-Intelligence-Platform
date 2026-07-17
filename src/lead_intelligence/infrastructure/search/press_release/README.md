# Press Release Provider

`PressReleaseProvider` — one of the five federated Search Layer providers
(see `application/search/README.md`'s "Federated Search" section).
Crawls the executive's own company website, scoped specifically to its
press/newsroom/media/investor-relations/announcements section, looking
for executive appointment announcements. Implements `SearchProviderPort`
— returns `SearchResult`s only.

## Why this is a separate provider from CompanyCrawlerProvider, not a mode of it

This task explicitly names both as distinct providers with distinct
search scopes and explicitly says "Keep the existing implementation" for
`CompanyCrawlerProvider` — so this is a new, independent crawl of the same
site with a narrower, differently-weighted keyword set (`press`,
`newsroom`, `media`, `investor(-relations)`, `announcement(s)`,
`release(s)` — deliberately excludes `leadership`/`about`/`team` etc.,
which `CompanyCrawlerProvider` already covers), not a parameter added to a
provider this task says must stay unmodified. Running both is intentional,
federated redundancy: a "Leadership" page and a "Press Releases" index
often carry different, complementary evidence about the same appointment.

## Why this is a sibling to `company_crawler/`, not a shared/parameterized crawl engine

Structurally near-identical BFS crawl loop (`crawler.py`,
`link_prioritization.py`), but deliberately independent modules rather
than one shared, parameterized engine — refactoring `company_crawler`'s
internals to share code with this provider, even without changing its
observable behavior, was judged out of scope for "keep the existing
implementation." See `link_prioritization.py`'s own module docstring.

## Confidence

Every result defaults to `0.95` (`application/search/confidence.py`'s
`PROVIDER_BASE_CONFIDENCE["press_release"]`) — the company speaking for
itself, one step removed from its own website (`company_crawler`'s
`1.00`).

## Configuration (`settings.py`)

Same shape and defaults as `company_crawler/settings.py` — no
`from_env()`, since crawling a dataset row's own company website needs no
authorization decision.

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `PressReleaseProvider` — the `SearchProviderPort` implementation. |
| `settings.py` | `PressReleaseProviderSettings` — crawl budget, timeout/retry policy. |
| `link_prioritization.py` | Press/newsroom/media/investor-relations/announcements keyword scoring. |
| `crawler.py` | `crawl_company_press_pages` — the breadth-first crawl loop. |

## Testing

`tests/unit/press_release/` — fake, in-memory Browser/Page and a mocked
`httpx` transport for robots.txt checks; no test here launches a real
browser or touches the real network. Mirrors `tests/unit/company_crawler/`'s
coverage shape (link scoring/exclusion, crawl budget/depth, robots.txt
handling, homepage-unreachable vs. empty-result distinction), plus a
dedicated assertion that every returned result carries `confidence=0.95`.
