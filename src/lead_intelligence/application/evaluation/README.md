# Evaluation & Validation Module

Measures how well the already-built Executive Processing Pipeline performs
on a real Excel dataset of executives — no new provider, no AI, no
automation, and no change to any existing engine or framework. This
package only calls the platform's existing use cases (`ImportDatasetUseCase`,
`CleanDatasetUseCase`, `ProcessExecutiveUseCase`), once per executive, and
turns their combined output into a flat, CSV-friendly row plus aggregate
summary metrics.

## Scope: what Version 1 does and does not do

**Does:** given an Excel file, import it, clean it, run every resulting
executive through the real `ProcessExecutiveUseCase`, and produce (a) one
`ExecutiveEvaluationRow` per executive with CSV-ready flattened fields, (b)
one `EvaluationSummary` of platform-wide metrics, and (c) a CSV report and
a JSON summary report on disk.

**Does not:** implement any new enrichment/verification provider, call an
AI/LLM, automate anything beyond one explicit `PipelineRunner.run()` call,
or change the public contract of `ImportDatasetUseCase`, `CleanDatasetUseCase`,
`ProcessExecutiveUseCase`, or anything they depend on. This module reads
`ExecutiveProcessingReport`s; it never constructs one differently than
`ExecutiveProcessingOrchestrator` already does.

## How the pieces communicate

```
scripts/run_evaluation.py                      (CLI entry point; wires real infra)
        |
        v
PipelineRunner.run()                           (runner.py)
        |
        |-- ImportDatasetUseCase.execute()             -> ImportedLeadDataset
        |-- CleanDatasetUseCase.execute()               -> CleaningResult
        |
        |-- for each CleanedLeadRecord:
        |       subject_id = f"row:{record.raw_record.row_number}"
        |       try: ProcessExecutiveUseCase.execute(record, subject_id)
        |             -> ExecutiveProcessingReport
        |             -> build_row(report, record.cleaned_values)   (row_builder.py)
        |       except Exception: _error_row(...)   (batch-level fail-safe)
        |
        |-- compute_summary(rows)                       (metrics.py)
        |
        v
EvaluationRun                                  (application/dto/evaluation_models.py)
  = source_description, rows: tuple[ExecutiveEvaluationRow, ...],
    summary: EvaluationSummary, started_at, completed_at

write_evaluation_run(run, csv_path, summary_path)      (export.py)
  -> executive_report.csv + processing_summary.json
```

## Why row-building and metrics are separate from `ExecutiveProcessingReport`

`ExecutiveProcessingReport` embeds each stage's own rich result type
(`ComparisonResult`, `InflectionReport`, `VerificationReport`) — exactly
right for programmatic use, exactly wrong for a CSV column. `row_builder.py`
flattens each report into one `ExecutiveEvaluationRow` of plain
strings/numbers, and `metrics.py` aggregates those flattened rows into one
`EvaluationSummary`. Neither file changes what the Executive Processing
Pipeline computes — they only reformat it for measurement.

## Why "results found" and "searches completed" are different fields

The task's own vocabulary distinguishes them: a Google search can run
successfully and still find nothing. `ExecutiveEvaluationRow.providers_executed`
(comma-joined `report.providers_executed`) answers "did the provider run
at all," while `google_results_found`/`company_website_results_found`
(per-provider counts of `report.observations_collected`) answer "how much
did it find." `metrics.py` mirrors the same distinction: `google_searches_completed`
counts execution, `company_websites_found` requires at least one result —
matching the task's own asymmetric wording ("Google searches completed" vs.
"Company websites found").

## Why "failed searches" means a technical failure, not "found nothing"

`compute_summary` counts a row as a failed search only when its `errors`
field contains an `"Enrichment ("`-prefixed stage error — the exact message
`ExecutiveProcessingOrchestrator` already produces when an enrichment stage
raises. Zero results from a provider that ran successfully is not a
failure; it's evidence the platform correctly found nothing to report.

## Verification status semantics

`row_builder._verification_status` derives one of:

