"""Parked Home behavior across the native layout boundary."""
from __future__ import annotations

import importlib
import sys
import time
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from openpilot.selfdrive.ui.tandem import screens, tokens as T
from openpilot.selfdrive.ui.tandem.home import home_content_rect, readiness, software_line
from openpilot.selfdrive.ui.tandem.software import HomeSoftware, InstallTarget, SoftwareState, SoftwareWatch, project_software
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.lib.application import MousePos, gui_app
from openpilot.system.ui.widgets import Widget


@pytest.fixture
def home_layout(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
  """Use the real inherited layout with stubs for its device-only dependencies."""
  state = SimpleNamespace(ignition=False, projection_read_only=False, replay_clock=None, is_offroad=lambda: True)
  params = SimpleNamespace(get=lambda *args, **kwargs: None)

  class Panel(Widget):
    """A render-free upstream widget with the offroad owner's public fields."""

    def __init__(self) -> None:
      super().__init__()
      self.sorted_alerts: list[Any] = []
      self.excessive_actuation_btn = Mock(is_visible=False)
      self.snooze_btn = Mock(is_visible=False)

    def set_dismiss_callback(self, callback: Any) -> None:
      self.set_click_callback(callback)

    def refresh(self) -> int:
      return sum(item.visible for item in self.sorted_alerts)

    def _render(self, rect: rl.Rectangle) -> None:
      pass

  modules = {
    "openpilot.common.params": {"Params": lambda: params},
    "openpilot.selfdrive.ui.ui_state": {"ui_state": state},
    "openpilot.selfdrive.ui.widgets.offroad_alerts": {"UpdateAlert": Panel, "OffroadAlert": Panel},
    "openpilot.selfdrive.ui.widgets.exp_mode_button": {"ExperimentalModeButton": Panel},
    "openpilot.selfdrive.ui.widgets.prime": {"PrimeWidget": Panel},
    "openpilot.selfdrive.ui.widgets.setup": {"SetupWidget": Panel},
  }
  for name, attrs in modules.items():
    module = ModuleType(name)
    module.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, module)
  imports = ("openpilot.selfdrive.ui.layouts.home", "openpilot.selfdrive.ui.tandem.home_layout")
  for name in imports:
    # Record the previous module entry so mock-bound imports do not affect other tests.
    monkeypatch.setitem(sys.modules, name, ModuleType(name))
    del sys.modules[name]

  layout = importlib.import_module(imports[0])
  binding = importlib.import_module(imports[1])
  headers: list[Any] = []
  monkeypatch.setattr(layout.HomeLayout, "_render_header", lambda self: headers.append(self.current_state))
  monkeypatch.setattr(gui_app, "_mouse_events", [])
  software = Mock()
  watch = SoftwareWatch(Mock, lambda _key: None, lambda: True, Mock())   # stands in for the shared watch
  home = binding.EssentialsHome(software, lambda: watch)
  home.last_refresh = time.monotonic()
  home._next_summary = float("inf")
  target = InstallTarget("development", "a" * 40, "b" * 40)
  home._software.state = SoftwareState(home=HomeSoftware(installed="7.0.0", version="7.0.1", target=target))
  monkeypatch.setattr(home._software, "poll", lambda: home._software.state)
  drawn = {}
  for name in ("_content", "_alerts_view", "_update_view"):
    monkeypatch.setattr(getattr(home, name), "_render", lambda rect, name=name: drawn.update({name: rect}))
  try:
    yield SimpleNamespace(home=home, layout=layout, drawn=drawn, headers=headers, target=target, software=software, state=state)
  finally:
    home._software.close()


@pytest.mark.parametrize("rect", [(0, 0, 2160, 1080), (554, 30, 1606, 1050), (400, 10, 1200, 800)])
def test_home_cards_reclaim_header_and_gap_with_sidebar_offsets(home_layout: SimpleNamespace, rect: tuple[int, ...]) -> None:
  rect = rl.Rectangle(*rect)
  home_layout.home.render(rect)
  assert not home_layout.headers
  actual = home_layout.drawn["_content"]
  expected = home_content_rect(rect)
  assert (actual.x, actual.y, actual.width, actual.height) == (expected.x, expected.y, expected.width, expected.height)
  assert actual.y == rect.y + T.px(18)
  assert actual.height == rect.height - T.px(18) * 2


def test_invisible_header_buttons_do_not_intercept_home_card_taps(home_layout: SimpleNamespace) -> None:
  home = home_layout.home
  home.alert_count = 1
  home.render(rl.Rectangle(554, 0, 1606, 1080))
  for rect in (home.update_notif_rect, home.alert_notif_rect):
    home._handle_mouse_release(MousePos(rect.x + rect.width / 2, rect.y + rect.height / 2))
    assert home.current_state == home_layout.layout.HomeLayoutState.HOME


@pytest.mark.parametrize("state", ["ALERTS", "UPDATE"])
def test_home_card_opens_detail_and_back_returns(home_layout: SimpleNamespace, state: str) -> None:
  home = home_layout.home
  home.alert_count = 1
  rect = rl.Rectangle(554, 0, 1606, 1080)
  home.render(rect)
  view = home._alerts_view if state == "ALERTS" else home._update_view
  content = home._content
  button = content._hero if state == "ALERTS" else content._update._button
  assert button._click_callback is not None
  button._click_callback()
  assert home.current_state.name == state
  home.render(rect)
  assert not home_layout.headers
  assert home_layout.drawn["_alerts_view" if state == "ALERTS" else "_update_view"].y == T.px(18)
  view._header._back._click_callback()
  assert home.current_state.name == "HOME"


