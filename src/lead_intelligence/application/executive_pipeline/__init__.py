"""The Executive Processing Pipeline.

Public entry point: ExecutiveProcessingOrchestrator (orchestrator.py). See
README.md in this folder for how the pieces fit together.

Version 1 scope only: this package processes one existing executive
record through every module already built for this platform — the
Enrichment Provider Framework (Company Website + Google Search providers),
the Executive Comparison Engine, the Inflection Detection Engine, and
(only if configured) the Contact Verification Framework's email
verification. It implements no new provider, no AI, no messaging, no
automation, and makes no change to any existing engine or framework — it
only sequences calls to them and aggregates their results.
"""
