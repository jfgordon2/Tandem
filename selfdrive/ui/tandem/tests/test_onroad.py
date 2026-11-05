from types import SimpleNamespace

import pytest
from cereal import car, custom, log
from openpilot.starpilot.tandem.state import NAV_TURN

from openpilot.selfdrive.ui.tandem.onroad.layers import AT_LIMIT, COMFORTABLE, LIMIT_HOLD, WORKING, Headroom
from openpilot.selfdrive.ui.tandem.onroad.status import ChipPicker, ChipTone, Snapshot, chip_for, snapshot, weather_name


class StatusMessages(dict):
  @property
  def valid(self):
    return dict.fromkeys(self, True)


def test_chip_priority_paused_then_stopping_then_slowing_then_waiting():
  s = Snapshot(lateral_paused=True, red_light=True, curve_control=True, engaged=True, standstill=True, waiting_for_resume=True)
  assert chip_for(s).key == "pause_button" and chip_for(s).tone == ChipTone.PAUSED
  s.lateral_paused = False
  assert chip_for(s).key == "red_light"
  s.red_light = False
  assert chip_for(s).label == "Slowing for curve"
  s.curve_control = False
  assert chip_for(s).key == "ready" and chip_for(s).tone == ChipTone.WAITING
  s.engaged = False
  assert chip_for(s) is None


def test_chip_labels_use_units_and_direction():
  slow = dict(steering_held=True, speed=5.0, pause_lateral_ms=8.33, pause_lateral_speed=30, metric=True)
  assert chip_for(Snapshot(**slow)).label == "Steering paused · under 30 km/h"
  assert chip_for(Snapshot(**slow, signal_on=True, pause_on_signal=True)).label == "Steering paused for signal"
  assert chip_for(Snapshot(lane_change="starting", lane_change_direction="right")).label == "Changing lanes right"
  assert chip_for(Snapshot(lane_change="pre", blindspot=True)).label == "Lane change blocked"
  assert chip_for(Snapshot(limit_changed=True, speed_limit=45)).label == "Matching limit 45"
  assert chip_for(Snapshot(events={"greenLight"})).label == "Light is green"
  assert chip_for(Snapshot(always_on_lateral=True)).label == "Steering only"


def test_chip_holds_two_seconds_and_hides_under_alerts():
  picker = ChipPicker()
  assert picker.update(Snapshot(curve_control=True), 0.0, False).key == "curve"
  assert picker.update(Snapshot(), 1.5, False).key == "curve"
  assert picker.update(Snapshot(), 2.1, False) is None
  assert picker.update(Snapshot(curve_control=True), 3.0, True) is None


@pytest.mark.parametrize("lane_state, expected", [("off", "off"), ("preLaneChange", "pre"),
                                                 ("laneChangeStarting", "starting"), ("laneChangeFinishing", "finishing")])
@pytest.mark.parametrize("direction", ["none", "left", "right"])
def test_snapshot_accepts_live_model_lane_change_enums(lane_state, expected, direction):
  model = log.ModelDataV2.new_message()
  model.meta.laneChangeState = lane_state
  model.meta.laneChangeDirection = direction
  # Live UI messages are readers after decoding, not integer-valued test doubles.
  with log.ModelDataV2.from_bytes(model.to_bytes()) as received:
    state = SimpleNamespace(sm=StatusMessages(modelV2=received), engaged=True, is_metric=False,
                            always_on_lateral_active=False, starpilot_toggles={})
    current = snapshot(state)
    assert (current.lane_change, current.lane_change_direction) == (expected, direction)


