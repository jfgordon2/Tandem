"""Use the approved Home content inside openpilot's parked layout."""
from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.ui.layouts.home import HomeLayout, HomeLayoutState
from openpilot.selfdrive.ui.tandem.forecast import ForecastService, Outlook, outlook, wall_clock
from openpilot.selfdrive.ui.tandem.home import HomeContent, HomeState, home_content_rect
from openpilot.selfdrive.ui.tandem.home_alerts import AlertsView, HomeAlert, UpdateView
from openpilot.selfdrive.ui.tandem.home_software import HomeSoftwareWatch, InstallTarget, SoftwareOwner
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.prefs import WEATHER_HEADS_UP, celsius, prefs_dir
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.starpilot.gps.source import select_location
from openpilot.starpilot.lateral import lane_change_preferences
from openpilot.starpilot.navigation.position import LastPositionStore
from openpilot.starpilot.speed_limits import runtime_settings
from openpilot.starpilot.storage import starpilot_storage_root
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

  def __init__(self, on_software: Callable[[], None]):
    super().__init__()
    self._summary = ""
    self._next_summary = 0.0
    self._notes_target: InstallTarget | None = None
    self._software = HomeSoftwareWatch(self._new_software_owner, self.params.get, self._can_mutate, self._software_error)
    self._position: LastPositionStore | None = None
    self._forecast: ForecastService | None = None
    self._content = self._child(HomeContent(self._state, self._open_alerts, self._open_notes, on_software, self._outlook))
    self._alerts_view = self._child(AlertsView(self._home_alerts, self._back, self._alert_action))
    self._update_view = self._child(UpdateView(lambda: self._software.state.version, lambda: self._software.state.notes, self._back,
                                              self._restart, lambda: self._software.state.scheduled, self._can_restart))

  def _new_software_owner(self) -> SoftwareOwner:
    from openpilot.starpilot.galaxy.software_operations import SoftwareOperations
    return SoftwareOperations(params=self.params)

  @staticmethod
  def _software_error(error: Exception) -> None:
    cloudlog.warning("Tandem Home software status: %s", error)

  @staticmethod
  def _can_mutate() -> bool:
    return ui_state.is_offroad() and not ui_state.projection_read_only and ui_state.replay_clock is None

  def _state(self) -> HomeState:
    return HomeState(alerts=self.alert_count, ignition=ui_state.ignition, setup=self._summary, software=self._software.state)

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
    if (target := self._software.state.target) is not None:
      self._notes_target = target
      self._set_state(HomeLayoutState.UPDATE)

  def _can_restart(self) -> bool:
    return self._notes_target is not None and self._notes_target == self._software.state.target and self._software.can_restart()

  def _restart(self) -> None:
    if self._notes_target is not None and self._can_restart():
      self._software.restart(self._notes_target)

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

  def _position_now(self) -> tuple[float, float] | None:
    if (fix := select_location(ui_state.sm, time.monotonic_ns())) is not None:
      _, gps = fix
      return float(gps.latitude), float(gps.longitude)
    if self._position is None:
      self._position = LastPositionStore(starpilot_storage_root() / "navigation")
    position = self._position.read()
    return (position["latitude"], position["longitude"]) if position else None

  def _outlook(self) -> Outlook | None:
    if not WEATHER_HEADS_UP.get() or ui_state.projection_read_only or ui_state.replay_clock is not None:
      return None
    if self._forecast is None:
      self._forecast = ForecastService(prefs_dir() / ".tandem_forecast.json", self._position_now, WEATHER_HEADS_UP.get)
    self._forecast.tick()
    return outlook(self._forecast.forecast, wall_clock(), celsius(ui_state.is_metric))

  def _render(self, rect: rl.Rectangle) -> None:
    now = time.monotonic()
    if now - self.last_refresh >= 10.0:
      self._refresh()
      self.last_refresh = now
    software = self._software.poll()
    if self.current_state == HomeLayoutState.UPDATE and self._notes_target != software.target:
      self._back()
    content = home_content_rect(rect)
    if self.current_state == HomeLayoutState.ALERTS:
      self._alerts_view.render(content)
    elif self.current_state == HomeLayoutState.UPDATE:
      self._update_view.render(content)
    else:
      if now >= self._next_summary:
        self._summary = setup_line(self.params)
        self._next_summary = now + 5.0
      self._content.render(content)

  def _handle_mouse_release(self, mouse_pos: MousePos, /) -> None:
    # Stock header hit boxes do not apply to the Essentials content.
    Widget._handle_mouse_release(self, mouse_pos)
