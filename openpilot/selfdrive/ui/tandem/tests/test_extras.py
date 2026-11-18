"""StarPilot's pedal and border highlights on Tandem's driving screen (onroad/extras.py), on real StarPilot 7 messages."""
from __future__ import annotations

from openpilot.cereal import log
from openpilot.selfdrive.ui.tandem.onroad import extras
from openpilot.starpilot.ui.wheel_feedback import observe_wheel_acceleration


def car(**values: object) -> object:
  state = log.Event.new_message().init("carState")
  state.canValid = True
  for key, value in values.items():
    setattr(state, key, value)
  return state


def test_pedals_follow_starpilots_wheel_feedback() -> None:
  pedals = extras.Pedals()
  assert pedals.update(observe_wheel_acceleration(car(aEgo=-1.0)), False, 1, 1) is None    # StarPilot's setting off
  levels = None
  for frame in range(1, 40):   # StarPilot's fade settles over a few frames
    levels = pedals.update(observe_wheel_acceleration(car(aEgo=-2.0)), True, frame * 50_000_000, 1)
  assert levels is not None and levels[0] > 0.95 and levels[1] == extras.IDLE
  for frame in range(40, 80):
    levels = pedals.update(observe_wheel_acceleration(car(aEgo=0.0)), True, frame * 50_000_000, 1)
  assert levels is not None and max(levels) < extras.IDLE + 0.05


def test_border_reads_the_cars_blinkers_and_blind_spots() -> None:
  state = car(leftBlinker=True, rightBlindspot=True)
  on = extras.border_halves(True, True, state.leftBlinker, state.rightBlinker, state.leftBlindspot, state.rightBlindspot, now=0.1)
  assert on == (extras.SIGNAL_BORDER, extras.BLIND_SPOT_BORDER)
  off = extras.border_halves(True, True, state.leftBlinker, state.rightBlinker, state.leftBlindspot, state.rightBlindspot, now=0.6)
  assert off == (None, extras.BLIND_SPOT_BORDER)   # the signal blinks; the blind spot holds
  assert extras.border_halves(False, False, True, False, False, True, now=0.1) == (None, None)
