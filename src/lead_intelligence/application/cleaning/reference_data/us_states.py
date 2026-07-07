"""US state/territory name <-> abbreviation table for CLN-037.

Only US states are provided today, matching the only region observed in
the reference dataset — deliberately not extended to other countries'
subdivisions without real evidence of what those look like (see
docs/CLEANING_RULES.md CLN-037's Potential Risks).
"""

US_STATE_NAME_TO_ABBREVIATION: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

#: "of"/"the" stay lowercase in proper display casing (e.g. "District of Columbia").
_LOWERCASE_WORDS = {"of", "the"}


def _display_case(name: str) -> str:
    words = name.split(" ")
    return " ".join(
        word if word in _LOWERCASE_WORDS else word.capitalize() for word in words
    )


US_STATE_ABBREVIATION_TO_NAME: dict[str, str] = {
    abbreviation: _display_case(name)
    for name, abbreviation in US_STATE_NAME_TO_ABBREVIATION.items()
}
