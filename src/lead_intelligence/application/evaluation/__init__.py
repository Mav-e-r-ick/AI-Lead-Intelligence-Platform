"""The Evaluation & Validation module.

Public entry points: PipelineRunner (runner.py), build_row (row_builder.py),
compute_summary (metrics.py), write_csv_report / write_summary_report /
write_evaluation_run (export.py). See README.md in this folder for how the
pieces fit together.

Version 1 scope only: this module measures how the existing Executive
Processing Pipeline performs on a real Excel dataset — it implements no
new provider, no AI, no automation, and makes no change to any existing
engine, coordinator, or framework. It only calls the same
ImportDatasetUseCase / CleanDatasetUseCase / ProcessExecutiveUseCase every
other caller of this platform uses, once per executive, and reports what
came back.
"""
