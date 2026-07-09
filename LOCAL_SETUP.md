# Running the Executive Processing Pipeline on a developer laptop

This is a companion to the top-level [`README.md`](README.md), specifically
for getting `run_local.py` working end to end with real internet access —
Playwright installation, `.env.local` configuration, the pre-flight
`setup_local.py` checks, and Development Mode.

## 1. Install dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # only if you'll also run tests/linters
```

## 2. Install Playwright's browser

`requirements.txt` installs the `playwright` Python package, but Playwright
manages its own browser binaries separately — they aren't part of the pip
package:

```bash
playwright install chromium
```

This downloads a Chromium build matched to your installed `playwright`
version into Playwright's own cache directory. Run it once per machine (or
whenever you upgrade `playwright` in `requirements.txt`).

**If you're on a machine that already has a Chromium binary Playwright
doesn't recognize** (a pre-provisioned sandbox, a container image with its
own Chromium, a corporate-managed browser install) — this happens more
often than you'd expect, and `playwright install chromium` isn't always the
right fix (it may not be able to download at all, or may install a build
that coexists confusingly with the one you already have. Point
`BROWSER_SEARCH_EXECUTABLE_PATH` (see `.env.local.example`) at your
existing binary instead of installing a second one:

```bash
export BROWSER_SEARCH_EXECUTABLE_PATH=/path/to/your/chrome
```

`setup_local.py` (below) checks this for you and tells you exactly which
path to set if Playwright's own resolution can't find a matching browser.

## 3. Configure `.env.local`

```bash
cp .env.local.example .env.local
```

`.env.local.example` pre-fills `BrowserSearchProvider` with DuckDuckGo's
HTML-only results endpoint (`https://html.duckduckgo.com/html/`) as a
concrete, working starting point — see that file's own comments for why
this is separate from the app-wide `.env.example`, and for how to point it
at a different search engine (nothing about the target is hardcoded in
Python; every value is read from this file at runtime).

Before automating queries against any real search engine, confirm you're
authorized to do so under its terms of service — the same rule
`infrastructure/search/browser/README.md` already documents.

## 4. Verify your environment

```bash
python setup_local.py
```

Checks, in order: Python version, Playwright installed, a matching
Chromium browser installed, internet connectivity, DNS resolution,
`BrowserSearchProvider` configuration, and that the output directory is
writable. Each line is `[PASS]`, `[WARN]` (an optional feature will be
degraded or skipped, the rest of the pipeline still runs), or `[FAIL]`
(fix this first). Exits non-zero only on a `[FAIL]`.

`run_local.py` (next section) runs these same checks automatically before
every run — you don't have to run this by hand, but it's useful on its own
when something isn't working and you want to know exactly what.

## 5. Run the pipeline

```bash
python run_local.py path/to/your.xlsx --limit 10
```

This loads `.env.local`, runs `setup_local.py`'s checks (aborting on a
`[FAIL]`; add `--skip-checks` to bypass), then delegates entirely to
[`run_pipeline.py`](run_pipeline.py) — every argument except `--skip-checks`
is passed straight through. See `python run_pipeline.py --help` for the
full list (`--sheet`, `--limit`, `--output-dir`, `--dev-mode`, etc.).
Output — `results.xlsx`, `processing_report.json`, `logs/` — goes to
`run_output/` by default (`PIPELINE_OUTPUT_DIR` in `.env.local`, or
`--output-dir`).

You can also run `run_pipeline.py` directly (it does not load `.env.local`
itself — only `run_local.py` does that) if you've already exported the
same variables into your shell:

```bash
python run_pipeline.py path/to/your.xlsx --limit 10 --dev-mode
```

## 6. Development Mode

`ProviderHealthTracker` trips a circuit breaker after 3 consecutive
provider failures — correct in production, but counterproductive on a
laptop where a VPN, corporate proxy, or firewall can produce several
connection-level failures in a row that say nothing about whether the
target site is reachable in general. `--dev-mode` (or
`PIPELINE_DEV_MODE=true` in `.env.local`, already set in
`.env.local.example`) changes exactly one thing: a failure that looks like
a network/connectivity problem — a blocked connection, DNS failure, or an
HTTP 403 at the connect/robots stage (see `run_pipeline.py`'s own
`_is_network_policy_failure`) — no longer counts towards a provider's
consecutive-failure streak. A provider that reaches the real destination
and gets a genuine content-level failure (404, 500, a timeout after
retries against a reachable host) is tracked exactly as before —
Development Mode never changes how a real website failure is handled.
Off by default.

## Troubleshooting

**"It looks like you are using Playwright Sync API inside the asyncio
loop."** — This is Playwright's own error when a second browser-launch
attempt starts after an earlier one failed mid-launch in the same
process. It shows up here specifically when
`BrowserSearchProvider`/Playwright's own executable-path resolution
doesn't find a real Chromium binary (a `BrowserType.launch: Executable
doesn't exist at ...` error immediately precedes it in the log) — the
retry that follows is what triggers the asyncio message, not the real
problem. Run `python setup_local.py` and follow its "Browser installed"
line; it names the exact `BROWSER_SEARCH_EXECUTABLE_PATH` to set.

**`net::ERR_TUNNEL_CONNECTION_FAILED` / `net::ERR_CONNECTION_REFUSED` /
`net::ERR_NAME_NOT_RESOLVED`** — Chromium could not reach the configured
search engine at all (a blocked network path, not a DNS or destination-
site problem you can fix in this codebase). `BrowserSearchProvider`
retries per its configured policy and then reports `FAILURE` for that
query — expected behavior on a restricted network. Development Mode (see
above) keeps this from tripping the circuit breaker for every other
provider afterward.

**`setup_local.py` reports `[WARN] BrowserSearchProvider configuration`**
— `BROWSER_SEARCH_URL_TEMPLATE` isn't set. This is optional: the rest of
the pipeline (Company Website, Comparison, Inflection Detection) runs
fine without it. Copy `.env.local.example` to `.env.local` for a working
default.

## Files this adds

| File | Purpose |
|---|---|
| `.env.local.example` | Checked-in sample `BrowserSearchProvider` (DuckDuckGo) + Development Mode configuration for local runs. Copy to `.env.local` (gitignored) to use. |
| `setup_local.py` | Pre-flight environment verification — no business logic, only checks. |
| `run_local.py` | Loads `.env.local`, runs `setup_local.py`'s checks, then delegates to `run_pipeline.py`. Contains no pipeline logic of its own. |
| `run_pipeline.py` | The actual runner — Import Engine, Cleaning Engine, `ExecutiveProcessingOrchestrator.process_batch()` — unchanged in shape, now with `--dev-mode` and `PIPELINE_OUTPUT_DIR`/`PIPELINE_DEV_MODE` environment-variable defaults. |
