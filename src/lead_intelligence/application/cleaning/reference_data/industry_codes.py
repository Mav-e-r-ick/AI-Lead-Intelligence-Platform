"""Bundled, versioned classification-code reference tables for CLN-054.

WHY THESE TABLES ARE PARTIAL:
Full NAICS/SIC/ISIC/etc. reference tables run to thousands of entries and
are revised on a multi-year cycle (e.g. NAICS revises every 5 years). This
module ships a small, real starting subset (values observed during Import
Engine dataset profiling, so they're known-good) rather than a fabricated
"complete" table — see CLN-054's Potential Risks in docs/CLEANING_RULES.md
for why a stale/incomplete table is an accepted, documented tradeoff here,
not an oversight. Production use should grow these from real data.
"""

from lead_intelligence.application.cleaning.field_contract import (
    NAICS_CODE,
    UK_SIC_CODE,
    US_SIC1987_CODE,
    US_SIC8_CODE,
)

#: canonical code field name -> set of known-valid codes for that scheme.
#: A scheme absent from this dict is skipped by CLN-054, never guessed at
#: (mirrors CLN-042's "skip silently if no configured pattern" policy).
KNOWN_CLASSIFICATION_CODES: dict[str, frozenset[str]] = {
    NAICS_CODE: frozenset({"311111", "561110", "611519", "522130"}),
    US_SIC1987_CODE: frozenset({"2047", "8741", "8249", "6061"}),
    US_SIC8_CODE: frozenset({"20479902", "87410100", "82490100", "60610000"}),
    UK_SIC_CODE: frozenset({"1092", "7022", "8532", "64921"}),
}