@pytest.mark.parametrize("direction", ["left", "right"])
@pytest.mark.parametrize("hide_turn_banner", [False, True])
def test_turn_chip_follows_actual_slowdown_then_turn(direction, hide_turn_banner):
  cs = car.CarState.new_message(vEgo=12.0, aEgo=0.0)
  plan = custom.StarPilotPlan.new_message(lateralCheck=True, experimentalMode=True, vCruise=8.0)
  state = SimpleNamespace(sm=StatusMessages(carState=cs, starpilotPlan=plan), engaged=True, is_metric=False,
                          always_on_lateral_active=False, starpilot_toggles={"hide_turning_banner": hide_turn_banner})
  picker = ChipPicker()

  # Navigating in experimental mode alone is not a turn slowdown.
  assert picker.update(snapshot(state, nav_active=True), 0.0, False) is None
  cs.aEgo = -0.5
  assert picker.update(snapshot(state, nav_active=True), 0.1, False) is None
  NAV_TURN.write({"active": True, "maneuver": "turn", "modifier": direction}, now=0.0)
  slowing = picker.update(snapshot(state, nav_active=True), 0.2, False)
  assert (slowing.label, slowing.icon) == ("Slowing for turn", f"turn_{direction}")

  # The model can request a turn during the approach: keep describing the slowdown first.
  plan.starpilotEvents = [{"name": f"turning{direction.title()}"}]
  assert picker.update(snapshot(state, nav_active=True), 0.3, False).label == "Slowing for turn"
  cs.aEgo = 0.0
  chip = picker.update(snapshot(state, nav_active=True), 0.4, False)
  assert (chip.label, chip.icon, chip.tone) == (f"Turning {direction}", f"turn_{direction}", ChipTone.INFO)
  assert picker.update(snapshot(state, nav_active=True), 0.5, True) is None

  # Clear after the normal hold when the maneuver has ended.
  plan.starpilotEvents = []
  NAV_TURN.write({"active": False, "maneuver": "", "modifier": ""}, now=0.0)
  assert picker.update(snapshot(state, nav_active=True), 2.6, False) is None

  # Braking for something else below the turn's target is not a turn slowdown.
  NAV_TURN.write({"active": True, "maneuver": "turn", "modifier": direction}, now=0.0)
  cs.vEgo, cs.aEgo = 6.0, -0.5
  assert not snapshot(state, nav_active=True).nav_turn


@pytest.mark.parametrize("direction", ["left", "right"])
@pytest.mark.parametrize("pedal, acceleration", [("gas", 0.5), ("brake", -0.5)])
@pytest.mark.parametrize("nav_active", [False, True])
def test_turn_chip_without_slowdown_when_driver_operates_pedals(direction, pedal, acceleration, nav_active):
  cs = car.CarState.new_message(vEgo=8.0, aEgo=acceleration, gasPressed=pedal == "gas", brakePressed=pedal == "brake")
  control = car.CarControl.new_message(enabled=False, latActive=True, longActive=False)
  plan = custom.StarPilotPlan.new_message(experimentalMode=False)
  state = SimpleNamespace(sm=StatusMessages(carState=cs, carControl=control, starpilotPlan=plan), engaged=False,
                          is_metric=False, always_on_lateral_active=True, starpilot_toggles={"hide_turning_banner": True})
  picker = ChipPicker()
  assert picker.update(snapshot(state, nav_active=nav_active), 0.0, False).key == "steering_only"

  # Go directly from steering-only to turning, without ever reporting a turn slowdown.
  plan.starpilotEvents = [{"name": f"turning{direction.title()}"}]
  current = snapshot(state, nav_active=nav_active)
  assert not current.nav_turn
  chip = picker.update(current, 0.1, False)
  assert (chip.label, chip.icon) == (f"Turning {direction}", f"turn_{direction}")


@pytest.mark.parametrize("higher_status, expected", [
  ({"lateral_paused": True}, "pause_button"),
  ({"lane_change": "pre", "blindspot": True}, "lane_blocked"),
  ({"lane_change": "starting", "lane_change_direction": "right"}, "lane_change"),
  ({"stop_sign": True}, "stop_sign"),
  ({"red_light": True}, "red_light"),
  ({"curve_control": True}, "curve"),
])
def test_turn_progress_keeps_existing_chip_priorities(higher_status, expected):
  assert chip_for(Snapshot(events={"turningLeft"}, **higher_status)).key == expected


@pytest.mark.parametrize("service, message", [("selfdriveState", log.SelfdriveState),
                                            ("starpilotSelfdriveState", custom.StarPilotSelfdriveState)])
def test_hidden_turn_banner_does_not_make_empty_alerts_into_persistent_turn_chips(service, message, monkeypatch):
  import copy
  from openpilot.selfdrive.selfdrived import alertmanager, events

  # Reproduce StarPilot's shared EmptyAlert mutation without leaking it to other tests.
  empty = copy.copy(events.EmptyAlert)
  monkeypatch.setattr(events, "EmptyAlert", empty)
  monkeypatch.setattr(alertmanager, "EmptyAlert", empty)
  turn_events = events.Events(starpilot=True)
  turn_events.add(custom.StarPilotOnroadEvent.EventName.turningLeft)
  hidden = turn_events.create_alerts([events.ET.WARNING],
    [None, None, None, False, 0, None, SimpleNamespace(hide_turning_banner=True)])
  assert hidden[0] is empty and empty.alert_type == "turningLeft/warning"
  manager = alertmanager.AlertManager()
  manager.process_alerts(1000, set())  # no active alert, but EmptyAlert still carries the old type
  alert = manager.current_alert
  outgoing = message.new_message(alertType=alert.alert_type, alertSize=alert.alert_size)
  with message.from_bytes(outgoing.to_bytes()) as received:
    state = SimpleNamespace(sm=StatusMessages({service: received}), engaged=False, is_metric=False,
                            always_on_lateral_active=False, starpilot_toggles={})
    assert str(received.alertSize) == "none" and received.alertType == "turningLeft/warning"
    assert not snapshot(state).events


