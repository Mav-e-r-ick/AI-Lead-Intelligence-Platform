# Executive Processing Pipeline

Processes one executive from start to finish using every module already
built for this platform — no new provider, no AI, no messaging, no
automation, and no change to any existing engine or framework. This
package only sequences calls to already-existing coordinators/engines and
aggregates their own result types into one `ExecutiveProcessingReport`.

## Scope: what Version 1 does and does not do

**Does:** given one existing (cleaned) executive record, run it through
enrichment (Company Website Provider + Google Search Provider, via the
existing `EnrichmentCoordinator`), aggregate the resulting
`ObservationCandidate`s, run the Executive Comparison Engine, run the
Inflection Detection Engine, and — only if a `VerificationCoordinator` was
configured — verify the executive's already-known email address. Every
stage's own result type is carried into one `ExecutiveProcessingReport`,
with per-stage error handling so one stage's unexpected failure never
discards what earlier stages already produced.

**Does not:** implement any new provider, call an AI/LLM, generate or send
any outreach message, automate anything beyond one explicit `process()`
call per executive, or change the public contract of
`EnrichmentCoordinator`, `ComparisonEngine`, `InflectionDetectionEngine`,
or `VerificationCoordinator`.

## How the pieces communicate

```
ProcessExecutiveUseCase                 (application/use_cases/process_executive.py)
        |
        v
ExecutiveProcessingOrchestrator         (orchestrator.py)
        |
        |-- resolve_name(cleaned_values)         "no name -> FAILED, nothing else runs"
        |
        |-- for subject_type in (PERSON, COMPANY):
        |       EnrichmentCoordinator.enrich(subject_type, subject_id, known_attributes)
        |       (Google Search only supports PERSON; Company Website only supports COMPANY —
        |        querying both subject types is what lets each one run)
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
  + comparison_result: ComparisonResult | None
  + inflection_report: InflectionReport | None
  + verification_report: VerificationReport | None
  + status: ExecutiveProcessingStatus
  + stage_errors: tuple[str, ...]
```

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
catches a raising provider). Taken to its logical conclusion at the top of
the pipeline: an unexpected exception in the Comparison Engine, say, must
not prevent the report from at least recording what enrichment already
collected. `ExecutiveProcessingOrchestrator.process()` never raises for an
ordinary processing failure — every failure mode is reported via
`ExecutiveProcessingReport.status`/`stage_errors`, never a raised exception.

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
| `PARTIAL` | A `ComparisonResult` was produced, but at least one other stage (enrichment for either subject type, inflection detection, or verification) encountered an error. |
| `SUCCESS` | Every applicable stage ran without error. |

## Why the report embeds each stage's own result type instead of flattening

`ComparisonResult`, `InflectionReport`, and `VerificationReport` are
already rich, well-tested output types with their own summaries/detected
events/provider results. Duplicating their fields into new,
pipeline-specific fields would be exactly the "framework redesign" this
task excludes — `ExecutiveProcessingReport` carries each one directly (or
`None` if that stage didn't run), so nothing is ever renamed or
reinterpreted. "Comparison Summary" is `comparison_result.summary`;
"Detected Inflections" is `inflection_report.inflections`; "Verification
Results" is `verification_report.provider_results`.

## Files

| File | Responsibility |
|---|---|
| `orchestrator.py` | `ExecutiveProcessingOrchestrator` — sequences enrichment (both subject types), comparison, inflection detection, and optional verification; per-stage error handling; status derivation; logging. |
| `application/dto/executive_pipeline_models.py` | `ExecutiveProcessingStatus`, `ExecutiveProcessingReport`. |
| `application/use_cases/process_executive.py` | `ProcessExecutiveUseCase` — thin orchestration entry point. |

Tests: `tests/unit/executive_pipeline/` — missing-executive-name handling,
the happy path (all stages succeed, including a detected Promotion),
subject-type routing (Person- and Company-scoped providers both run;
providers supporting neither never run), observation aggregation,
verification scope (skipped when not configured, skipped when no email is
known, receives the existing record's email), per-stage error handling
for all four stages (each triggered via a genuinely invalid sub-profile,
not an artificial fake), status derivation, and determinism — all against
fake enrichment/verification providers. `tests/integration/test_executive_pipeline.py`
proves the same orchestrator processes one executive correctly through
the *real* `CompanyWebsiteProvider`, `GoogleSearchProvider`, and
`NeverBounceEmailProvider` (each HTTP-mocked, never a real network call),
with no fakes standing in for any of the orchestrator's own collaborators.
