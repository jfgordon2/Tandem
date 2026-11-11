"""Publish the turn StarPilot actually selected without extending its message schema or state."""
from __future__ import annotations

import os
import time
from typing import Any, TYPE_CHECKING, TypedDict

from openpilot.starpilot.tandem.turn_status import EMPTY_TURN, Publisher, Subscriber

if TYPE_CHECKING:
  from cereal.messaging import SubMaster


class TurnReading(TypedDict):
  """The selected turn fields used by the drive screen."""

  active: bool
  maneuver: str
  modifier: str


_turn_publisher = Publisher()
_turn_subscriber = Subscriber()


def controller_type(base: type[Any]) -> type[Any]:
  """StarPilot's cruise controller, recording the turn it selected; with offline routing, only from a fresh instruction."""
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return base

  class TandemCruise(base):
    nav_turn_maneuver = ""
    nav_turn_modifier = ""

    def _selected_turn(self, maneuver: str | None, modifier: str | None) -> None:
      self.nav_turn_maneuver = str(maneuver or "").strip().lower()
      self.nav_turn_modifier = str(modifier or "").strip()

    def _get_nav_turn_control_target(self, v_cruise: float, sm: SubMaster, starpilot_toggles: Any) -> float:
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
      return float(super()._get_nav_turn_control_target(v_cruise, sm, starpilot_toggles, on_selected=self._selected_turn))

  return TandemCruise


def publish_turn(planner: Any, sm: SubMaster) -> None:
  """Publishes whether the selected turn currently sets the cruise target."""
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return
  cruise = planner.starpilot_vcruise
  active = bool(sm["carControl"].longActive and not cruise.forcing_stop
                and 0.0 < cruise.nav_turn_target == planner.v_cruise)
  turn = (True, cruise.nav_turn_maneuver, cruise.nav_turn_modifier) if active else EMPTY_TURN
  _turn_publisher.update(turn, time.monotonic())


def read_turn(now: float | None = None) -> TurnReading:
  """Returns the latest fresh turn for the drive screen."""
  turn = EMPTY_TURN if os.getenv("TANDEM_ONROAD", "1") == "0" else _turn_subscriber.read(time.monotonic() if now is None else now)
  active, maneuver, modifier = turn
  return {"active": active, "maneuver": maneuver, "modifier": modifier}