| Value | Meaning |
|---|---|
| A real `VerificationStatus` value (e.g. `valid`, `invalid`) | Verification actually ran and returned at least one provider result. |
| `no_email` | No email address was resolvable from the record, so verification was never attempted. |
| `not_configured` | An email was known, but no `VerificationCoordinator` was wired into the pipeline. |
| `error` | The verification stage itself raised (per `ExecutiveProcessingOrchestrator`'s own "Verification failed: ..." stage error). |

`metrics.compute_summary`'s `verification_success_rate` excludes
`no_email`/`not_configured`/`error` rows from its denominator — it answers
"of the emails we actually checked, how many came back valid," not diluted
by executives who were never eligible for verification.

## CSV report columns

One row per executive, in `ExecutiveEvaluationRow` field order: `subject_id`,
`executive_name`, `company`, `website_searched`, `providers_executed`,
`company_website_results_found`, `google_results_found`,
`observations_collected`, `comparison_summary`, `inflections_detected`,
`verification_status`, `processing_duration_ms`, `errors`, `status`.
Column order is derived programmatically from `dataclasses.fields(ExecutiveEvaluationRow)`
in `export.py`, so the CSV can never silently drift from the dataclass.

## Summary metrics (`EvaluationSummary`)

| Metric | Definition |
|---|---|
| `total_executives_processed` | Number of rows produced (one per cleaned record). |
| `success_rate` | % of rows with `status == SUCCESS`. |
| `failed_searches` | Rows whose `errors` contains an enrichment-stage failure. |
| `company_websites_found` | Rows with at least one Company Website observation. |
| `google_searches_completed` | Rows where `google_search` appears in `providers_executed` (ran, regardless of results). |
| `promotions_detected` / `company_changes_detected` / `missing_executives` | Rows whose `inflections_detected` lists `promotion` / `company_change` / `executive_no_longer_found`. |
| `verification_success_rate` | % of *actually verified* rows (excludes `no_email`/`not_configured`/`error`) whose status is `valid`. |

## Files

| File | Responsibility |
|---|---|
| `runner.py` | `PipelineRunner` — imports, cleans, and processes every executive; per-record fail-safe; builds the `EvaluationRun`. |
| `row_builder.py` | `build_row()` — flattens one `ExecutiveProcessingReport` into one `ExecutiveEvaluationRow`. |
| `metrics.py` | `compute_summary()` — aggregates rows into one `EvaluationSummary`. |
| `export.py` | `write_csv_report()`, `write_summary_report()`, `write_evaluation_run()` — CSV/JSON export. |
| `application/dto/evaluation_models.py` | `ExecutiveEvaluationRow`, `EvaluationSummary`, `EvaluationRun`. |
| `scripts/run_evaluation.py` | Standalone CLI: wires real infrastructure (Excel reader, Cleaning Pipeline, Enrichment/Comparison/Inflection/Verification) and runs one evaluation end to end. Not part of the importable application. |

Tests: `tests/unit/evaluation/` — `fixtures.py` (shared
`ExecutiveProcessingReport`/`InflectionReport`/`VerificationReport`
builders), `test_row_builder.py` (every flattened field, all four
verification-status branches, comparison/inflection formatting),
`test_metrics.py` (every summary metric, including the "found" vs.
"completed" and "excluded from verification denominator" distinctions),
`test_export.py` (CSV/JSON structure, `None`-to-blank conversion, parent
directory creation), and `test_runner.py` (a real Import Engine + Cleaning
Engine against a tiny in-memory workbook, a fake `ProcessExecutiveUseCase`,
row-per-executive processing, subject_id derivation, per-record fail-safe
handling, and source-description defaulting/override).

## Running an evaluation

```bash
python scripts/run_evaluation.py path/to/executives.xlsx --output-dir reports
```

Writes `reports/executive_report.csv` and `reports/processing_summary.json`.
`GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` and `NEVERBOUNCE_API_KEY`
are optional — if unset, the run proceeds without that provider/verifier
and logs a warning, rather than failing.
