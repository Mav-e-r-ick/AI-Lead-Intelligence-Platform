# Executive Processing Pipeline

Processes one executive — or a whole batch of executives — from start to
finish using every module already built for this platform: no new
provider, no AI, no messaging, no automation, and no change to any
existing engine or framework. This package only sequences calls to
already-existing coordinators/engines and aggregates their own result
types into one `ExecutiveProcessingReport` (per executive) or one
`ExecutiveIntelligenceReport` (per batch — the "Final Executive
Intelligence Report").

## Scope: what Version 1 does and does not do

**Does:** given one existing (cleaned) executive record, run it through
identity resolution (if configured), enrichment (Company Website
Provider, and any other `EnrichmentProviderPort` registered — e.g. Google
Search — via the existing `EnrichmentCoordinator`), search (Browser
Search Provider, and any other `SearchProviderPort` registered, via the
existing `SearchCoordinator`) followed by search extraction (turning
found URLs into evidence, via anything satisfying `SearchExtractionPort`
— in production, the real `SearchExtractionEngine`), combine every
`ObservationCandidate` collected from both evidence paths, run the
Executive Comparison Engine, run the Inflection Detection Engine, and —
only if a `VerificationCoordinator` was configured — verify the
executive's already-known email address. Every stage's own result type is
carried into one `ExecutiveProcessingReport`, with per-stage error
handling so one stage's unexpected failure never discards what earlier
stages already produced. `process_batch()` runs this for many executives,
continuing past any one executive's failure, and returns one combined
`ExecutiveIntelligenceReport` with batch-level statistics.

**Does not:** implement any new provider, call an AI/LLM, generate or
send any outreach message, automate anything beyond one explicit
`process()`/`process_batch()` call, or change the public contract of
`IdentityResolutionEngine`, `EnrichmentCoordinator`, `SearchCoordinator`,
`SearchExtractionEngine`, `ComparisonEngine`, `InflectionDetectionEngine`,
or `VerificationCoordinator`.

## How the pieces communicate

```
ProcessExecutiveUseCase                 (application/use_cases/process_executive.py)
        |
        v
ExecutiveProcessingOrchestrator.process()      (orchestrator.py)
        |
        |-- resolve_name(cleaned_values)         "no name -> FAILED, nothing else runs"
        |
        |-- IdentityResolutionEngine.resolve_record(record, PERSON, subject_id)
        |   (skipped if no engine configured — no IdentityCandidatePort
        |    infrastructure adapter exists yet; outcome recorded on the
        |    report, subject_id is NOT swapped — see "Why" below)
        |
        |-- for subject_type in (PERSON, COMPANY):
        |       EnrichmentCoordinator.enrich(subject_type, subject_id, known_attributes)
        |       (Google Search only supports PERSON; Company Website only supports COMPANY —
        |        querying both subject types is what lets each one run)
        |
        |-- SearchCoordinator.search(PERSON, subject_id, known_attributes)
        |   (skipped if no coordinator configured)
        |       |-- if results found and a SearchExtractionPort is configured:
        |       |       SearchExtractionEngine.extract(subject_id, results) -> ObservationCandidates
        |       |   (a search with no extraction engine records which providers ran
        |       |    but produces no observations — a configuration choice, not a failure)
        |
        |-- observations = enrichment_observations + search_extraction_observations
        |
        |-- ComparisonEngine.compare(existing_record, observations, subject_id)
        |
        |-- InflectionDetectionEngine.detect(comparison_result)   (skipped if comparison failed)
        |
        |-- resolve_email(cleaned_values)
        |-- VerificationCoordinator.verify(EMAIL, subject_id, email)   (skipped if not
        |    configured, or no email known)
        |
        v
ExecutiveProcessingReport                (application/dto/executive_pipeline_models.py)
  = executive_name, providers_executed, observations_collected
  + identity_resolution_outcome: IdentityResolutionOutcome | None
  + comparison_result: ComparisonResult | None
  + inflection_report: InflectionReport | None
  + verification_report: VerificationReport | None
  + status: ExecutiveProcessingStatus
  + stage_errors: tuple[str, ...]

ExecutiveProcessingOrchestrator.process_batch(records)
        |
        |-- for (record, subject_id) in records:
        |       try: process(record, subject_id)     (already never raises for ordinary failures)
        |       except Exception: build a FAILED report from resolve_name() alone
        |           (mirrors the Evaluation module's PipelineRunner batch fail-safe)
        v
ExecutiveIntelligenceReport               (the "Final Executive Intelligence Report")
  = executive_reports: tuple[ExecutiveProcessingReport, ...]   (one per input record, input order)
  + statistics: ExecutiveBatchStatistics    (total/succeeded/partial/failed, error counts, execution time)
  + started_at / completed_at / duration_ms
```

## Why identity resolution's outcome is recorded but its resolved id is not (yet) used as the pipeline's `subject_id`

No persistence exists — there is no identity store to merge into, no
`IdentityCandidatePort` infrastructure adapter, and no durable id to
carry forward between runs. Swapping the caller-supplied `subject_id`
mid-pipeline for an identity id that evaporates when the process exits
would be motion without progress. Version 1 records the engine's full
`IdentityResolutionOutcome` on the report (so the decision is visible and
auditable — auto-merge / candidate review / new identity, with its
extracted identity and scored candidates) and keeps the caller-supplied
`subject_id` for every other stage. This is the honest wiring until
persistence exists, not an oversight.

## Why search and search extraction are separate optional collaborators

They are separate modules with separate jobs, per the approved Search
Layer RFC — search finds URLs, extraction reads them. A configuration
that searches but cannot extract (no `SearchExtractionPort` configured)
collects evidence it can't use, so the orchestrator logs a warning in
that case and still records which search providers executed, rather than
failing or silently pretending nothing happened. `SearchExtractionPort`
is a `typing.Protocol` (unlike the other, ABC-based ports) specifically
so the already-built, already-tested `SearchExtractionEngine`
(`infrastructure/search/extraction/`) satisfies it structurally — zero
lines of that engine needed to change for this task's "only connect,
never redesign" scope.

## Why enrichment issues one `enrich()` call per subject type, not one call total

`CompanyWebsiteProvider` supports only `SubjectType.COMPANY` (it answers
"who does this company say its leaders are"); `GoogleSearchProvider`
supports only `SubjectType.PERSON` (it answers "what does the public web
say about this specific executive"). Both were deliberately scoped that
way when each was built, and changing either now would itself be a
framework redesign. So `_run_enrichment` calls
`EnrichmentCoordinator.enrich()` once for `PERSON` and once for `COMPANY`,
using the same opaque `subject_id` for both (this pipeline has no separate
Company Digital Twin id yet), and merges whichever providers/observations
each call produced. Each call has its own error handling, so one subject
type's enrichment failing never discards the other's results.

## Why every stage is wrapped in its own `try`/`except`

Mirrors the "one misbehaving component never sinks the whole run" pattern
already used by every coordinator in this platform
(`EnrichmentCoordinator` catches a raising provider; `VerificationCoordinator`
catches a raising provider; `SearchCoordinator` catches a raising search
provider). Taken to its logical conclusion at the top of the pipeline: an
unexpected exception in the Comparison Engine, say, must not prevent the
report from at least recording what enrichment already collected.
`ExecutiveProcessingOrchestrator.process()` never raises for an ordinary
processing failure — every failure mode is reported via
`ExecutiveProcessingReport.status`/`stage_errors`, never a raised
exception. `process_batch()` extends the same philosophy one level up: a
per-record `try`/`except` around `process()` itself means even a
genuinely unanticipated bug for one executive can't take down the rest of
the batch.

## Why verification uses the existing record's email, not a newly observed one

The Contact Verification Framework's job is "confirm this contact detail
is safe to use before outreach" — that only makes sense for a value the
platform actually intends to use, which is the executive's existing,
already-known email (the same `resolve_email` the Executive Comparison
Engine itself uses), not an unverified value a provider merely observed on
some webpage.

## `ExecutiveProcessingStatus`

| Status | When |
|---|---|
| `FAILED` | No executive name could be resolved from the input record (nothing else ran), or the Executive Comparison Engine itself failed. |
| `PARTIAL` | A `ComparisonResult` was produced, but at least one other stage (identity resolution, enrichment for either subject type, search, search extraction, inflection detection, or verification) encountered an error. |
| `SUCCESS` | Every applicable stage ran without error. |

## Why the report embeds each stage's own result type instead of flattening

`ComparisonResult`, `InflectionReport`, `VerificationReport`, and
`IdentityResolutionOutcome` are already rich, well-tested output types
with their own summaries/detected events/provider results/scored
candidates. Duplicating their fields into new, pipeline-specific fields
would be exactly the "framework redesign" this task excludes —
`ExecutiveProcessingReport` carries each one directly (or `None` if that
stage didn't run), so nothing is ever renamed or reinterpreted.
"Comparison Summary" is `comparison_result.summary`; "Detected
Inflections" is `inflection_report.inflections`; "Verification Results"
is `verification_report.provider_results`; "Identity Decision" is
`identity_resolution_outcome.decision`.

## Batch processing statistics (`ExecutiveBatchStatistics`)

| Field | Meaning |
|---|---|
| `total_executives` | How many records went in. |
| `succeeded` / `partial` / `failed` | Reports finishing with each `ExecutiveProcessingStatus`. |
| `executives_with_errors` | Reports carrying at least one stage error — a superset of `failed` (a `PARTIAL` report has errors too). |
| `stage_errors_total` | Every stage error across every report, summed. |
| `execution_time_total_ms` | Wall-clock time spent processing the whole batch (measured via `time.perf_counter()`, the same precision-timing convention `EnrichmentCoordinationMetrics`/`SearchCoordinationMetrics` already use — deliberately excluded from any determinism guarantee, like every other engine's own execution-time metric). |

## Files

| File | Responsibility |
|---|---|
| `orchestrator.py` | `ExecutiveProcessingOrchestrator` — `process()` sequences identity resolution, enrichment (both subject types), search + search extraction, comparison, inflection detection, and optional verification; `process_batch()` runs many executives with a batch-level fail-safe and computes statistics; per-stage error handling; status derivation; logging. |
| `application/dto/executive_pipeline_models.py` | `ExecutiveProcessingStatus`, `ExecutiveProcessingReport`, `ExecutiveBatchStatistics`, `ExecutiveIntelligenceReport`. |
| `application/ports/search_extraction_port.py` | `SearchExtractionPort` — the structural (`Protocol`) contract the orchestrator depends on, satisfied by the real `SearchExtractionEngine` without that engine needing to change. |
| `application/use_cases/process_executive.py` | `ProcessExecutiveUseCase` — thin orchestration entry point for `process()`. |

Tests: `tests/unit/executive_pipeline/` — `test_orchestrator.py` covers
the original scope (missing-executive-name handling, the happy path
including a detected Promotion, subject-type routing, observation
aggregation, verification scope, per-stage error handling, status
derivation, determinism, all against fake enrichment/verification
providers). `test_full_pipeline_stages.py` covers everything this task
added: identity resolution (outcome recorded, absent-engine vs.
stage-failure behavior, pipeline continues as `PARTIAL`), search +
extraction (results flowing into observations, no-coordinator vs.
no-extraction-engine vs. no-results behavior, independent stage-failure
handling for search vs. extraction), and `process_batch()` (one report
per record in input order, continuing past a failed executive, batch
statistics accuracy, an unexpected exception for one record yielding a
`FAILED` report with a best-effort `executive_name` while the rest of the
batch keeps going, and the empty-batch edge case). `tests/integration/test_executive_pipeline.py`
proves the original (pre-Identity-Resolution/Search) orchestrator
processes one executive correctly through the *real*
`CompanyWebsiteProvider`, `GoogleSearchProvider`, and
`NeverBounceEmailProvider` (each HTTP-mocked). `tests/integration/test_executive_intelligence_pipeline.py`
proves the *full* pipeline — every stage in the diagram above, including
Identity Resolution, Browser Search, and Search Extraction — through
real, unmodified modules end to end (an in-memory `IdentityCandidatePort`
is the only piece with no infrastructure adapter yet; `BrowserSearchProvider`
drives a fake browser instead of a real Chromium process; every other
network call is HTTP-mocked), for both a single executive and a batch.
