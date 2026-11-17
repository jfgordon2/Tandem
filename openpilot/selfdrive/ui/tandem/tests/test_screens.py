"""Where Tandem joins StarPilot 7's UI (screens.py), and the sidebar, the first screen ported to it."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem import screens
from openpilot.selfdrive.ui.tandem.sidebar import (Health, MapsWatch, Status, connect_status, health_of, maps_status,
                                                   network_status)

UI = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("big_ui,environment,expected", [
  (True, {}, True),                                            # the big UI takes Tandem's screens by default
  (False, {}, False),                                          # the small UI stays StarPilot's
  (True, {"STARPILOT_UI": "upstream"}, False),                 # StarPilot's recovery override wins
  (True, {"TANDEM_SIDEBAR": "0"}, True),                       # one screen off: the others still need MainLayout
  (True, dict.fromkeys(screens.SWITCHES, "0"), False),         # all off: StarPilot 7 chooses as it would without Tandem
])
def test_tandem_takes_openpilots_layout_only_while_one_of_its_screens_is_on(big_ui, environment, expected):
  assert screens.essentials_ui(big_ui, environment) is expected


def test_starpilots_own_choice_stands_when_tandem_is_off(monkeypatch):
  from openpilot.selfdrive.ui.tandem import screenshot
  installed = []
  monkeypatch.setattr(screenshot, "install", installed.append)
  from openpilot.starpilot.ui.startup import UiSelection
  starpilot = UiSelection(True, "reviewed StarPilot assets verified")
  assert screens.ui_selection(starpilot, True, dict.fromkeys(screens.SWITCHES, "0")) is starpilot
  assert screens.ui_selection(starpilot, False, {}) is starpilot
  assert not installed                              # StarPilot's own UI gets no screenshot hook
  tandem = screens.ui_selection(starpilot, True, {})
  assert not tandem.custom and "Tandem" in tandem.reason and len(installed) == 1


@pytest.mark.parametrize("environment", [{"TANDEM_SIDEBAR": "0"}, {"STARPILOT_UI": "upstream"}])
def test_switched_off_the_sidebar_is_openpilots_and_leaves_tandems_fonts_alone(monkeypatch, environment):
  from openpilot.selfdrive.ui.tandem import fonts
  from openpilot.system.ui.lib import application
  monkeypatch.setattr(fonts, "prepare_fallback", lambda: pytest.fail("openpilot's sidebar initialized Tandem fonts"))
  for name, value in environment.items():
    monkeypatch.setenv(name, value)
  expected = object()
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.layouts.sidebar", SimpleNamespace(Sidebar=lambda: expected, SIDEBAR_WIDTH=300))
  before = application.TEXT_SHAPERS[:]
  assert screens.sidebar() is expected and screens._sidebar_width() == 300
  assert not application.KEEP_FONT and application.TEXT_SHAPERS == before


def test_the_sidebar_width_is_the_mocks_when_ours_is_on(monkeypatch):
  from openpilot.selfdrive.ui.tandem.sidebar import WIDTH
  monkeypatch.delenv("TANDEM_SIDEBAR", raising=False)
  monkeypatch.delenv("STARPILOT_UI", raising=False)
  assert screens._sidebar_width() == int(WIDTH)


def test_the_hooks_in_ui_and_main_layout_go_through_screens():
  """The two upstream edits stay one line each (README › Upstream integration)."""
  main = ast.parse((UI / "layouts/main.py").read_text())
  imports = {(node.module, alias.name, alias.asname) for node in ast.walk(main) if isinstance(node, ast.ImportFrom) for alias in node.names}
  assert ("openpilot.selfdrive.ui.tandem.screens", "sidebar", "Sidebar") in imports
  assert ("openpilot.selfdrive.ui.tandem.screens", "SIDEBAR_WIDTH", None) in imports
  assert not any(module == "openpilot.selfdrive.ui.layouts.sidebar" for module, _, _ in imports)
  ui = (UI / "ui.py").read_text()
  assert "selection = ui_selection(select_ui(" in ui and ui.count("ui_selection") == 2


def test_network_and_connect_rows():
  assert (network_status("--", 0).value, network_status("--", 0).health) == ("Offline", Health.OFF)
  assert network_status("Wi-Fi", 4).health == Health.GOOD
  assert network_status("LTE", 1).health == Health.WARN
  assert [connect_status(h).value for h in (Health.GOOD, Health.WARN, Health.BAD)] == ["Online", "Offline", "Error"]


def test_status_colors_compare_by_value():
  from openpilot.starpilot.ui.raylib import rl
  danger, warning = rl.Color(201, 34, 49, 255), rl.Color(218, 111, 37, 255)
  assert health_of(rl.Color(201, 34, 49, 255), danger, warning) == Health.BAD     # an equal color, not the same object
  assert health_of(rl.Color(218, 111, 37, 255), danger, warning) == Health.WARN
  assert health_of(rl.Color(255, 255, 255, 255), danger, warning) == Health.GOOD


def test_maps_row_follows_the_map_manager_and_keeps_the_last_answer():
  checking = Status("Maps", "Checking", Health.OFF)
  assert maps_status({"state": "transferring", "selectedGeneration": ""}, checking) == Status("Maps", "Downloading", Health.WARN)
  assert maps_status({"state": "completed", "selectedGeneration": "ab" * 32}, checking) == Status("Maps", "Ready", Health.GOOD)
  assert maps_status({"state": "idle", "selectedGeneration": ""}, checking) == Status("Maps", "Not downloaded", Health.OFF)
  ready = Status("Maps", "Ready", Health.GOOD)
  assert maps_status(None, ready) is ready                       # the manager answers only parked
  assert maps_status({"state": "unavailable"}, ready) is ready


def test_maps_watch_asks_off_the_drawing_thread_and_not_every_frame():
  now = [0.0]
  asked = []

  def ask():
    asked.append(now[0])
    return {"state": "idle", "selectedGeneration": "ab" * 32}

  watch = MapsWatch(ask, clock=lambda: now[0])
  try:
    assert watch.poll().value == "Checking"
    watch._pending.result(timeout=5)
    assert watch.poll().value == "Ready"
    now[0] = 5.0
    watch.poll()
    assert asked == [0.0]                                        # not again until REFRESH_S has passed
    now[0] = MapsWatch.REFRESH_S
    watch.poll()
    watch._pending.result(timeout=5)
    assert asked == [0.0, MapsWatch.REFRESH_S]
  finally:
    watch.close()


def test_a_failed_question_keeps_the_last_row():
  def ask():
    raise OSError("no map manager")

  watch = MapsWatch(ask, clock=lambda: 0.0)
  try:
    watch.poll()
    watch._pending.exception(timeout=5)
    assert watch.poll().value == "Checking"
  finally:
    watch.close()


@pytest.fixture
def starpilot_sidebar(monkeypatch):
  """StarPilot 7's Sidebar module over a stand-in ui_state (msgq and params need the device build) and no textures."""
  from openpilot.system.ui.lib import application
  state = SimpleNamespace(started=False, recording_audio=False, sm=SimpleNamespace(updated={"deviceState": False}))
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.ui_state", SimpleNamespace(ui_state=state, device=SimpleNamespace()))
  monkeypatch.setattr(application.gui_app, "texture", lambda *args, **kwargs: SimpleNamespace(width=1, height=1))
  monkeypatch.setattr(application.gui_app, "font", lambda *args, **kwargs: None)
  monkeypatch.delitem(sys.modules, "openpilot.selfdrive.ui.layouts.sidebar", raising=False)
  return state


