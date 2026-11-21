"""The driving screen's stop, traffic, held-steering and Matching limit chips on StarPilot 7 (onroad/binding.py), read
from StarPilot's own conditional mode, Pause steering rule and accepted speed limit as view.py passes them in."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from openpilot.selfdrive.ui.tandem.onroad.binding import matching_limit, steering_held, stop_chips, stop_sign_seen
from openpilot.selfdrive.ui.tandem.onroad.status import LimitWatch, Snapshot, chips_for
from openpilot.starpilot.conditional_mode.policy import Reason
from openpilot.starpilot.lateral.pause import LateralPause, PauseSettings
from openpilot.starpilot.speed_limits.vision.stop_observation import STOP_MAX_AGE_NS

ROOT = Path(__file__).resolve().parents[5]
S = 1_000_000_000


def labels(snapshot: Snapshot) -> list[str]:
  return [chip.label for chip in chips_for(snapshot)]


def test_a_stop_conditional_mode_accepted_shows_stopping_then_stopped() -> None:
  stopping, sign, traffic = stop_chips(True, False, "cem_stop", True)
  assert (stopping, sign, traffic) == (True, False, False)
  assert "Stopping ahead" in labels(Snapshot(engaged=True, speed=12.0, red_light=stopping))
  assert "Stopped" in labels(Snapshot(engaged=True, standstill=True, red_light=stopping))
  assert stop_chips(False, True, "cem_stop", True) == (False, False, False)   # a sighting alone isn't a stop


def test_a_stop_sign_needs_a_stop_and_a_fresh_sighting() -> None:
  assert stop_sign_seen(10 * S, 10 * S + STOP_MAX_AGE_NS - 1, dashboard=False)
  assert not stop_sign_seen(10 * S, 10 * S + STOP_MAX_AGE_NS, dashboard=False)   # gone when StarPilot's STOP sign goes
  assert not stop_sign_seen(0, 10 * S, dashboard=False)
  assert stop_sign_seen(0, 10 * S, dashboard=True)
  _, sign, _ = stop_chips(True, True, "cem_stop", True)
  assert sign and "Stopping for stop sign" in labels(Snapshot(engaged=True, speed=8.0, red_light=True, stop_sign=sign))


def test_slowing_for_traffic_is_conditional_modes_lead_reason() -> None:
  assert Reason.CEM_LEAD.value == "cem_lead"
  _, _, traffic = stop_chips(False, False, "cem_lead", True)
  assert traffic and "Slowing for traffic" in labels(Snapshot(engaged=True, speed=20.0, accel=-1.0, slowing_for_lead=traffic))
  assert stop_chips(False, False, "cem_lead", False)[2] is False   # the driver has the speed
  assert stop_chips(False, False, "cem_curve", True)[2] is False


def car(speed: float, signal: bool = False) -> SimpleNamespace:
  return SimpleNamespace(canValid=True, canTimeout=False, vEgo=speed, leftBlinker=signal, rightBlinker=False)


def test_steering_held_follows_starpilots_pause_rule_while_steering_is_off() -> None:
  pause = LateralPause(PauseSettings(speed_mps=10.0))
  slow = pause.allowed(car(5.0), now_ns=2 * S, source_ns=2 * S, drive_id=7)
  assert steering_held(slow, wants_steering=True, lateral_active=False, standstill=False)
  assert not steering_held(slow, wants_steering=True, lateral_active=True, standstill=False)   # it's steering after all
  assert not steering_held(slow, wants_steering=False, lateral_active=False, standstill=False)
  assert not steering_held(slow, wants_steering=True, lateral_active=False, standstill=True)
  fast = pause.allowed(car(15.0), now_ns=3 * S, source_ns=3 * S, drive_id=7)
  assert not steering_held(fast, wants_steering=True, lateral_active=False, standstill=False)
  shown = Snapshot(engaged=True, speed=5.0, steering_held=True, pause_lateral_ms=10.0, pause_lateral_speed=22.0)
  assert "Steering paused · under 22 mph" in labels(shown)


def test_signal_only_pause_names_the_signal() -> None:
  pause = LateralPause(PauseSettings(speed_mps=10.0, signal_only=True))
  held = not pause.allowed(car(5.0, signal=True), now_ns=2 * S, source_ns=2 * S, drive_id=7)
  assert held
  shown = Snapshot(engaged=True, speed=5.0, steering_held=held, pause_on_signal=True, signal_on=True, signal_direction="left")
  assert "Steering paused for signal" in labels(shown)


def limit(accepted: float | None, adjusted: float | None = None, limiting: bool = True, pending: float | None = None,
          override: bool = False) -> SimpleNamespace:
  return SimpleNamespace(accepted_speed_limit_mps=accepted, accepted_adjusted_limit_mps=adjusted, effective_cap_mps=None,
                         pending_speed_limit_mps=pending, automatic_adoption_pending=False, limiting_max_set=limiting,
                         driver_override_active=override)


def test_matching_limit_shows_after_a_new_accepted_limit_until_the_car_reaches_it() -> None:
  watch = LimitWatch()
  assert not matching_limit(watch, limit(29.0, 30.0), 30.0, True, 0.0)   # the first limit isn't a change
  assert matching_limit(watch, limit(20.0, 21.0), 30.0, True, 1.0)
  assert not matching_limit(watch, limit(20.0, 21.0, pending=25.0), 28.0, True, 2.0)   # still asking the driver
  assert not matching_limit(watch, limit(20.0, 21.0), 28.0, False, 2.5)   # the driver has the speed
  assert not matching_limit(watch, limit(20.0, 21.0, override=True), 28.0, True, 3.0)
  assert not matching_limit(watch, limit(20.0, 21.0), 21.2, True, 4.0)   # reached
  assert not matching_limit(watch, limit(20.0, 21.0), 28.0, True, 5.0)


def _fields(path: str, name: str) -> set[str]:
  tree = ast.parse((ROOT / path).read_text())
  cls = next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == name)
  return {node.target.id for node in cls.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}


def test_the_starpilot_fields_view_py_reads_still_exist() -> None:
  """view.py reads these on the device, where the off-device stand-ins above can't notice a rename."""
  onroad = _fields("openpilot/starpilot/ui/onroad_state.py", "OnroadState")
  assert {"stop_sign_observed_ns", "longitudinal_active", "lateral_active", "aol_latched", "engaged", "speed_limit",
          "metric", "observed_ns"} <= onroad
  assert set(vars(limit(None))) <= _fields("openpilot/starpilot/ui/onroad_state.py", "SpeedLimitObservation")
  assert "dashboardStopSign @" in (ROOT / "openpilot/cereal/custom.capnp").read_text()
  conditional = (ROOT / "openpilot/starpilot/ui/onroad_conditional.py").read_text()
  assert "def stop_active(state" in conditional and "def reason(state" in conditional
