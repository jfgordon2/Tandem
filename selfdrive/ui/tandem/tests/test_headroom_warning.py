from types import SimpleNamespace

import numpy as np
import pytest
import pyray as rl
from cereal import custom, log

from openpilot.selfdrive.ui import soundd
from openpilot.selfdrive.ui.onroad.alert_renderer import Alert
from openpilot.selfdrive.ui.onroad import model_renderer
from openpilot.selfdrive.ui.tandem.onroad import view as onroad
from openpilot.selfdrive.ui.tandem.onroad.layers import (
  AT_LIMIT, COMFORTABLE, WORKING, ArcState, Headroom, LIMIT_BORDER_COLOR, LIMIT_LANE_COLOR,
)


class Memory(dict):
  def __init__(self):
    super().__init__()
    self.writes = []

  def put_nonblocking(self, key, value):
    self.writes.append((key, value))
    self[key] = value


class Messages(dict):
  def __init__(self):
    super().__init__(carControl=SimpleNamespace(latActive=True), carState=SimpleNamespace(steeringPressed=False),
                     selfdriveState=SimpleNamespace(alertSize=log.SelfdriveState.AlertSize.none),
                     starpilotSelfdriveState=SimpleNamespace(alertSize=custom.StarPilotSelfdriveState.AlertSize.none))
    services = ("carControl", "carState", "carOutput", "controlsState", "selfdriveState")
    self.valid = dict.fromkeys(services, True)
    self.alive = dict.fromkeys(services, True)
    self.recv_frame = dict.fromkeys(services, 10)


@pytest.fixture
def warning_view(monkeypatch):
  now, usage, alert, fading = [1.0], [0.9], [None], [None]
  sm = Messages()
  state = SimpleNamespace(sm=sm, started=True, started_frame=5)
  monkeypatch.setattr(onroad, "ui_state", state)
  monkeypatch.setattr(onroad.time, "monotonic", lambda: now[0])
  view = onroad.EssentialsOnroadView.__new__(onroad.EssentialsOnroadView)
  view._closed = True  # no camera resources in this state-only fixture
  view._headroom, view._arc_state = Headroom(), ArcState()
  view._headroom_warning = view._headroom_chimed = False
  view._memory = Memory()
  view._gap_tracker = onroad.GapTracker()
  view._gap_state = None
  view.model_renderer = SimpleNamespace(lane_line_color_override=None)
  view.alert_renderer = SimpleNamespace(get_alert=lambda _: alert[0], will_render=lambda: (fading[0], True), level=lambda: None)
  view.is_in_reverse = lambda: False
  view._camera_view = lambda: 2
  view._preview = lambda: 0.95
  torque = SimpleNamespace(_torque_filter=SimpleNamespace(x=0.0))
  torque._update_state = lambda: setattr(torque._torque_filter, "x", usage[0])
  view._torque_bar = torque
  return SimpleNamespace(view=view, now=now, usage=usage, alert=alert, fading=fading, state=state, sm=sm)


def enter_limit(fixture):
  fixture.view._update_headroom()
  fixture.now[0] += 0.51
  fixture.view._update_headroom()


def test_debounce_release_margin_and_inactive_reset():
  headroom = Headroom()
  assert headroom.stage(0.9, 0.0) == WORKING
  assert headroom.stage(0.7, 0.3) == WORKING  # a brief spike never warns
  assert headroom.stage(-0.9, 0.4) == WORKING
  assert headroom.stage(-0.9, 0.91) == AT_LIMIT
  assert headroom.stage(-0.84, 1.0) == AT_LIMIT  # no repeated chime at the entry threshold
  assert headroom.stage(-0.79, 1.1) == WORKING
  assert headroom.stage(0.95, 1.2) == WORKING
  assert headroom.stage(0.95, 1.3, active=False) == COMFORTABLE
  assert headroom.stage(0.95, 5.0) == WORKING  # time spent inactive cannot satisfy the hold


