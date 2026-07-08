"""The Executive Comparison Engine.

Public entry points: ComparisonEngine (engine.py), ComparisonProfile /
default_profile (config.py). See README.md in this folder for how the
pieces fit together.

Version 1 scope only: this engine identifies *differences* between an
existing (cleaned) executive record and newly collected
ObservationCandidates. It does not decide what a difference *means* — no
promotion/resignation/inflection classification, no AI, no verification.
That interpretation is explicitly future work.
"""