def test_upstream_home_keeps_header_geometry_and_notification_buttons(home_layout: SimpleNamespace,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("TANDEM_HOME", "0")
  home = screens.home()
  layout = home_layout.layout
  assert type(home) is layout.HomeLayout
  home.last_refresh = time.monotonic()
  home.update_available = True
  home.render(rl.Rectangle(554, 0, 1606, 1080))
  assert home_layout.headers == [layout.HomeLayoutState.HOME]
  assert home.header_rect.height == layout.HEADER_HEIGHT
  assert home.content_rect.y == layout.CONTENT_MARGIN + layout.HEADER_HEIGHT + layout.SPACING
  button = home.update_notif_rect
  home._handle_mouse_release(MousePos(button.x + 10, button.y + 10))
  assert home.current_state == layout.HomeLayoutState.UPDATE
  monkeypatch.setenv("TANDEM_HOME", "1")
  monkeypatch.setenv("STARPILOT_UI", "upstream")
  assert type(screens.home()) is layout.HomeLayout


def test_refresh_returning_home_reclaims_header_in_the_same_frame(home_layout: SimpleNamespace) -> None:
  home = home_layout.home
  home._open_notes()
  home._software.state = SoftwareState(home=HomeSoftware(installed="7.0.0"))
  home.render(rl.Rectangle(554, 30, 1606, 1050))
  assert home.current_state.name == "HOME"
  assert not home_layout.headers
  assert home_layout.drawn["_content"].y == 30 + T.px(18)


def test_native_alert_action_requires_parked_writable_ui(home_layout: SimpleNamespace) -> None:
  home = home_layout.home
  alert = home.offroad_alert
  alert.sorted_alerts = [SimpleNamespace(key="Offroad_ConnectivityNeeded", text="Connect", severity=2, visible=True)]
  alert.snooze_btn.is_visible = True
  home._refresh()
  assert home.current_state.name == "ALERTS"
  assert readiness(home._state())[1] == "Check 1 alert"
  assert home._alert_action()[1] is alert.snooze_btn._click_callback
  home_layout.state.projection_read_only = True
  assert home._alert_action() is None


def test_update_copy_follows_the_software_owner() -> None:
  status = {"installed": {"version": "7.0.0", "commit": "a" * 40, "branch": "development"},
            "updater": {"state": "idle", "targetBranch": "development", "lastCheckedAt": "2026-11-16T12:00:00Z",
                        "finalizedUpdateReady": False, "targetChangeFound": False, "failedCount": 0}}
  assert software_line(project_software(status, {})) == "7.0.0"
  assert software_line(project_software(status, {"updaterAvailable": True})) == "Up to date · 7.0.0"
  status["updater"]["finalizedUpdateReady"] = True
  assert not project_software(status, {"updaterAvailable": True}).ready
  available = {"canInstall": True, "preparedCommit": "b" * 40, "selectedTarget": "development"}
  manual = project_software(status, available, "7.0.1 / development / bbbbbbb / Nov 16", b"<ul><li>Fix</li></ul>")
  assert manual.ready and not manual.scheduled and manual.notes == "• Fix" and manual.version == "7.0.1"
  assert software_line(manual) == "Restart to install"
  assert project_software(status, dict(available, nextRestartAt="2026-11-17T00:00:00Z")).scheduled


def test_install_rechecks_park_and_the_revision_in_view() -> None:
  owner = Mock()
  owner.status.snapshot.return_value = {"installed": {"version": "7.0.0"}, "updater": {}}
  owner.snapshot.return_value = {"canInstall": False}
  can_mutate = Mock(return_value=True)
  watch = SoftwareWatch(lambda: owner, lambda _key: None, can_mutate, Mock())
  target = InstallTarget("development", "a" * 40, "b" * 40)
  watch.state = SoftwareState(home=HomeSoftware(target=target))
  try:
    assert not watch.install(InstallTarget("development", "a" * 40, "c" * 40))
    can_mutate.return_value = False
    assert not watch.install(target)
    can_mutate.return_value = True
    assert watch.install(target)
    assert not watch.install(target)
    assert watch._pending is not None
    watch._pending.result(timeout=3)
    owner.action.assert_called_once_with("install", {"action": "install", "branch": "development",
                                                     "expectedCommit": "a" * 40, "selectedCommit": "b" * 40},
                                         authorized=can_mutate)
  finally:
    watch.close()


def test_replacing_details_releases_the_previous_scroll_panel(home_layout: SimpleNamespace) -> None:
  home = home_layout.home
  view = home._alerts_view
  previous = view._cards()
  home.offroad_alert.sorted_alerts = [SimpleNamespace(key="Offroad_ConnectivityNeeded", text="Connect", severity=2, visible=True)]
  assert view._cards() is not previous
  assert previous not in view._children

  update = home._update_view
  previous = update._panel()
  home._software.state = SoftwareState(home=HomeSoftware(notes="New release notes"))
  assert update._panel() is not previous
  assert previous not in update._children
