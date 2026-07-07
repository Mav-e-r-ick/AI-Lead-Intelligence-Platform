"""Region-scoped street-suffix abbreviation tables for CLN-040.

Keyed by ISO alpha-2 country code (see country_codes.py) so a US-centric
table is never silently applied to a non-US address. Only "US" is
populated today, matching the reference dataset's evidence.
"""

US_STREET_SUFFIX_ABBREVIATIONS: dict[str, str] = {
    "street": "St.",
    "avenue": "Ave.",
    "boulevard": "Blvd.",
    "drive": "Dr.",
    "lane": "Ln.",
    "road": "Rd.",
    "court": "Ct.",
    "place": "Pl.",
    "square": "Sq.",
    "terrace": "Ter.",
    "highway": "Hwy.",
    "parkway": "Pkwy.",
}

STREET_SUFFIX_ABBREVIATIONS_BY_COUNTRY: dict[str, dict[str, str]] = {
    "US": US_STREET_SUFFIX_ABBREVIATIONS,
}
