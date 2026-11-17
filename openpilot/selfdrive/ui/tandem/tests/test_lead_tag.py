import __future__
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.onroad.developer import draw_lead_tag, lead_tag_motion
from openpilot.selfdrive.ui.tandem.onroad.lead import LEAD_UNSURE, GapTracker, LeadSample, detailed_tag_on, lead_anchor, read_lead_sample


def _message(service: str) -> Any:
  """A real StarPilot 7 message, so a field the code reads that doesn't exist fails here as it would on the device."""
  from openpilot.cereal import log
  return log.Event.new_message().init(service)


def _radar() -> Any:
  radar = _message("radarState")
  lead = radar.leadOne
  lead.present, lead.dRel, lead.vRel, lead.modelProb, lead.radar = True, 32.0, -2.0, 0.9, False
  return radar


def _car() -> Any:
  car = _message("carState")
  car.vEgo = 20.0
  return car


class Messages(dict):
  def __init__(self):
    super().__init__(radarState=_radar(), carState=_car(), modelV2=object())
    self.valid = dict.fromkeys(self, True)
    self.alive = dict.fromkeys(self, True)
    self.recv_frame = dict.fromkeys(self, 10)


class Params:
  def __init__(self, **values):
    self.values = values

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def get_int(self, key):
    return int(self.values.get(key, 0))


def state():
  return SimpleNamespace(started=True, started_frame=5, is_metric=False, sm=Messages(), starpilot_toggles={})


def sample(**values):
  return replace(LeadSample(32.0, 20.0, -2.0), **values)


def test_live_messages_supply_distance_speed_and_confidence():
  s = state()
  assert read_lead_sample(s, 0.5) == sample()
  s.sm['radarState'].leadOne.modelProb = 0.3
  assert not read_lead_sample(s, 0.5).confident


@pytest.mark.parametrize('service', ['radarState', 'carState', 'modelV2'])
@pytest.mark.parametrize('failure', ['invalid', 'dead', 'previous_drive'])
def test_missing_or_stale_data_hides_the_tag(service, failure):
  s = state()
  if failure == 'invalid':
    s.sm.valid[service] = False
  elif failure == 'dead':
    s.sm.alive[service] = False
  else:
    s.sm.recv_frame[service] = s.started_frame - 1
  assert read_lead_sample(s, 0.5) is None


@pytest.mark.parametrize('distance,speed,relative', [(0, 20, 0), (-1, 20, 0), (float('nan'), 20, 0),
                                                   (32, float('inf'), 0), (32, -1, 0), (32, 20, float('nan'))])
def test_invalid_numeric_values_cannot_reach_the_display(distance, speed, relative):
  s = state()
  lead = s.sm['radarState'].leadOne
  lead.dRel, s.sm['carState'].vEgo, lead.vRel = distance, speed, relative
  assert read_lead_sample(s, 0.5) is None


def test_offroad_and_lost_leads_have_no_tag():
  s = state()
  s.started = False
  assert read_lead_sample(s, 0.5) is None
  s.started = True
  s.sm['radarState'].leadOne.present = False
  assert read_lead_sample(s, 0.5) is None


def test_gap_and_extra_data_use_the_existing_driver_units():
  tracker = GapTracker()
  value = tracker.update(sample(), 0.0)
  assert (value.label, value.lead.distance, value.lead.gap, value.lead.rel_speed) == ('1.6 s', '105 ft', '1.6 s', '−4 mph')
  assert value.lead.closing and value.lead.source == 'vision'
  value = tracker.update(sample(metric=True, radar=True), 0.5)
  assert (value.label, value.lead.distance, value.lead.rel_speed, value.lead.source) == ('1.6 s', '32 m', '−7 km/h', 'radar')


def test_near_stop_distance_and_hysteresis_avoid_division_by_zero_and_flicker():
  tracker = GapTracker()
  stopped = sample(distance=8, speed=0, metric=True)
  assert tracker.update(stopped, 0.0).label == '8 m'
  assert tracker.update(replace(stopped, speed=1.2), 0.3).label == '8 m'
  assert tracker.update(replace(stopped, speed=1.6), 0.6).label == '5.0 s'
  assert tracker.update(replace(stopped, speed=1.2), 0.9).label.endswith(' s')
  value = tracker.update(replace(stopped, speed=0.8, metric=False), 1.2)
  assert value.label == '26 ft' and value.lead.distance == '26 ft' and value.lead.gap == '--'


