import __future__
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import pyray as rl

from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.onroad import extras
from openpilot.selfdrive.ui.tandem.onroad.developer import draw_lead_tag, lead_tag_motion
from openpilot.selfdrive.ui.tandem.onroad.lead import GapTracker, LeadSample, detailed_tag_on, lead_anchor, read_lead_sample


class Messages(dict):
  def __init__(self):
    super().__init__(radarState=SimpleNamespace(leadOne=SimpleNamespace(status=True, dRel=32.0, vRel=-2.0, modelProb=0.9, radar=False)),
                     carState=SimpleNamespace(vEgo=20.0), modelV2=object())
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
  s.sm['radarState'].leadOne.status = False
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
  assert uncertain.opacity == extras.LEAD_UNSURE and not uncertain.lead.closing
  recovered = tracker.update(sample(distance=28), 0.6)
  assert recovered.label == '1.4 s' and recovered.opacity == 1.0 and recovered.progress == 1.0


def test_details_follow_developer_view_or_lead_insights_but_not_an_unused_gate():
  s = state()
  assert not detailed_tag_on(s, Params())
  assert detailed_tag_on(s, Params(LeadInfo=True))
  assert detailed_tag_on(s, Params(DeveloperUI=True, DeveloperSidebar=True))
  assert not detailed_tag_on(s, Params(DeveloperUI=True))
  s.starpilot_toggles = {'developer_ui': True, 'developer_sidebar': True}
  assert detailed_tag_on(s, Params())


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


def test_view_draws_one_primary_tag_and_keeps_secondary_bars(monkeypatch):
  s, calls, bars = state(), [], []
  shape = [(1160, 610), (1080, 560), (1000, 610)]
  params = Params()
  renderer = SimpleNamespace(_params=params, _lead_vehicles=[SimpleNamespace(chevron=shape), SimpleNamespace(chevron=shape)],
                             _lead_info_enabled=False)
  tracker = GapTracker()
  tracker.update(sample(), 0.0)
  view = SimpleNamespace(model_renderer=renderer, _gap_state=tracker.update(sample(), 0.25), _braking_for_lead=False,
                         _content_rect=rl.Rectangle(0, 0, 2160, 1080), _tag_floor=lambda: 950, _lead_tag_on=True)
  radar = SimpleNamespace(leadOne=s.sm['radarState'].leadOne, leadTwo=SimpleNamespace(status=True))
  monkeypatch.setattr(extras, 'draw_lead_bar', lambda *args, **kwargs: bars.append(kwargs))
  method = view_method('_draw_leads', dict(extras=extras, lead_anchor=lead_anchor, detailed_tag_on=detailed_tag_on, ui_state=s,
                                        draw_lead_tag=lambda *args, **kwargs: calls.append(kwargs)))
  method(view, radar)
  assert len(calls) == len(bars) == 1 and calls[0]['compact'] and calls[0]['anchored']
  params.values.update(DeveloperUI=True, DeveloperSidebar=True)
  method(view, radar)
  assert not calls[-1]['compact']
  view._lead_tag_on, count = False, len(calls)   # Lead Car Tag off: no tag, the secondary bar stays
  method(view, radar)
  assert len(calls) == count and len(bars) == 3


def test_view_resets_acquisition_even_when_upstream_stops_drawing_a_lead():
  s, clock = state(), [0.0]
  view = SimpleNamespace(model_renderer=SimpleNamespace(_params=Params()), _gap_tracker=GapTracker(), _lead_tag_read=-1.0)
  method = view_method('_update_gap_tag', dict(ui_state=s, read_lead_sample=read_lead_sample, LEAD_TAG=SimpleNamespace(get=lambda: True),
                                            time=SimpleNamespace(monotonic=lambda: clock[0])))
  method(view)
  clock[0] = 0.3
  method(view)
  assert view._gap_state.progress == 1
  s.sm['radarState'].leadOne.status = False
  method(view)
  assert view._gap_state is None
  s.sm['radarState'].leadOne.status = True
  clock[0] = 1.0
  method(view)
  assert view._gap_state.progress == 0


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


def test_strip_and_tag_floor_stay_above_the_bar():
  from openpilot.selfdrive.ui.tandem.onroad.developer import strip_gap, strip_h
  from openpilot.selfdrive.ui.tandem.onroad.layers import bar_height, bar_margin
  names = dict(rl=rl, bar_margin=bar_margin, bar_height=bar_height, strip_gap=strip_gap, strip_h=strip_h)
  BAR_MARGIN, BAR_HEIGHT, STRIP_GAP, STRIP_H = bar_margin(), bar_height(), strip_gap(), strip_h()
  strip_rect, tag_floor = view_method('_strip_rect', dict(names)), view_method('_tag_floor', dict(names))
  c = rl.Rectangle(0, 0, 2000, 1000)
  bar_top = c.height - BAR_MARGIN - BAR_HEIGHT
  view = SimpleNamespace(_content_rect=c, _dev=None)
  view._strip_rect = lambda rect: strip_rect(view, rect)
  assert strip_rect(view, c) is None and tag_floor(view) == bar_top - STRIP_GAP
  view._dev = SimpleNamespace(strip=True)
  strip = strip_rect(view, c)
  assert strip.y + strip.height <= bar_top and strip.height == STRIP_H
  assert tag_floor(view) == strip.y - STRIP_GAP


def test_view_reads_the_lead_car_tag_switch_once_a_second():
  s, clock, reads = state(), [0.0], []
  view = SimpleNamespace(model_renderer=SimpleNamespace(_params=Params()), _gap_tracker=GapTracker(), _lead_tag_read=-1.0)
  switch = SimpleNamespace(get=lambda: reads.append(clock[0]) or False)
  method = view_method('_update_gap_tag', dict(ui_state=s, read_lead_sample=read_lead_sample, LEAD_TAG=switch,
                                            time=SimpleNamespace(monotonic=lambda: clock[0])))
  for t in (0.0, 0.3, 0.9, 1.1):
    clock[0] = t
    method(view)
  assert reads == [0.0, 1.1] and view._lead_tag_on is False