def test_one_event_per_curve_and_all_visuals_share_warning_state(warning_view, monkeypatch):
  f, view = warning_view, warning_view.view
  normal_border = rl.Color(22, 127, 64, 255)
  monkeypatch.setattr(onroad.StarPilotOnroadView, "_get_border_color", lambda _: normal_border)
  view._update_headroom()
  assert not view._headroom_warning and not view._memory
  enter_limit(f)
  assert view._arc_state.stage == AT_LIMIT and view._headroom_warning
  assert view.model_renderer.lane_line_color_override == LIMIT_LANE_COLOR
  assert view._get_border_color() == LIMIT_BORDER_COLOR
  first_event = view._memory["SteeringHeadroomWarning"]
  for f.now[0], f.usage[0] in ((2.0, 0.84), (2.1, -0.9), (2.2, 0.86)):
    view._update_headroom()
    assert view._memory["SteeringHeadroomWarning"] == first_event
  f.now[0], f.usage[0] = 3.0, 0.7
  view._update_headroom()
  assert not view._headroom_warning
  assert view.model_renderer.lane_line_color_override is None
  assert view._get_border_color() == normal_border
  assert view._memory["SteeringHeadroomWarning"] == 0.0
  f.usage[0] = 0.95
  enter_limit(f)
  assert view._memory["SteeringHeadroomWarning"] > first_event


@pytest.mark.parametrize("stop", ["offroad", "inactive", "override", "reverse", "driver_camera", "invalid", "stale", "previous_drive"])
def test_warning_clears_and_restarts_hold_when_steering_is_unavailable(warning_view, stop):
  f, view = warning_view, warning_view.view
  enter_limit(f)
  if stop == "offroad":
    f.state.started = False
  elif stop == "inactive":
    f.sm["carControl"].latActive = False
  elif stop == "override":
    f.sm["carState"].steeringPressed = True
  elif stop == "reverse":
    view.is_in_reverse = lambda: True
  elif stop == "driver_camera":
    view._camera_view = lambda: onroad.CAMERA_VIEW_DRIVER
  elif stop == "invalid":
    f.sm.valid["carOutput"] = False
  elif stop == "stale":
    f.sm.alive["controlsState"] = False
  else:
    f.sm.recv_frame["carControl"] = 1
  view._update_headroom()
  assert not view._headroom_warning
  assert view._arc_state.stage == COMFORTABLE
  assert view.model_renderer.lane_line_color_override is None
  assert view._memory["SteeringHeadroomWarning"] == 0.0
  f.state.started = f.sm["carControl"].latActive = True
  f.sm["carState"].steeringPressed = False
  view.is_in_reverse, view._camera_view = lambda: False, lambda: 2
  f.sm.valid["carOutput"] = f.sm.alive["controlsState"] = True
  f.sm.recv_frame["carControl"] = 10
  f.now[0] = 5.0
  view._update_headroom()
  assert view._arc_state.stage == WORKING and not view._headroom_warning


@pytest.mark.parametrize("alert_type", ["takeOver/critical", "promptDriverDistracted/warning", ""])
def test_existing_alert_and_its_exit_animation_keep_visual_priority(warning_view, alert_type):
  f, view = warning_view, warning_view.view
  alert = Alert(alert_type=alert_type)
  f.alert[0] = alert
  enter_limit(f)
  assert view._arc_state.stage == AT_LIMIT and not view._headroom_warning
  assert view.model_renderer.lane_line_color_override is None and not view._memory
  f.alert[0], f.fading[0] = None, alert
  view._update_headroom()
  assert not view._headroom_warning
  f.fading[0] = None
  view._update_headroom()
  assert view._headroom_warning
  assert view.model_renderer.lane_line_color_override == LIMIT_LANE_COLOR
  assert view._memory["SteeringHeadroomWarning"] == f.now[0]