def test_essentials_sidebar_reads_starpilots_sidebar_state(starpilot_sidebar):
  from openpilot.selfdrive.ui.layouts.sidebar import Colors, Sidebar
  from openpilot.selfdrive.ui.tandem.sidebar import essentials_sidebar
  sidebar = essentials_sidebar()
  try:
    assert isinstance(sidebar, Sidebar)
    sidebar._maps.poll = lambda: Status("Maps", "Ready", Health.GOOD)
    sidebar._net_type, sidebar._net_strength = "LTE", 1
    sidebar._temp_status.update("TEMP", "HIGH", Colors.DANGER)
    sidebar._connect_status.update("CONNECT", "ONLINE", Colors.GOOD)
    sidebar._panda_status.update("NO", "PANDA", Colors.DANGER)
    starpilot_sidebar.started, sidebar._recording_audio = True, True
    state = sidebar._state()
    assert [(row.label, row.value, row.health) for row in state.rows] == [
      ("Network", "LTE", Health.WARN), ("comma connect", "Online", Health.GOOD), ("Temperature", "Hot", Health.BAD),
      ("Vehicle", "Not connected", Health.BAD), ("Maps", "Ready", Health.GOOD)]
    assert state.onroad and state.recording_audio
  finally:
    sidebar._maps.close()


def test_essentials_sidebar_buttons_call_main_layouts_callbacks(starpilot_sidebar):
  from openpilot.selfdrive.ui.tandem.sidebar import essentials_sidebar
  sidebar = essentials_sidebar()
  called = []
  sidebar.set_callbacks(on_settings=lambda: called.append("settings"), on_flag=lambda: called.append("clip"),
                        open_settings=lambda: called.append("microphone"))
  try:
    for button in (sidebar._view._settings, sidebar._view._clip, sidebar._view._mic):
      button._click_callback()
    assert called == ["settings", "clip", "microphone"]
  finally:
    sidebar._maps.close()
