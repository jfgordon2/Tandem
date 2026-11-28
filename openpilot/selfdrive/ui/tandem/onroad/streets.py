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


_INTERSTATE = re.compile(r"^I[\s-]*(\d+[A-Z]?)$", re.IGNORECASE)


def road_name(raw: str) -> str:
  """The road mapd names, as the bar shows it. mapd joins a road's several names or route numbers with ";" ("I 74;US 6"):
  each is shortened (Interstates read "I-74"), repeats are dropped, and they're joined with " / " ("I-74 / US 6")."""
  parts: list[str] = []
  for piece in str(raw).split(";"):
    piece = " ".join(piece.split())
    if not piece:
      continue
    interstate = _INTERSTATE.match(piece)
    piece = f"I-{interstate.group(1).upper()}" if interstate else short_street(piece)
    if piece not in parts:
      parts.append(piece)
  return " / ".join(parts)


_JOINS = re.compile(r"(\s+(?:onto|on|toward|towards|to|via|at|and)\s+|\s*[/,;]\s*)", re.IGNORECASE)


def short_streets_in(text: str) -> str:
  """Each street in a route instruction shortened ("Turn right onto North Main Street" reads "... onto N Main St"):
  the text is split at joining words and separators, and each piece is shortened on its own."""
  return "".join(part if i % 2 else short_street(part) for i, part in enumerate(_JOINS.split(text)))


class StreetName:
  """The street the bar shows, steady through mapd's gaps.

  StarPilot 7 runs mapd as a development shadow (starpilot/maps/SHADOW_LIFECYCLE.md) whose messages are often invalid
  and nameless for seconds at a time between short valid ones (a 2026-11-26 drive: 593 and 1172 of 1199 a minute), so
  showing only what it names now blinks. The last street stays until mapd names a different one for HOLD_S, or until
  the car has driven LOST_M without mapd naming any street. That is distance, not time: stopped at a light the street
  can't change, and at highway speed seconds cover a lot of road.
  Over a 14-minute drive, 500 m blinked 7 times where 15 s blinked 11 (most nameless stretches were 100 to 300 m). If
  mapd sends nothing at all for SILENT_S (stopped, not just invalid), the street goes.

  Args:
    hold_s: How long a different street must be named before it shows.
    lost_m: How far the car may drive without any street named before the bar shows none.
    silent_s: How long without any message from mapd before the bar shows none.
  """
  # StarPilot's own map holds a new name 1.5 s (NAME_HOLD_S, starpilot/ui/onroad_map.py). mapd sends 20 a second, so
  # 0.5 s is ten readings: enough to pass over a junction's other road, and a second sooner after each turn.
  HOLD_S, LOST_M, SILENT_S = 0.5, 500.0, 10.0

  def __init__(self, hold_s: float = HOLD_S, lost_m: float = LOST_M, silent_s: float = SILENT_S) -> None:
    self._hold, self._lost, self._silent = hold_s, lost_m, silent_s
    self._shown = self._candidate = ""
    self._since = self._heard = -1e9
    self._named_at_m = 0.0

  def update(self, name: str | None, now: float, odometer_m: float) -> str:
    """Takes mapd's latest reading, if a new one arrived, and returns the street to show.

    Args:
      name: The street mapd just named ("" for none or an invalid message), or None when nothing new arrived this frame.
      now: Monotonic seconds.
      odometer_m: How far the car has driven, in meters, from any fixed start (the view adds up its speed).
    """
    if name is not None:
      self._heard = now
    if name:
      self._named_at_m = odometer_m
      if name != self._candidate:
        self._candidate, self._since = name, now
      if name == self._shown or not self._shown or now - self._since >= self._hold:
        self._shown = name
    if odometer_m - self._named_at_m > self._lost or now - self._heard > self._silent:
      self._shown = self._candidate = ""
    return self._shown
