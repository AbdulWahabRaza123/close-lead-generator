"""
US state name normalization for CSV (full names) and Close API (often abbreviations).
"""

from __future__ import annotations

# Full name -> USPS abbreviation
STATE_TO_ABBREV: dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
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
    "district of columbia": "DC",
}

ABBREV_TO_STATE: dict[str, str] = {v: k.title() for k, v in STATE_TO_ABBREV.items()}
# Multi-word title case
ABBREV_TO_STATE["DC"] = "District of Columbia"
ABBREV_TO_STATE["NM"] = "New Mexico"
ABBREV_TO_STATE["NY"] = "New York"
ABBREV_TO_STATE["NH"] = "New Hampshire"
ABBREV_TO_STATE["NJ"] = "New Jersey"
ABBREV_TO_STATE["NC"] = "North Carolina"
ABBREV_TO_STATE["ND"] = "North Dakota"
ABBREV_TO_STATE["RI"] = "Rhode Island"
ABBREV_TO_STATE["SC"] = "South Carolina"
ABBREV_TO_STATE["SD"] = "South Dakota"
ABBREV_TO_STATE["WV"] = "West Virginia"


def to_abbrev(state: str) -> str:
    """Convert full state name to abbreviation for Close address field."""
    key = state.strip().lower()
    if len(key) == 2 and key.upper() in ABBREV_TO_STATE:
        return key.upper()
    return STATE_TO_ABBREV.get(key, state.strip())


def to_full_name(state: str) -> str:
    """Convert abbreviation or mixed input to full state name for reports."""
    s = state.strip()
    if len(s) == 2:
        return ABBREV_TO_STATE.get(s.upper(), s)
    key = s.lower()
    if key in STATE_TO_ABBREV:
        return ABBREV_TO_STATE[STATE_TO_ABBREV[key]]
    return s
