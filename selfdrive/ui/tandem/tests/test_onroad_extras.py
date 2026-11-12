from types import SimpleNamespace

import numpy as np

from openpilot.selfdrive.ui.tandem.onroad import extras as X


class _Params:
  def __init__(self, **values):
    self.values = values

  def get_bool(self, key):
    return bool(self.values.get(key, False))


def test_pedals_follow_starpilots_modes():
  car = SimpleNamespace(standstill=False, brakeLights=False, aEgo=-1.5)
  assert X.pedal_levels(_Params(), car) is None                                     # PedalsOnUI off
  assert X.pedal_levels(_Params(PedalsOnUI=True), None) is None
  assert X.pedal_levels(_Params(PedalsOnUI=True), car) == (1.0, 1.0)                # neither mode: both full
  assert X.pedal_levels(_Params(PedalsOnUI=True, StaticPedalsOnUI=True), car) == (1.0, 0.25)
  brake, gas = X.pedal_levels(_Params(PedalsOnUI=True, DynamicPedalsOnUI=True), SimpleNamespace(standstill=False, aEgo=0.6))
  assert brake == 0.25 and gas == 0.6


def test_stop_distance():
  assert X.stop_text(45, True) == "45 m" and X.stop_text(45, False) == "148 ft"


def test_path_end_is_the_far_corners_of_the_path_polygon():
  path = np.array([(0, 100), (10, 50), (20, 50), (30, 100)], dtype=np.float32)   # L0, L1, R1, R0
  left, right = X.path_end(path)
  assert (left.x, left.y, right.x, right.y) == (10, 50, 20, 50)
  assert X.path_end(np.zeros((2, 2))) is None


def test_border_halves_hold_red_for_a_blind_spot_and_blink_blue_for_a_signal():
  red, blue = X.BLIND_SPOT_BORDER, X.SIGNAL_BORDER
  assert X.border_halves(True, True, True, False, False, True, now=0.1) == (blue, red)
  assert X.border_halves(True, True, True, False, False, True, now=0.6) == (None, red)   # the signal's off half
  assert X.border_halves(False, True, True, False, False, False, now=0.1) == (None, None)  # SignalMetrics off


def test_every_model_state_has_a_chip():
  assert set(X.MODEL_LABELS) == {"loading", "active", "failed", "fallback_engaged"}
