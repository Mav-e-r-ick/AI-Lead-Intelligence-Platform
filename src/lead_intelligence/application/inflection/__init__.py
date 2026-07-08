"""The Inflection Detection Engine.

Public entry points: InflectionDetectionEngine (engine.py),
InflectionRuleRegistry (registry.py), ALL_RULES (rules.py),
InflectionProfile / default_profile (config.py). See README.md in this
folder for how the pieces fit together.

Version 1 scope only: this engine converts a ComparisonResult (from the
Executive Comparison Engine) into deterministic, explainable business
events — Promotion, Demotion, Company Change, Possible Resignation,
Contact Information Changed, Executive Newly Appeared, Executive No
Longer Found. No AI, no Google Search, no LinkedIn, no email/phone
verification, no outreach messaging.
"""
