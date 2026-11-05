"""Behavior at the owned adapters, upstream controller hooks and process boundaries."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem.settings.controllers import confirmed_controller, notice_controller
from openpilot.selfdrive.ui.tandem.prefs import DEVELOPER_STRIP, restore_prefs, save_prefs
from openpilot.starpilot.tandem.navigation import controller_type, publish_turn, read_turn
from openpilot.starpilot.tandem.state import HEADROOM, NAV_TURN, Snapshot
from openpilot.system.ui.widgets import DialogResult

ROOT = Path(__file__).resolve().parents[4]


def test_confirmation_matches_only_the_approved_action_and_restores_after_errors():
  requested, answered = [], []

  class Controller:
    def _request_confirmation(self, action, message, label, callback):
      requested.append((action, callback))

  controller = confirmed_controller(Controller)()

  def action():
    controller._request_confirmation("recalibrate", "Reset?", "Reset", answered.append)
    controller._request_confirmation("new_upstream_prompt", "Really?", "Continue", answered.append)

  controller.run_confirmed("recalibrate", action)
  assert answered == [DialogResult.CONFIRM]
  assert requested[0][0] == "new_upstream_prompt"
  with pytest.raises(RuntimeError):
    controller.run_confirmed("recalibrate", lambda: (_ for _ in ()).throw(RuntimeError("failed")))
  controller._request_confirmation("recalibrate", "Reset?", "Reset", answered.append)
  assert len(answered) == 1 and requested[-1][0] == "recalibrate"


def test_actual_model_controller_refusal_goes_to_the_owned_notice_sink():
  source = ROOT / "selfdrive/ui/layouts/settings/starpilot/driving_model.py"
  tree = ast.parse(source.read_text())
  controller = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "StarPilotDrivingModelLayout")
  controller.bases = []
  controller.body = [n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name in ("_show_notice", "start_download")]
  pushed, notified = [], []
  namespace = {"gui_app": SimpleNamespace(push_widget=pushed.append), "alert_dialog": lambda message: message,
               "tr": str, "ui_state": SimpleNamespace(started=True)}
  exec(compile(ast.fix_missing_locations(ast.Module(body=[controller], type_ignores=[])), str(source), "exec"), namespace)
  base = namespace[controller.name]
  for cls, messages in ((base, pushed), (notice_controller(base, notified.append), notified)):
    instance = cls()
    instance._update_model_metadata = lambda: None
    assert instance.start_download("model") is False
    assert messages == ["Cannot download models while driving."]
  assert pushed == notified


def test_actual_calibration_action_keeps_the_upstream_engagement_check():
  path = ROOT / "selfdrive/ui/layouts/settings/device.py"
  tree = ast.parse(path.read_text())
  controller = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DeviceLayout")
  controller.bases = []
  controller.body = [n for n in controller.body if isinstance(n, ast.FunctionDef)
                     and n.name in ("_request_confirmation", "_reset_calibration_prompt")]
  shown, removed, written = [], [], []
  state = SimpleNamespace(engaged=True)
  namespace = {"gui_app": SimpleNamespace(push_widget=shown.append), "ui_state": state, "tr": str,
               "DialogResult": DialogResult, "alert_dialog": lambda text: text,
               "ConfirmDialog": lambda text, label, callback: (text, label, callback)}
  exec(compile(ast.fix_missing_locations(ast.Module(body=[controller], type_ignores=[])), str(path), "exec"), namespace)
  obj = confirmed_controller(namespace[controller.name])()
  obj._params = SimpleNamespace(remove=removed.append, put_bool=lambda *args: written.append(args))
  obj._update_calib_description = lambda: None
  obj.run_confirmed("reset_calibration", obj._reset_calibration_prompt)
  assert shown == ["Disengage to Reset Calibration"] and not removed and not written
  state.engaged = False
  obj.run_confirmed("reset_calibration", obj._reset_calibration_prompt)
  assert set(removed) == {"CalibrationParams", "LiveTorqueParameters", "LiveParameters", "LiveParametersV2", "LiveDelay"}
  assert written == [("OnroadCycleRequested", True)]


def test_snapshot_is_atomic_and_rejects_old_future_and_malformed_data(tmp_path):
  state = Snapshot("sample.json")
  assert state.read(1.0, now=100) is None
  assert state.write({"active": True}, now=100)
  assert state.read(1.0, now=100.5) == {"active": True}
  assert state.read(1.0, now=101.1) is None and state.read(1.0, now=99) is None
  path = tmp_path / "state/sample.json"
  for broken in ("partial json", "[]", '{"time": "invalid"}', '{"time": 100}'):
    path.write_text(broken)
    assert state.read(1.0, now=100) is None
  assert state.write(0.0, now=100)
  assert state.read(1.0, now=100) == 0.0
  assert sorted(p.name for p in path.parent.iterdir()) == ["sample.json"]


def test_unavailable_snapshot_storage_does_not_break_the_driving_process(tmp_path, monkeypatch):
  blocked = tmp_path / "blocked"
  blocked.touch()
  monkeypatch.setenv("TANDEM_STATE_DIR", str(blocked))
  assert not NAV_TURN.write({"active": True}, now=100)
  assert read_turn(100) == {"active": False, "maneuver": "", "modifier": ""}


@pytest.mark.parametrize("prefix", ["d", "_desktop"])
def test_metric_preference_migrates_without_a_compiled_key_and_survives_backups(tandem_prefs, tmp_path, monkeypatch, prefix):
  monkeypatch.setenv("OPENPILOT_PREFIX", prefix)
  (tandem_prefs / prefix).mkdir()
  legacy = tandem_prefs / prefix / "DeveloperStripMetrics"
  legacy.write_text("steer,accel")
  assert DEVELOPER_STRIP.get() == "steer,accel"
  legacy.write_text("torque")
  assert DEVELOPER_STRIP.get() == "steer,accel"   # migrated once
  backup = tmp_path / "backup"
  save_prefs(backup)
  DEVELOPER_STRIP.set("none")
  assert DEVELOPER_STRIP.get() == "none"
  assert restore_prefs(backup) and DEVELOPER_STRIP.get() == "steer,accel"


def test_navigation_observes_the_upstream_choice_and_does_not_change_its_target(monkeypatch):
  monkeypatch.setenv("TANDEM_ROUTING", "0")  # original progress/control path; policy freshness is tested separately
  monkeypatch.setenv("TANDEM_ONROAD", "1")
  calls = []

  class Cruise:
    def _get_nav_turn_control_target(self, speed, sm, toggles, on_selected=None):
      calls.append((speed, sm, toggles))
      if on_selected:
        on_selected("turn", "sharpLeft")
      return 8.5

  cruise = controller_type(Cruise)()
  assert cruise._get_nav_turn_control_target(20, "messages", "toggles") == 8.5
  assert calls == [(20, "messages", "toggles")]
  assert (cruise.nav_turn_maneuver, cruise.nav_turn_modifier) == ("turn", "sharpLeft")
  monkeypatch.setenv("TANDEM_ONROAD", "0")
  assert controller_type(Cruise) is Cruise


def test_navigation_snapshot_tracks_the_binding_target_and_expires(monkeypatch):
  monkeypatch.setenv("TANDEM_ONROAD", "1")
  monkeypatch.setattr("openpilot.starpilot.tandem.state.time.monotonic", lambda: 100.0)
  cruise = SimpleNamespace(forcing_stop=False, nav_turn_target=8.0, nav_turn_maneuver="turn", nav_turn_modifier="right")
  planner = SimpleNamespace(starpilot_vcruise=cruise, v_cruise=8.0)
  messages = {"carControl": SimpleNamespace(longActive=True)}
  publish_turn(planner, messages)
  assert read_turn(100) == {"active": True, "maneuver": "turn", "modifier": "right"}
  assert not read_turn(101.1)["active"]
  for field, value in (("forcing_stop", True), ("nav_turn_target", 0.0)):
    setattr(cruise, field, value)
    publish_turn(planner, messages)
    assert read_turn(100) == {"active": False, "maneuver": "", "modifier": ""}
    setattr(cruise, field, False if field == "forcing_stop" else 8.0)
  planner.v_cruise = 6.0
  publish_turn(planner, messages)
  assert not read_turn(100)["active"]


def test_local_state_does_not_extend_the_upstream_schema_or_param_registry():
  header = (ROOT / "common/params_keys.h").read_text()
  schema = (ROOT / "cereal/custom.capnp").read_text()
  assert all(f'{{"{key}"' not in header for key in ("SpeedAtBottom", "DeveloperStripMetrics", "SteeringHeadroomWarning"))
  assert "navTurnControllingSpeed" not in schema and "navTurnModifier" not in schema
  assert HEADROOM.name != NAV_TURN.name


def test_font_shaping_and_fallback_are_scoped_to_tandem(monkeypatch):
  from openpilot.selfdrive.ui.tandem import draw, fonts
  from openpilot.system.ui.lib import application
  before = application.TEXT_SHAPERS[:]
  with draw._own_font:
    assert application.KEEP_FONT and len(application.TEXT_SHAPERS) == len(before) + 2
  assert not application.KEEP_FONT and application.TEXT_SHAPERS == before
  monkeypatch.setattr(fonts.rl, "load_font", lambda path: SimpleNamespace(texture=SimpleNamespace(id=1), source=path))
  monkeypatch.setattr(fonts.rl, "gen_texture_mipmaps", lambda _: None)
  monkeypatch.setattr(fonts.rl, "set_texture_filter", lambda *args: None)
  monkeypatch.setattr(fonts, "_loaded", {})
  assert fonts.font(application.FontWeight.ROMAN).source.endswith("Figtree-Regular.fnt")
  assert application.FontWeight.ROMAN == "Inter-Regular.fnt" and application.TEXT_SHAPERS == before


def test_disabled_screen_factories_do_not_initialize_tandem_fonts(monkeypatch):
  import sys
  from openpilot.selfdrive.ui.tandem import fonts, screens
  from openpilot.system.ui.lib import application

  def unexpected():
    pytest.fail("an upstream screen initialized Tandem fonts")

  monkeypatch.setattr(fonts, "prepare_fallback", unexpected)
  targets = [
    ("SETTINGS", screens.settings_window, "openpilot.selfdrive.ui.layouts.settings.settings", "SettingsLayout"),
    ("HOME", screens.home_layout, "openpilot.selfdrive.ui.layouts.home", "HomeLayout"),
    ("ONROAD", screens.onroad_view, "openpilot.selfdrive.ui.onroad.starpilot.starpilot_onroad_view", "StarPilotOnroadView"),
    ("SIDEBAR", screens.sidebar, "openpilot.selfdrive.ui.layouts.sidebar", "Sidebar"),
  ]
  before = application.TEXT_SHAPERS[:]
  for switch, factory, module, name in targets:
    expected = object()
    monkeypatch.setenv(f"TANDEM_{switch}", "0")
    monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{name: lambda result=expected: result}))
    assert factory() is expected
    assert not application.KEEP_FONT and application.TEXT_SHAPERS == before


def test_disabled_sound_factory_keeps_the_original_catalog(monkeypatch):
  from openpilot.starpilot.tandem.headroom import sound_type

  class Original:
    _sound_list = {1: ("engage.wav", 1, 1.0)}

  monkeypatch.setenv("TANDEM_ONROAD", "0")
  assert sound_type(Original) is Original
  assert Original._sound_list == {1: ("engage.wav", 1, 1.0)}