def test_value_is_smoothed_without_restarting_acquisition():
  tracker = GapTracker()
  tracker.update(sample(), 0.0)
  tracker.update(sample(), 0.3)
  changed = tracker.update(sample(distance=30), 0.35)
  assert changed.label == '1.6 s' and changed.progress == 1.0
  assert tracker.update(sample(distance=30), 2.0).label == '1.5 s'


def test_lost_lead_and_cut_in_restart_motion_and_clear_the_old_value():
  tracker = GapTracker()
  assert tracker.update(sample(distance=60), 0.0).progress == 0.0
  assert tracker.update(sample(distance=60), 0.25).progress == 1.0
  nearer = tracker.update(sample(distance=20), 0.5)
  assert nearer.progress == 0.0 and nearer.label == '1.0 s'
  assert tracker.update(None, 0.6) is None
  reacquired = tracker.update(sample(distance=40), 0.7)
  assert reacquired.progress == 0.0 and reacquired.label == '2.0 s'


def test_uncertain_lead_suppresses_every_number_and_does_not_reuse_old_values():
  tracker = GapTracker()
  tracker.update(sample(), 0.0)
  uncertain = tracker.update(sample(confident=False, distance=28), 0.5)
  assert (uncertain.label, uncertain.lead.distance, uncertain.lead.gap, uncertain.lead.rel_speed) == ('--', '--', '--', '--')
  assert uncertain.opacity == LEAD_UNSURE and not uncertain.lead.closing
  recovered = tracker.update(sample(distance=28), 0.6)
  assert recovered.label == '1.4 s' and recovered.opacity == 1.0 and recovered.progress == 1.0


def test_details_follow_developer_view_or_lead_info() -> None:
  from openpilot.starpilot.ui.appearance_preferences import LeadInfoMode, OnroadAppearance
  assert not detailed_tag_on(OnroadAppearance())
  assert detailed_tag_on(OnroadAppearance(lead_info_mode=LeadInfoMode.DISTANCE))   # StarPilot's Lead Info (Lead Insights)
  assert detailed_tag_on(OnroadAppearance(show_developer_sidebar=True))            # Developer View


def test_anchor_follows_projected_lead_and_rejects_missing_geometry():
  anchor = lead_anchor([(562.5, 350), (500, 300), (437.5, 350)])
  assert anchor.x == 500 and anchor.y < 300
  assert lead_anchor([]) is None and lead_anchor(None) is None
  assert lead_anchor([(0, 0), (0, 1), (0, 0)]) is None
  assert lead_anchor([(0, 50), (float('nan'), 0), (0, 50)]) is None


def test_acquisition_reveals_anchor_then_connector_then_tag():
  assert lead_tag_motion(0) == (0, 0, 0)
  anchor, connector, tag = lead_tag_motion(0.1)
  assert anchor > 0 and connector == tag == 0
  anchor, connector, tag = lead_tag_motion(0.3)
  assert anchor == 1 and connector > 0 and tag == 0
  assert lead_tag_motion(1) == (1, 1, 1)


@pytest.fixture
def painted(monkeypatch):
  words, discs, fills = [], [], []
  monkeypatch.setattr(draw, 'text_width', lambda text, size, weight: len(text) * 10.0)
  monkeypatch.setattr(draw, 'text', lambda rect, text, size, *args: words.append((text, size)))
  monkeypatch.setattr(draw, 'disc', lambda point, radius, color: discs.append((point, radius)))
  monkeypatch.setattr(draw, 'fill', lambda *args: fills.append(args))
  monkeypatch.setattr(draw, 'stroke', lambda *args: None)
  return words, discs, fills


def test_both_views_reuse_the_tag_and_keep_text_full_size_during_entrance(painted):
  words, discs, fills = painted
  value = GapTracker().update(sample(), 0.0)
  draw_lead_tag(500, 300, value.lead, compact=True, value=value.label, anchored=True, progress=0.3)
  assert discs and fills and not words
  draw_lead_tag(500, 300, value.lead, compact=True, value=value.label, anchored=True, progress=0.7)
  assert [word for word, size in words] == ['1.6 s']
  entering_size = words[0][1]
  words.clear()
  draw_lead_tag(500, 300, value.lead, anchored=True)
  assert [word for word, size in words] == ['105 ft', '1.6 s', '−4 mph']
  assert all(size == entering_size for word, size in words)


def test_tags_fit_the_view_and_keep_only_the_anchor_when_the_roof_is_too_high(painted):
  words, discs, _ = painted
  value = GapTracker().update(sample(), 0.0)
  bounds = rl.Rectangle(0, 0, 1000, 700)
  box = draw_lead_tag(20, 300, value.lead, compact=True, anchored=True, bounds=bounds)
  assert box.x >= 0 and box.x + box.width <= 1000 and words
  words.clear()
  assert draw_lead_tag(500, 30, value.lead, compact=True, anchored=True, bounds=bounds) is None
  assert not words and discs