def test_weather_groups():
  assert [weather_name(i) for i in (211, 501, 502, 601, 741, 800)] == ["Heavy rain", "Rain", "Rain", "Snow", "Fog", ""]


@pytest.mark.parametrize("weather_id, expected", [(211, "rain"), (501, "rain"), (502, "rain"), (601, "snow"), (741, "fog")])
def test_weather_chip_icon_matches_condition(weather_id, expected):
  from openpilot.selfdrive.ui.tandem import draw
  chip = chip_for(Snapshot(weather=weather_name(weather_id), weather_gap=True))
  assert chip.icon == expected
  assert (draw.ICON_DIR / f"{chip.icon}.png").is_file()


@pytest.mark.parametrize("left, right, expected", [
  (True, False, "signal"), (False, True, "signal_right"), (True, True, "warning"), (False, False, "wheel_pause"),   # no signal: the after-turn hold
])
def test_paused_chip_icon_matches_signals(left, right, expected):
  from openpilot.selfdrive.ui.tandem import draw
  cs = car.CarState.new_message(leftBlinker=left, rightBlinker=right, vEgo=3.0)
  plan = custom.StarPilotPlan.new_message(lateralCheck=False)   # StarPilot's planner holding steering
  state = SimpleNamespace(sm=StatusMessages(carState=cs, starpilotPlan=plan), engaged=True, is_metric=False, always_on_lateral_active=False,
                          starpilot_toggles={"pause_lateral_below_speed": 8.94, "pause_lateral_below_signal": True})
  chip = chip_for(snapshot(state))
  assert chip.icon == expected
  assert (draw.ICON_DIR / f"{draw.MIRRORED.get(chip.icon, chip.icon)}.png").is_file()
  assert draw.MIRRORED["signal_right"] == "signal"


def test_headroom_stages_need_a_held_limit():
  h = Headroom()
  assert h.stage(0.3, 0.0) == COMFORTABLE
  assert h.stage(-0.7, 0.1) == WORKING
  assert h.stage(0.9, 0.2) == WORKING
  assert h.stage(0.9, 0.2 + LIMIT_HOLD + 0.01) == AT_LIMIT
  assert h.stage(0.5, 1.0) == COMFORTABLE
  assert h.stage(0.9, 1.1) == WORKING


# ── Home and first-run setup ──

def test_home_readiness_and_setup_line():
  from openpilot.selfdrive.ui.tandem.home import HomeState, readiness, setup_line
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  assert readiness(HomeState(ignition=True))[:2] == ("READY", "Press cruise to engage")
  assert readiness(HomeState())[1] == "Start the car to drive"
  assert readiness(HomeState(alerts=1))[:2] == ("NEEDS ATTENTION", "Check 1 alert")
  speed = SpeedSteering(SettingsStore(FakeCache({"SpeedLimitController": True, "NudgelessLaneChange": True}), lambda: None))
  assert setup_line(speed) == "Standard style · Matching speed limits · Auto lane change"


def test_setup_answers_apply_over_the_defaults():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.setup import Setup
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  cache = FakeCache()
  notified, done = [], []
  store = SettingsStore(cache, lambda: notified.append(1))
  setup = Setup(store, lambda: done.append(1))
  setup.pick(0)          # Relaxed
  setup.next()
  setup.pick(1)          # Show
  setup.back()
  assert setup.step == 0 and setup.answers[:2] == [0, 1]
  setup.next()
  setup.next()
  setup.pick(0)          # Nudge
  setup.next()
  speed = SpeedSteering(store)
  assert done == [1] and notified == [1]
  assert (speed.style, speed.speed_limits, speed.lane_changes) == (0, 1, 0)
  assert cache.values["WeatherPresets"]     # defaults the questions don't cover still applied
  assert not any(cache.values[k] for k in ("NNFF", "NNFFLite", "ForceTorqueController"))


def test_setup_use_defaults():
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.setup import Setup
  from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache
  cache = FakeCache({"LongitudinalPersonality": 0, "NNFF": True, "NNFFLite": True, "ForceTorqueController": True})
  store = SettingsStore(cache, lambda: None)
  Setup(store, lambda: None).finish(use_answers=False)
  speed = SpeedSteering(store)
  assert (speed.style, speed.matching, speed.lane_changes) == (1, True, 0)
  assert not any(cache.values[k] for k in ("NNFF", "NNFFLite", "ForceTorqueController"))