def test_each_visible_headroom_warning_chimes_once_after_an_alert_clears(warning_view):
  f, view = warning_view, warning_view.view
  enter_limit(f)
  first_event = view._memory["SteeringHeadroomWarning"]
  for _ in range(3):
    f.now[0] += 0.1
    view._update_headroom()
  assert view._memory.writes == [("SteeringHeadroomWarning", first_event)]
  f.alert[0] = Alert(alert_type="takeOver/critical")
  view._update_headroom()
  assert not view._headroom_warning
  assert view._memory["SteeringHeadroomWarning"] == 0.0
  f.alert[0], f.fading[0] = None, f.alert[0]
  f.now[0] += 1
  view._update_headroom()
  assert not view._headroom_warning
  assert len(view._memory.writes) == 2
  f.fading[0] = None
  view._update_headroom()
  assert view._headroom_warning
  second_event = view._memory["SteeringHeadroomWarning"]
  assert second_event == f.now[0] and second_event > first_event
  for _ in range(3):
    f.now[0] += 0.1
    view._update_headroom()
  assert view._memory.writes == [("SteeringHeadroomWarning", first_event), ("SteeringHeadroomWarning", 0.0),
                                 ("SteeringHeadroomWarning", second_event)]


@pytest.mark.parametrize("service", ["selfdriveState", "starpilotSelfdriveState"])
@pytest.mark.parametrize("alert_type", ["steerSaturated/warning", "goatSteerSaturated/warning",
                                       "firefoxSteerSaturated/warning", "thisIsFineSteerSaturated/warning"])
def test_steering_limit_alert_starts_one_warning_before_headroom_estimate_reaches_limit(warning_view, service, alert_type):
  f, view = warning_view, warning_view.view
  f.usage[0] = 0.7
  f.sm.valid[service] = True
  f.sm[service].alertType = alert_type
  f.alert[0] = Alert(alert_type=alert_type)
  view._update_headroom()
  assert view._arc_state.stage == WORKING and view._headroom_warning
  assert view.model_renderer.lane_line_color_override == LIMIT_LANE_COLOR
  assert view._memory.writes == [("SteeringHeadroomWarning", f.now[0])]
  f.now[0] += 1
  view._update_headroom()
  assert len(view._memory.writes) == 1


def test_hidden_view_clears_feedback(warning_view, monkeypatch):
  f, view = warning_view, warning_view.view
  enter_limit(f)
  monkeypatch.setattr(onroad.StarPilotOnroadView, "hide_event", lambda _: None)
  view.hide_event()
  assert not view._headroom_warning and not view._headroom_chimed
  assert view.model_renderer.lane_line_color_override is None
  assert view._memory["SteeringHeadroomWarning"] == 0.0


def test_inherited_border_draws_amber_then_restores_normal_color(warning_view, monkeypatch):
  from openpilot.selfdrive.ui.onroad.starpilot import starpilot_onroad_view as upstream
  f, view = warning_view, warning_view.view
  view._get_border_width = lambda: 12
  view._draw_hud_controls = False
  view._content_rect = rl.Rectangle(12, 12, 2136, 1056)
  view._render_layers = lambda: None   # drawn just before the border; this test is about the border's color
  normal = rl.Color(22, 127, 64, 255)
  monkeypatch.setattr(onroad.StarPilotOnroadView, "_get_border_color", lambda _: normal)
  for name in ("render_background_effects", "render_overlay"):
    monkeypatch.setattr(upstream, name, lambda *_: None)
  monkeypatch.setattr(rl, "draw_rectangle_lines_ex", lambda *_: None)
  for name in ("begin_scissor_mode", "end_scissor_mode"):
    monkeypatch.setattr(rl, name, lambda *_: None)
  colors = []
  monkeypatch.setattr(rl, "draw_rectangle_rounded_lines_ex", lambda _r, _round, _segments, _width, color: colors.append(color))
  enter_limit(f)
  view._draw_border(rl.Rectangle(0, 0, 2160, 1080))
  f.sm["carControl"].latActive = False
  view._update_headroom()
  view._draw_border(rl.Rectangle(0, 0, 2160, 1080))
  assert colors == [LIMIT_BORDER_COLOR, normal]


