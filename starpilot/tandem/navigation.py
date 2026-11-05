"""Publish the turn StarPilot actually selected without extending its message schema or state."""
from __future__ import annotations

import os
import time

from openpilot.starpilot.tandem.state import NAV_TURN

EMPTY_TURN = {"active": False, "maneuver": "", "modifier": ""}


def controller_type(base):
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return base

  class TandemCruise(base):
    nav_turn_maneuver = ""
    nav_turn_modifier = ""

    def _selected_turn(self, maneuver, modifier):
      self.nav_turn_maneuver = str(maneuver or "").strip().lower()
      self.nav_turn_modifier = str(modifier or "").strip()

    def _get_nav_turn_control_target(self, v_cruise, sm, starpilot_toggles):
      self.nav_turn_maneuver = self.nav_turn_modifier = ""
      from openpilot.starpilot.tandem.routing.config import enabled
      if enabled():
        self._update_nav_instruction_state()
        stamp = self._nav_instruction_state.get("updatedAtMonotonic")
        try:
          if not 0 <= time.monotonic() - float(stamp) <= 2.5:
            return 0.0
        except (TypeError, ValueError, OverflowError):
          return 0.0
      return super()._get_nav_turn_control_target(v_cruise, sm, starpilot_toggles, on_selected=self._selected_turn)

  return TandemCruise


def publish_turn(planner, sm) -> None:
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return
  cruise = planner.starpilot_vcruise
  active = bool(sm["carControl"].longActive and not cruise.forcing_stop
                and 0.0 < cruise.nav_turn_target == planner.v_cruise)
  NAV_TURN.write({"active": active, "maneuver": cruise.nav_turn_maneuver if active else "",
                  "modifier": cruise.nav_turn_modifier if active else ""})


def read_turn(now: float | None = None) -> dict:
  value = NAV_TURN.read(max_age=1.0, now=time.monotonic() if now is None else now)
  if (isinstance(value, dict) and type(value.get("active")) is bool
      and all(isinstance(value.get(key), str) for key in ("maneuver", "modifier"))):
    return value
  return EMPTY_TURN.copy()
