"""Use the approved Home content inside openpilot's parked layout."""
from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

from openpilot.selfdrive.ui.layouts.home import HomeLayout, HomeLayoutState
from openpilot.selfdrive.ui.tandem.forecast import ForecastService, Outlook, outlook, shared_service, wall_clock
from openpilot.selfdrive.ui.tandem.home import HomeContent, HomeState, home_content_rect
from openpilot.selfdrive.ui.tandem.home_alerts import AlertsView, HomeAlert, UpdateView
from openpilot.selfdrive.ui.tandem.software import InstallTarget, SoftwareWatch, shared_software
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.prefs import WEATHER_HEADS_UP, celsius
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.starpilot.lateral import lane_change_preferences
from openpilot.starpilot.speed_limits import runtime_settings
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.lib.application import MousePos
from openpilot.system.ui.widgets import Widget

STYLES = (N_("Sport"), N_("Standard"), N_("Relaxed"))


def setup_line(params: Any) -> str:
  """Summarize saved choices using Dom's typed Params and qualified settings readers."""
  personality = params.get("LongitudinalPersonality", return_default=True)
  style = t_("{} style", STYLES[personality]) if type(personality) is int and personality in range(len(STYLES)) else ""
  speed_limits = runtime_settings.read_params(params)
  limit = (N_("Matching speed limits") if speed_limits.enabled else
           N_("Showing speed limits") if speed_limits.display else N_("Speed limits off"))
  lanes = lane_change_preferences.read_saved(params)
  lane = ""
  if lanes.valid and lanes.readable and lanes.policy.enabled:
    lane = N_("Auto lane change") if lanes.policy.auto_lane_change else N_("Nudge to change lanes")
  if style and lane:
    return t_("{} style · {} · {}", STYLES[personality], limit, lane)
  return " · ".join(part for part in (style, limit, lane) if part)


class EssentialsHome(HomeLayout):
  """Retain native offroad alerts, onboarding callbacks, and the parked lifecycle."""

  def __init__(self, on_software: Callable[[], None] | None = None, software: Callable[[], SoftwareWatch] = shared_software):
    """Makes Home.

    Args:
      on_software: Opens the Software tab; by default through MainLayout's settings callback, as on release.
      software: The software watch Home shares with the Software tab.
    """
    super().__init__()
    self._summary = ""
    self._next_summary = 0.0
    self._setup_checked = False   # first-run setup (setup.py), once onboarding has closed
    self._notes_target: InstallTarget | None = None
    self._software = software()   # the same watch as the Software tab
    self._forecast: ForecastService | None = None
    self._content = self._child(HomeContent(self._state, self._open_alerts, self._open_notes, on_software or self._open_software,
                                            self._outlook, self._open_where_to))
    self._alerts_view = self._child(AlertsView(self._home_alerts, self._back, self._alert_action))
    self._update_view = self._child(UpdateView(lambda: self._software.state.home.version, lambda: self._software.state.home.notes, self._back,
                                              self._restart, lambda: self._software.state.home.scheduled, self._can_restart))

  @staticmethod
  def _can_mutate() -> bool:
    return ui_state.is_offroad() and not ui_state.projection_read_only and ui_state.replay_clock is None

  def _open_where_to(self) -> None:
    """Where to? (destinations.py) over Home, on StarPilot 7's navigation."""
    from openpilot.system.ui.lib.application import gui_app
    from openpilot.selfdrive.ui.tandem.destinations import destinations_screen
    gui_app.push_widget(destinations_screen(gui_app.pop_widget))

  def _open_software(self) -> None:
    """Settings at its Software tab: MainLayout opens settings as Home's settings button does, then the tab moves."""
    from openpilot.selfdrive.ui.tandem.screens import show_settings_tab
    from openpilot.selfdrive.ui.tandem.settings.window import Tab
    callback = self.settings_callback
    if callback is not None:
      callback()
      show_settings_tab(Tab.SOFTWARE)

  def _state(self) -> HomeState:
    return HomeState(alerts=self.alert_count, ignition=ui_state.ignition, setup=self._summary, software=self._software.state.home)

  def _home_alerts(self) -> list[HomeAlert]:
    return [HomeAlert(item.key, item.text, item.severity > 0) for item in self.offroad_alert.sorted_alerts if item.visible]

  def _alert_action(self) -> tuple[str, Callable[[], None]] | None:
    if self._can_mutate():
      for label, button in ((N_("Acknowledge excessive actuation"), self.offroad_alert.excessive_actuation_btn),
                            (N_("Snooze update"), self.offroad_alert.snooze_btn)):
        if button.is_visible and (callback := button._click_callback) is not None:
          return label, callback
    return None

  def _open_alerts(self) -> None:
    if self.alert_count:
      self._set_state(HomeLayoutState.ALERTS)

  def _open_notes(self) -> None:
    if (target := self._software.state.home.target) is not None:
      self._notes_target = target
      self._set_state(HomeLayoutState.UPDATE)

  def _can_restart(self) -> bool:
    return self._software.can_install(self._notes_target)

  def _restart(self) -> None:
    if self._notes_target is not None and self._can_restart():
      self._software.install(self._notes_target)

  def _back(self) -> None:
    self._notes_target = None
    self._set_state(HomeLayoutState.HOME)

  def _refresh(self) -> None:
    # The native offroad alert widget owns the list, severity and footer callbacks.
    self.alert_count = self.offroad_alert.refresh()
    if self.alert_count and not self._prev_alerts_present:
      self._open_alerts()
    elif not self.alert_count and self.current_state == HomeLayoutState.ALERTS:
      self._back()
    self._prev_alerts_present = self.alert_count > 0

  def _outlook(self) -> Outlook | None:
    if not WEATHER_HEADS_UP.get() or ui_state.projection_read_only or ui_state.replay_clock is not None:
      return None
    if self._forecast is None:
      self._forecast = shared_service()   # the drive screen's Weather heads-up reads the same forecast
    self._forecast.tick()
    return outlook(self._forecast.forecast, wall_clock(), celsius(ui_state.is_metric))

  def _render(self, rect: rl.Rectangle) -> None:
    now = time.monotonic()
    if now - self.last_refresh >= 10.0:
      self._refresh()
      self.last_refresh = now
    software = self._software.poll().home
    if self.current_state == HomeLayoutState.UPDATE and self._notes_target != software.target:
      self._back()
    content = home_content_rect(rect)
    if self.current_state == HomeLayoutState.ALERTS:
      self._alerts_view.render(content)
    elif self.current_state == HomeLayoutState.UPDATE:
      self._update_view.render(content)
    else:
      if not self._setup_checked:
        from openpilot.selfdrive.ui.tandem.setup import maybe_show_setup
        self._setup_checked = maybe_show_setup()
      if now >= self._next_summary:
        self._summary = setup_line(self.params)
        self._next_summary = now + 5.0
      self._content.render(content)

  def _handle_mouse_release(self, mouse_pos: MousePos, /) -> None:
    # Stock header hit boxes do not apply to the Essentials content.
    Widget._handle_mouse_release(self, mouse_pos)
