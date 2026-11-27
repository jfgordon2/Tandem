"""Street names as the bar shows them: directions and street types shortened the way signs and the USPS write them.

"North Main Street" is "N Main St", "Martin Luther King Junior Boulevard Northwest" is "Martin Luther King Junior Blvd NW".
A direction that is the name itself stays whole ("North Ave"), and a type that isn't last does too ("Avenue of the Americas").
"""
from __future__ import annotations

import re
from openpilot.selfdrive.ui.tandem.i18n import N_

DIRECTIONS = {"north": "N", "south": "S", "east": "E", "west": "W", "northeast": "NE", "northwest": "NW", "southeast": "SE",
              "southwest": "SW"}
TYPES = {
  "street": N_("St"), "avenue": N_("Ave"), "road": N_("Rd"), "boulevard": N_("Blvd"), "drive": N_("Dr"), "lane": N_("Ln"), "court": N_("Ct"), "place": N_("Pl"),
  "terrace": N_("Ter"), "parkway": N_("Pkwy"), "highway": N_("Hwy"), "expressway": N_("Expy"), "freeway": N_("Fwy"), "circle": N_("Cir"), "trail": N_("Trl"),
  "square": N_("Sq"), "crossing": N_("Xing"), "turnpike": N_("Tpke"), "heights": N_("Hts"), "center": N_("Ctr"), "plaza": N_("Plz"), "point": N_("Pt"),
  "mountain": N_("Mtn"), "junction": N_("Jct"), "crescent": N_("Cres"), "alley": N_("Aly"), "causeway": N_("Cswy"), "bypass": N_("Byp"),
}
TYPE_WORDS = set(TYPES) | {short.lower() for short in TYPES.values()} | {"way"}   # a type spelled out or already short


def short_street(name: str) -> str:
  """A street name shortened as signs write it: "North Main Street" reads "N Main St". Single words stay."""
  words = name.split()
  if len(words) < 2:
    return name
  start, end = 0, len(words)
  # A trailing direction ("... Street Northwest"), when something other than a type comes before it.
  if DIRECTIONS.get(words[-1].lower()) and len(words) >= 3:
    words[-1], end = DIRECTIONS[words[-1].lower()], end - 1
  # A leading direction, when at least a name and maybe a type follow ("North Main Street", not "North Avenue").
  rest = words[1:end]
  if DIRECTIONS.get(words[0].lower()) and any(w.lower().rstrip(".") not in TYPE_WORDS for w in rest):
    words[0], start = DIRECTIONS[words[0].lower()], 1
  # The street type: the last word before any trailing direction, after a name.
  last = end - 1
  if last > start and words[last].lower() in TYPES:
    words[last] = TYPES[words[last].lower()]
  return " ".join(words)


_JOINS = re.compile(r"(\s+(?:onto|on|toward|towards|to|via|at|and)\s+|\s*[/,;]\s*)", re.IGNORECASE)


def short_streets_in(text: str) -> str:
  """Each street in a route instruction shortened ("Turn right onto North Main Street" reads "... onto N Main St"):
  the text is split at joining words and separators, and each piece is shortened on its own."""
  return "".join(part if i % 2 else short_street(part) for i, part in enumerate(_JOINS.split(text)))


class StreetName:
  """The street the bar shows, steady through mapd's gaps.

  StarPilot 7 runs mapd as a development shadow (starpilot/maps/SHADOW_LIFECYCLE.md) whose messages are often invalid
  and nameless for seconds at a time between short valid ones (a 2026-11-26 drive: 593 and 1172 of 1199 a minute), so
  showing only what it names now blinks. The last street stays until mapd names a different one for HOLD_S, as
  StarPilot's own map waits before a new name, or names nothing for LOST_S.

  Args:
    hold_s: How long a different street must be named before it shows.
    lost_s: How long without any street named before the bar shows none.
  """
  HOLD_S, LOST_S = 1.5, 15.0   # StarPilot's NAME_HOLD_S (starpilot/ui/onroad_map.py); about a block at city speed

  def __init__(self, hold_s: float = HOLD_S, lost_s: float = LOST_S) -> None:
    self._hold, self._lost = hold_s, lost_s
    self._shown = self._candidate = ""
    self._since = self._named = -1e9

  def update(self, name: str | None, now: float) -> str:
    """Takes mapd's latest reading, if a new one arrived, and returns the street to show.

    Args:
      name: The street mapd just named ("" for none or an invalid message), or None when nothing new arrived this frame.
      now: Monotonic seconds.
    """
    if name:
      self._named = now
      if name != self._candidate:
        self._candidate, self._since = name, now
      if name == self._shown or not self._shown or now - self._since >= self._hold:
        self._shown = name
    if now - self._named > self._lost:
      self._shown = self._candidate = ""
    return self._shown
