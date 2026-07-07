"""Small, versioned, curated static reference data used by Business rules.

Injected into rules via the CleaningProfile mechanism in spirit (a rule
imports its default table from here, but a profile's `parameters` can
override it) rather than hardcoded deep inside rule logic — the same
"swap the reference data, keep the rule" principle used for external
vendors elsewhere in this platform, applied here to static lookup tables.

Each table here is intentionally a *starting point*, not exhaustive — real
production usage is expected to grow these lists over time (see each
table's rule entry in docs/CLEANING_RULES.md for the associated risk note).
"""
