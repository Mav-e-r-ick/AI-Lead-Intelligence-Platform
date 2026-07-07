"""Name-particle exception list for CLN-002 (Name Casing Standardization).

Particles that follow their own established capitalization instead of
naive per-word Title Case. Keys are lowercase tokens; values are how they
should render. "mc"/"mac" are handled as prefixes (see rules/identity.py),
not standalone tokens.
"""

DEFAULT_LOWERCASE_PARTICLES: frozenset[str] = frozenset(
    {"van", "von", "der", "den", "de", "la", "le", "du", "da", "dos", "das"}
)

#: Prefixes that capitalize themselves plus the letter immediately after
#: them (e.g. "mcdonald" -> "McDonald", "o'brien" -> "O'Brien").
CAPITALIZED_NAME_PREFIXES: tuple[str, ...] = ("mc", "mac", "o'")