def test_sidebar_network_status():
  from openpilot.selfdrive.ui.tandem.sidebar import Health, network_status
  assert (network_status("--", 0).value, network_status("--", 0).health) == ("Offline", Health.OFF)
  assert network_status("Wi-Fi", 4).health == Health.GOOD
  assert network_status("LTE", 1).health == Health.WARN
  from openpilot.selfdrive.ui.tandem.sidebar import connect_status
  assert [connect_status(h).value for h in (Health.GOOD, Health.WARN, Health.BAD)] == ["Online", "Offline", "Error"]


def test_every_icon_named_has_a_png():
  import re
  from pathlib import Path
  from openpilot.selfdrive.ui.tandem import draw
  root = Path(draw.__file__).parent
  pngs = {p.stem for p in draw.ICON_DIR.glob("*.png")}
  assert pngs == {p.stem for p in (draw.ICON_DIR / "svg").glob("*.svg")}
  source = "\n".join(p.read_text() for p in root.rglob("*.py") if "tests" not in p.parts)
  named = set(re.findall(r'draw\.icon\([^,]+, "(\w+)"', source)) | set(re.findall(r'icon="(\w+)"', source))
  named |= set(re.findall(r'ChipTone\.\w+, "(\w+)"', source)) | {"lane_left", "lane_right"}
  assert named and {draw.MIRRORED.get(n, n) for n in named} <= pngs


def test_turn_card_and_chip_icons_by_maneuver():
  from openpilot.selfdrive.ui.tandem import draw
  from openpilot.selfdrive.ui.tandem.onroad.layers import turn_icon
  cases = {("turn", "right"): "turn_right", ("turn", "slightLeft"): "turn_left", ("turn", "straight"): "shift",
           ("arrive", "straight"): "pin", ("roundabout", "right"): "restart", ("turn", "uturn"): "restart", ("", ""): "map"}
  assert {key: turn_icon(*key) for key in cases} == cases
  assert {key: chip_for(Snapshot(nav_turn=True, nav_turn_maneuver=key[0], nav_turn_modifier=key[1])).icon for key in cases} == cases
  pngs = {p.stem for p in draw.ICON_DIR.glob("*.png")}
  assert {draw.MIRRORED.get(name, name) for name in cases.values()} <= pngs


def test_home_software_card_shows_only_the_version_number():
  from openpilot.selfdrive.ui.tandem.home import short_version
  assert short_version("6.7.9 / design/essentials / 4b3a097 / Oct 31 - Regret Driven") == "6.7.9"
  assert short_version(b"0.10.1 / release / Oct 28") == "0.10.1"
  assert short_version(None) == ""


def test_weather_chip_only_when_its_preset_adds_distance():
  plan = custom.StarPilotPlan.new_message(lateralCheck=True, weatherId=501)
  def chip(toggles):
    state = SimpleNamespace(sm=StatusMessages(starpilotPlan=plan), engaged=True, is_metric=False, always_on_lateral_active=False,
                            starpilot_toggles=toggles)
    return chip_for(snapshot(state))
  assert chip({"weather_presets": True, "increase_following_distance_rain": 0.5}).label == "Rain · longer gap"
  assert chip({"weather_presets": True, "increase_following_distance_rain": 0}) is None   # rain, but its preset keeps the gap
  assert chip({"weather_presets": False, "increase_following_distance_rain": 0.5}) is None


@pytest.mark.parametrize("lateral_check,expected", [(True, "turn"), (False, "pause_held")])
def test_live_planner_steering_gate_keeps_priority_over_turn_and_weather(lateral_check, expected):
  cs = car.CarState.new_message(vEgo=12.0, aEgo=-0.5)
  plan = custom.StarPilotPlan.new_message(lateralCheck=lateral_check, vCruise=8.0, weatherId=501)
  NAV_TURN.write({"active": True, "maneuver": "turn", "modifier": "left"}, now=0.0)
  with custom.StarPilotPlan.from_bytes(plan.to_bytes()) as received:
    state = SimpleNamespace(sm=StatusMessages(carState=cs, starpilotPlan=received), engaged=True, is_metric=False,
                            always_on_lateral_active=False,
                            starpilot_toggles={"weather_presets": True, "increase_following_distance_rain": 0.5})
    current = snapshot(state, nav_active=True)
    assert current.steering_held is (not lateral_check)
    assert current.nav_turn and current.weather_gap
    assert chip_for(current).key == expected