@pytest.mark.parametrize('value', ['1.6 s', '8 m', '26 ft', '--'])
def test_short_and_long_single_values_are_centered_in_the_tag(painted, monkeypatch, value):
  boxes = []
  monkeypatch.setattr(draw, 'text', lambda rect, *args: boxes.append(rect))
  lead = GapTracker().update(sample(), 0.0).lead
  tag = draw_lead_tag(500, 300, lead, compact=True, value=value, anchored=True, progress=0.7)
  assert len(boxes) == 1
  assert boxes[0].x + boxes[0].width / 2 == pytest.approx(tag.x + tag.width / 2)


def view_method(name, namespace):
  """Exercise the view's integration without importing its device/cereal stack, as the alert render scene does."""
  path = Path(__file__).resolve().parents[1] / 'onroad' / 'view.py'
  cls = next(node for node in ast.parse(path.read_text()).body if isinstance(node, ast.ClassDef) and node.name == 'EssentialsOnroadView')
  method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
  exec(compile(ast.Module([method], []), str(path), 'exec', flags=__future__.annotations.compiler_flag), namespace)   # as view.py
  return namespace[name]


def test_tag_never_sinks_below_the_floor_and_drops_the_anchor_there(painted):
  words, discs, _ = painted
  lead = GapTracker().update(sample(), 0.0).lead
  bounds = rl.Rectangle(0, 0, 1000, 1000)
  high = draw_lead_tag(500, 300, lead, anchored=True, bounds=bounds, floor=600)
  assert high.y + high.height <= 600 and discs        # far above the floor: as before, with its anchor
  discs.clear()
  for top_y in (640, 690, 750):                       # at or under the strip or bar
    box = draw_lead_tag(500, top_y, lead, anchored=True, bounds=bounds, floor=600)
    assert box.y + box.height == 600
  assert not discs




def test_developer_view_reads_starpilots_messages_and_metrics() -> None:
  from openpilot.selfdrive.ui.tandem.onroad import developer
  from openpilot.starpilot.ui.live_developer_sidebar import DeveloperMetric
  car, control, device = _message("carState"), _message("carControl"), _message("deviceState")
  car.vEgo, car.aEgo, car.steeringAngleDeg = 20.0, 0.31, -4.2
  control.actuators.accel, control.actuators.torque = 0.42, -0.3
  device.cpuUsagePercent, device.maxTempC, device.gpuUsagePercent, device.memoryUsagePercent = [40, 44], 61.0, 18, 39
  delay, controls, radar, vehicle = _message("lateralDelay"), _message("controlsState"), _message("radarState"), _message("vehicleParameters")
  delay.lateralDelay, controls.curvature, vehicle.steerRatio = 0.18, 0.003, 15.3
  radar.leadOne.present, radar.leadOne.dRel, radar.leadOne.vRel, radar.leadOne.radar = True, 38.0, -1.0, True
  messages = {"carState": car, "carControl": control, "deviceState": device, "lateralDelay": delay, "controlsState": controls,
              "radarState": radar, "vehicleParameters": vehicle}
  sm = type("SM", (), {"valid": dict.fromkeys(messages, True), "__getitem__": lambda self, name: messages[name]})()
  state = SimpleNamespace(developer_metrics=(DeveloperMetric("STEER RATIO", "15.30000"),),
                          curve=None, speed_limit=SimpleNamespace(source="Map Data"))
  data = developer.read(sm, state, metric=True)
  assert data.lead is not None and data.lead.distance == "38 m" and data.lead.source == "radar"
  assert (data.accel, data.want, data.delay, data.steer, data.torque, data.ratio) == ("+0.31", "+0.42", "0.18 s", "−4°", "30%", "15.30")
  assert data.limit_source == "map data" and data.metrics == (("STEER RATIO", "15.30000"),) and round(data.cpu, 2) == 0.42
  assert [label for label, _ in data.strip_values()] == ["accel", "want", "lat", "delay", "steer"]


def test_the_strip_keeps_known_metrics_in_order_and_at_most_five() -> None:
  from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_DEFAULT, strip_keys
  assert strip_keys(None) == list(STRIP_DEFAULT)
  assert strip_keys("ratio,accel,jerk") == ["accel", "ratio"]   # StarPilot 7 publishes no jerk
  assert strip_keys("none") == []
  assert len(strip_keys("accel,want,lat,delay,steer,torque,ratio")) == 5
