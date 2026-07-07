"""Acronym dictionary for CLN-004 (Title Acronym Casing Correction).

Maps the lowercase form of a known acronym to its correctly-cased form.
Matched whole-word/token only — see rules/identity.py.
"""

DEFAULT_ACRONYMS: dict[str, str] = {
    "crm": "CRM",
    "vp": "VP",
    "svp": "SVP",
    "evp": "EVP",
    "avp": "AVP",
    "cfo": "CFO",
    "ceo": "CEO",
    "coo": "COO",
    "cto": "CTO",
    "cio": "CIO",
    "cmo": "CMO",
    "chro": "CHRO",
    "r&d": "R&D",
    "it": "IT",
    "hr": "HR",
    "pr": "PR",
    "ux": "UX",
    "ui": "UI",
    "b2b": "B2B",
    "b2c": "B2C",
}