def test_real_lane_renderer_tints_lines_preserves_confidence_and_restores_settings(monkeypatch):
  renderer = model_renderer.ModelRenderer.__new__(model_renderer.ModelRenderer)
  renderer._params, renderer._rect = object(), rl.Rectangle(0, 0, 2160, 1080)
  renderer._lane_lines = [SimpleNamespace(projected_points=np.ones((4, 2))) for _ in range(4)]
  renderer._lane_line_probs = np.array([0.9, 0.5, 0.7, 0.1])
  renderer._road_edges = []
  renderer._lane_centering_direction = lambda: 1
  custom_color = rl.Color(12, 34, 56, 200)
  monkeypatch.setattr(model_renderer, "get_param_color", lambda *_: custom_color)
  drawn = []
  monkeypatch.setattr(model_renderer, "draw_polygon", lambda _r, _p, color: drawn.append(color))
  renderer.lane_line_color_override = LIMIT_LANE_COLOR
  renderer._draw_lane_lines()
  assert [(c.r, c.g, c.b) for c in drawn] == [(255, 138, 77)] * 4
  assert [c.a for c in drawn] == [178, 127, 178, 25]
  renderer.lane_line_color_override = None
  drawn.clear()
  renderer._draw_lane_lines()
  assert (drawn[0].r, drawn[0].g, drawn[0].b) == (12, 34, 56)
  lane_centering = model_renderer.OCEAN_BLUE_LANE_LINES_COLOR
  assert (drawn[2].r, drawn[2].g, drawn[2].b, drawn[2].a) == (lane_centering.r, lane_centering.g, lane_centering.b, 178)


@pytest.fixture
def warning_sound(warning_view):
  sound = soundd.Soundd.__new__(soundd.Soundd)
  sound.params_memory = warning_view.view._memory
  sound.headroom_warning_seen = 0.0
  sound.current_alert = soundd.AudibleAlert.none
  sound.current_alert_type = ""
  sound.current_sound_frame = 0
  sound.current_volume = 1.0
  sound.loaded_sounds = {soundd.STEERING_HEADROOM_ALERT: np.ones(4, dtype=np.float32)}
  sound.selfdrive_timeout_alert = False
  return sound


def test_chime_plays_once_and_releases_exact_audio_boundary(warning_view, warning_sound):
  f, sound = warning_view, warning_sound
  enter_limit(f)
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.STEERING_HEADROOM_ALERT
  np.testing.assert_array_equal(sound.get_sound_data(4), np.ones(4))
  sound.current_alert_type = ""  # normal selfdrive updates clear the type each soundd tick
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.AudibleAlert.none
  np.testing.assert_array_equal(sound.get_sound_data(4), np.zeros(4))
  f.now[0] += 0.1
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.AudibleAlert.none
  f.usage[0] = 0.7
  f.view._update_headroom()
  f.usage[0] = 0.95
  enter_limit(f)
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.STEERING_HEADROOM_ALERT


@pytest.mark.parametrize("block", ["audible", "timeout", "invalid", "stale", "stock_visual", "custom_visual"])
def test_chime_cannot_replace_existing_alerts_or_replay_after_them(warning_view, warning_sound, block):
  f, sound = warning_view, warning_sound
  enter_limit(f)
  if block == "audible":
    sound.current_alert = soundd.AudibleAlert.warningImmediate
  elif block == "timeout":
    sound.selfdrive_timeout_alert = True
  elif block == "invalid":
    f.sm.valid["selfdriveState"] = False
  elif block == "stale":
    f.sm.alive["selfdriveState"] = False
  elif block == "stock_visual":
    f.sm["selfdriveState"].alertSize = log.SelfdriveState.AlertSize.full
  else:
    f.sm["starpilotSelfdriveState"].alertSize = custom.StarPilotSelfdriveState.AlertSize.full
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert != soundd.STEERING_HEADROOM_ALERT
  sound.current_alert, sound.selfdrive_timeout_alert = soundd.AudibleAlert.none, False
  f.sm.valid["selfdriveState"] = f.sm.alive["selfdriveState"] = True
  f.sm["selfdriveState"].alertSize = log.SelfdriveState.AlertSize.none
  f.sm["starpilotSelfdriveState"].alertSize = custom.StarPilotSelfdriveState.AlertSize.none
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.AudibleAlert.none


