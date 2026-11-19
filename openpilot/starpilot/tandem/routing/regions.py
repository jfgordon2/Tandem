"""The US states Tandem's routing data covers, named as release's catalog names them ("us_state.IA").

StarPilot 6 kept these in starpilot/common/maps_selection.py and maps_catalog.py; StarPilot 7's road maps use mapd's own
region catalog instead, so Tandem keeps the list it publishes routing data for.
"""
from __future__ import annotations

STATE_PREFIX = "us_state."
NATION_US = "nation.US"

STATE_GROUPS = (
  ("Midwest", {"IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "MI": "Michigan", "MN": "Minnesota", "MO": "Missouri",
               "NE": "Nebraska", "ND": "North Dakota", "OH": "Ohio", "SD": "South Dakota", "WI": "Wisconsin"}),
  ("Northeast", {"CT": "Connecticut", "ME": "Maine", "MA": "Massachusetts", "NH": "New Hampshire", "NJ": "New Jersey",
                 "NY": "New York", "PA": "Pennsylvania", "RI": "Rhode Island", "VT": "Vermont"}),
  ("South", {"AL": "Alabama", "AR": "Arkansas", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
             "KY": "Kentucky", "LA": "Louisiana", "MD": "Maryland", "MS": "Mississippi", "NC": "North Carolina", "OK": "Oklahoma",
             "SC": "South Carolina", "TN": "Tennessee", "TX": "Texas", "VA": "Virginia", "WV": "West Virginia"}),
  ("West", {"AK": "Alaska", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "HI": "Hawaii", "ID": "Idaho", "MT": "Montana",
            "NV": "Nevada", "NM": "New Mexico", "OR": "Oregon", "UT": "Utah", "WA": "Washington", "WY": "Wyoming"}),
  ("Territories", {"AS": "American Samoa", "GU": "Guam", "MP": "Northern Mariana Islands", "PR": "Puerto Rico",
                   "VI": "Virgin Islands"}),
)
STATES = {code: name for _, group in STATE_GROUPS for code, name in group.items()}
STATE_TOKENS = frozenset(STATE_PREFIX + code for code in STATES)


def tokens(selection: str) -> set[str]:
  """The state tokens in a comma-separated selection; "nation.US" stands for every state. Anything else is dropped."""
  result: set[str] = set()
  for token in (t.strip() for t in selection.split(",")):
    if token == NATION_US:
      result |= STATE_TOKENS
    elif token in STATE_TOKENS:
      result.add(token)
  return result


def name(token: str) -> str:
  """A state's name from its token ("us_state.IA" → "Iowa"), or the token itself when it isn't a state."""
  return STATES.get(token.removeprefix(STATE_PREFIX), token)
