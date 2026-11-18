"""The driving bar's arrival time and what's left, from StarPilot 7's navigation display (onroad/state.py)."""
from __future__ import annotations

import datetime

from openpilot.starpilot.ui.navigation_state import NavigationDisplay
from openpilot.selfdrive.ui.tandem.onroad.state import route_progress, turn

NOW = datetime.datetime(2026, 11, 18, 16, 40)


def guiding(seconds: float, meters: float) -> NavigationDisplay:
  return NavigationDisplay(("session", 1), "Turn left onto SE Belmont St", "turn", "left", 120.0, meters, seconds)


def test_arrival_and_whats_left_in_miles_and_kilometers() -> None:
  assert route_progress(guiding(720, 13_518.0), False, NOW) == ("4:52 PM", "12 min · 8.4 mi")
  assert route_progress(guiding(720, 13_518.0), True, NOW) == ("4:52 PM", "12 min · 13.5 km")


def test_the_last_minute_still_reads_one_and_no_route_is_blank() -> None:
  assert route_progress(guiding(10, 50.0), False, NOW)[1] == "1 min · 0.0 mi"
  assert route_progress(None, False, NOW) == ("", "")


def test_the_turn_card_reads_starpilots_next_turn() -> None:
  assert turn(guiding(720, 13_518.0), False) == ("400 ft", "Turn left onto SE Belmont St", "turn", "left")
  assert turn(guiding(720, 13_518.0), True) == ("125 m", "Turn left onto SE Belmont St", "turn", "left")
  arrived = NavigationDisplay(("session", 1), "You have arrived", "arrive", "", 0.0, 0.0, 0.0, arrived=True)
  assert turn(arrived, False) == ("", "You have arrived", "arrive", "") and turn(None, False) is None