def test_real_alert_selection_interrupts_a_playing_headroom_chime(warning_view, warning_sound, tmp_path):
  f, sound = warning_view, warning_sound
  enter_limit(f)
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.STEERING_HEADROOM_ALERT
  sound.openpilot_crashed_played = False
  sound.error_log = tmp_path / "no-error.txt"
  sound.starpilot_toggles = SimpleNamespace(goat_scream_critical_alerts=False)
  f.sm.updated = {"selfdriveState": True}
  f.sm["selfdriveState"] = SimpleNamespace(alertSound=SimpleNamespace(raw=soundd.AudibleAlert.warningImmediate),
                                          alertType="takeOver/critical", alertSize=log.SelfdriveState.AlertSize.full,
                                          alertStatus=log.SelfdriveState.AlertStatus.critical)
  sound.loaded_sounds[soundd.AudibleAlert.warningImmediate] = np.ones(4, dtype=np.float32)
  f.sm["starpilotSelfdriveState"].alertSound = SimpleNamespace(raw=soundd.StarPilotAudibleAlert.none)
  sound.get_audible_alert(f.sm)
  sound.update_headroom_sound(f.sm)
  assert sound.current_alert == soundd.AudibleAlert.warningImmediate
  assert sound.current_alert_type == "takeOver/critical"


@pytest.mark.parametrize("payload", [None, b"invalid", float("nan"), float("inf"), -1, 0, 0.1, 10.0])
def test_chime_drops_missing_invalid_expired_or_future_requests(warning_view, warning_sound, payload):
  warning_sound.params_memory["SteeringHeadroomWarning"] = payload
  warning_view.now[0] = 2.0
  warning_sound.update_headroom_sound(warning_view.sm)
  assert warning_sound.current_alert == soundd.AudibleAlert.none


def test_chime_is_the_prompt_at_prompt_volume_and_retains_steering_limit_mute_type(warning_view, warning_sound):
  from openpilot.common.params import Params
  sound = warning_sound
  sound.volume_settings = soundd.read_volume_settings(Params(return_defaults=True))
  sound.volume_settings["PromptVolume"] = 25
  assert soundd.sound_list[soundd.STEERING_HEADROOM_ALERT][0] == "prompt.wav"   # the prompt, not the take-control warning
  sound.update_volume_map()
  enter_limit(warning_view)
  sound.update_headroom_sound(warning_view.sm)
  sound.current_alert_type = ""
  sound.update_headroom_sound(warning_view.sm)
  assert sound.get_volume_override() == 0.25
  assert soundd.should_mute_turn_steering_limit_alert(sound.current_alert_type, 1.0, 5.0)
  assert soundd.sound_list[soundd.STEERING_HEADROOM_ALERT][1] == 1


def test_help_steer_stands_in_for_steer_saturated_only_while_it_shows(monkeypatch):
  saturated = SimpleNamespace(alert_type="steerSaturated/warning")
  monkeypatch.setattr(onroad.AlertRenderer, "get_alert", lambda self, sm: saturated)
  renderer = onroad.EssentialsAlertRenderer.__new__(onroad.EssentialsAlertRenderer)
  renderer._prev_alert = None
  renderer.headroom_warning = lambda: True
  assert renderer.get_alert(None) is None          # Help steer already says it: no second alert
  renderer.headroom_warning = lambda: False
  assert renderer.get_alert(None) is saturated     # without it, openpilot's alert shows as before


def test_soundd_mutes_steer_saturated_only_while_the_headroom_warning_is_fresh(monkeypatch):
  sound = soundd.Soundd.__new__(soundd.Soundd)
  monkeypatch.setattr(soundd.time, "monotonic", lambda: 100.0)
  sound.headroom_warning_since = 0.0
  assert not sound.headroom_warning_active()
  sound.headroom_warning_since = 95.0
  assert sound.headroom_warning_active()
  sound.headroom_warning_since = 60.0                 # stale: the UI never cleared it
  assert not sound.headroom_warning_active()
