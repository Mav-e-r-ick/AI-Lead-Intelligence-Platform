# Running the pipeline simulation in Visual Studio Code

`simulate_pipeline.py` runs the entire Executive Intelligence pipeline
against your spreadsheet — on any machine, with **no internet access, no
API keys, and no browser**. Give it a sheet; it does the rest.

It exists because of a specific, real problem: `run_pipeline.py` asks live
search providers to go find evidence on the internet. On a laptop behind a
corporate proxy, on a locked-down build agent, or before anyone has a
Google API key, every stage after "Search" receives nothing — so the
pipeline works perfectly and *appears to do nothing at all*. This script
supplies the one missing ingredient so the rest becomes visible.

## What's real and what isn't

| Real (the actual shipped code) | Simulated |
|---|---|
| Import Engine — reads your real .xlsx | |
| Cleaning Engine — all 68 rules | |
| Identity Resolution Engine | |
| Comparison Engine | |
| Inflection Detection Engine + all 7 rules | |
| `ExecutiveRepository` — a real SQLite database, really written to | |
| Message Generator | |
| `ExecutiveProcessingOrchestrator` | |
| | **Only the search evidence** (the `ObservationCandidate`s) |

Nothing here is a mock of a pipeline *stage* — the stages are the real,
shipped classes. Only the evidence fed into them is invented.

**Read every result as "this is what the platform would do given that
evidence", never as a finding about a real executive.**

## Setup (once)

```bash
pip install -r requirements.txt
pip install -e .
```

That's it. No `playwright install`, no API keys, no `.env` file — the
simulation touches none of that.

## Run it

**In VS Code:** open `simulate_pipeline.py` and press the ▶ Run button.
With no arguments it finds the first spreadsheet in `data/raw/`, `data/`,
or the current folder and simulates 20 executives.

**From a terminal, to control it:**

```bash
python simulate_pipeline.py "path/to/your sheet.xlsx" --limit 30
```

| Flag | What it does |
|---|---|
| `--limit N` | How many executives to simulate (default 20). |
| `--scenario NAME` | Force every executive down one path. One of `promotion`, `company_change`, `contact_change`, `confirmed`, `no_evidence`. |
| `--sheet NAME` | Pick a worksheet by name (default: auto-selected). |
| `--output-dir DIR` | Where results go (default `simulation_output/`). |
| `--verbose` | Also show the pipeline's own INFO logging. |

### Running it from VS Code *with* flags

VS Code's ▶ button passes no arguments. To use flags from inside the
editor, create `.vscode/launch.json` (it's gitignored, so it stays yours)
and press F5:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Simulate pipeline",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/simulate_pipeline.py",
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}",
      "args": ["data/raw/your sheet.xlsx", "--limit", "30"]
    }
  ]
}
```

Because it's a normal launch config, VS Code breakpoints work — you can
set one inside any engine and step through a real detection.

## What you'll see

For each executive, its whole journey through all six stages:

```
[2/10] Erik Lam  (scenario: promotion)
    subject_id       : row:3
    1 Identity       : candidate_review
    2 Evidence       : 2 simulated observation(s)
    3 Comparison     : 1 changed, 1 matched, 3 missing
                       (title: 'Chief Relationship Officer' -> 'Chief Executive Officer')
    4 Inflection     : promotion (confidence 0.90, rule INF-001)
    5 Database       : 1 field(s) written
    6 Message        : Hi Erik Lam, congratulations on your promotion to Chief
                       Executive Officer at Coatue Management, L.L.C.! ...
```

Then a summary, and three files in `simulation_output/`:

- `simulation_results.xlsx` — one row per executive
- `simulation_report.json` — the same data, machine-readable
- `simulation.db` — the SQLite database that was actually written (open it
  in any SQLite viewer; the `executives` table carries the updated values
  and a `last_inflection_type` / `last_inflection_confidence` stamp)

## Why it runs two passes

Detecting a *change* needs something to compare against, so a single pass
over an empty database can only ever conclude "first time I've seen this
person". The script therefore does in one run what a real deployment does
over time:

1. **Pass 1 — baseline.** Seed the database from your spreadsheet: "what
   we knew as of yesterday." No detection attempted.
2. **Pass 2 — today's search.** Run the real pipeline against simulated
   new evidence. Identity Resolution matches each executive back to their
   Pass 1 row, Comparison diffs the two, and everything downstream reacts.

## The five scenarios

| Scenario | Simulated evidence | What should happen |
|---|---|---|
| `promotion` | A title one rung up the seniority ladder, plus the name | `promotion` (INF-001) |
| `company_change` | A different (fictional) employer, plus the name | `company_change` (INF-003) |
| `contact_change` | A new email, **deliberately with no name** | `contact_info_changed` (INF-005) |
| `confirmed` | The title they already hold | Nothing — correctly silent |
| `no_evidence` | Nothing at all | Nothing — correctly silent |

Which executive gets which is a stable hash of their row, so **the same
sheet always produces the same simulation**. There is no randomness to
re-seed; re-runs are directly comparable.

Two details in that table are deliberate, not arbitrary:

- **`contact_change` sends no name.** That mirrors the real
  `SearchExtractionEngine`, which fills `full_name`/`title`/`company_name`
  together from one announcement pattern but extracts `email`/`phone`
  independently — so in production a bio card really can yield an email
  with no parseable name, and simulated evidence has to have the same
  shape to be worth anything. (This exact case exposed a real bug the
  first time this script ran; see the note below.)
- **`promotion` checks its own new title is *distinguishable*.** `title`
  is compared fuzzily, so a higher-ranked title can still read as
  unchanged: "Chief Experience Officer" → "Chief Executive Officer" is a
  genuine promotion by rank but scores 0.809 against a 0.80 threshold, so
  Comparison calls it a match and nothing fires. The script checks each
  ladder rung with the same `similarity` function and the same live
  threshold the engine uses, and picks the first that clears both bars.

## Two summary lines worth understanding

- **`Title Changed But Direction Unknown`** — a title really changed, but
  no rule drew a conclusion, because `seniority_rank` doesn't recognize
  the old title and so can't tell up from down. That's the honest limit of
  a keyword ranking table, not a silent failure.
- **`Promotion Not Simulable (already top rank)`** — the executive is
  already at the top of the ladder, so no plausible promotion could be
  invented. A property of this script, never of the pipeline.

## A note on what simulation is for

The first run of this script against real data immediately exposed a
genuine product bug: for the `contact_change` scenario,
`executive_no_longer_found` (0.85) fired *alongside* the correct
`contact_info_changed` (0.70) and outranked it, so the drafted message was
"it's been a while since we've been in touch" instead of the contact-update
one. An earlier fix had guarded only `title` and `company`; email and phone
turned out to be the *more* common trigger, because they're the fields
that really do arrive without a name attached.

That's the point of running the whole pipeline on real data with
controlled evidence: it finds things that unit tests, which supply only
the shapes you already thought of, structurally cannot.

## Related

- [`LOCAL_SETUP.md`](LOCAL_SETUP.md) — running `run_pipeline.py` with
  **real** internet access and real search providers.
- [`README.md`](README.md) — the platform overall.
