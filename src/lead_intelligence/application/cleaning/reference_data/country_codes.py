"""Country name <-> ISO 3166-1 alpha-2 table for CLN-038.

A starting subset (not the full ISO list) covering the country observed in
the reference dataset plus other common ones — grow as real datasets
require, per the same rationale as us_states.py.
"""

COUNTRY_NAME_TO_ISO_ALPHA2: dict[str, str] = {
    "united states": "US",
    "united states of america": "US",
    "canada": "CA",
    "united kingdom": "GB",
    "australia": "AU",
    "germany": "DE",
    "france": "FR",
    "india": "IN",
    "japan": "JP",
    "china": "CN",
    "brazil": "BR",
    "mexico": "MX",
    "spain": "ES",
    "italy": "IT",
    "netherlands": "NL",
    "ireland": "IE",
    "new zealand": "NZ",
    "singapore": "SG",
    "south africa": "ZA",
}

COUNTRY_ISO_ALPHA2_TO_NAME: dict[str, str] = {
    "US": "United States",
    "CA": "Canada",
    "GB": "United Kingdom",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "IN": "India",
    "JP": "Japan",
    "CN": "China",
    "BR": "Brazil",
    "MX": "Mexico",
    "ES": "Spain",
    "IT": "Italy",
    "NL": "Netherlands",
    "IE": "Ireland",
    "NZ": "New Zealand",
    "SG": "Singapore",
    "ZA": "South Africa",
}
