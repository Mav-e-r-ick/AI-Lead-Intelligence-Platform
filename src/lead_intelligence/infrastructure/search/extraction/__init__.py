"""The Search Extraction Engine.

Public entry point: SearchExtractionEngine (engine.py) — SearchResults
in, ObservationCandidates out, completing the Search Layer RFC's
pipeline: Search Results (URLs only) -> Page Fetcher -> Content
Extractor -> Observation Extraction. See README.md in this folder for
how the pieces fit together.

Version 1 scope only: deterministic HTML parsing and rule-based fact
extraction — no AI, no LLM, no PDF support (PDF URLs and PDF responses
are skipped with a log line, never silently). Not yet wired into
ExecutiveProcessingOrchestrator — the same deliberate sequencing every
prior provider/engine followed (built and tested standalone first, wired
in as its own follow-up).
"""
