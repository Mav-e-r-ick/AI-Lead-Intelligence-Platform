"""Legal-entity suffix table for CLN-026 (Legal Suffix Standardization).

Maps a recognized suffix variant (matched at the end of a company name,
case-insensitively) to its canonical form. Used only when CLN-026 is
enabled with target="canonicalize"; the strip variant simply removes any
matched suffix instead of replacing it.
"""

DEFAULT_LEGAL_SUFFIXES: dict[str, str] = {
    "inc": "Inc.",
    "inc.": "Inc.",
    "incorporated": "Inc.",
    "corp": "Corp.",
    "corp.": "Corp.",
    "corporation": "Corp.",
    "co": "Co.",
    "co.": "Co.",
    "company": "Co.",
    "llc": "LLC",
    "l.l.c.": "LLC",
    "llp": "LLP",
    "l.l.p.": "LLP",
    "ltd": "Ltd.",
    "ltd.": "Ltd.",
    "limited": "Ltd.",
    "plc": "PLC",
}
