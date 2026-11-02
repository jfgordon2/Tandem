"""The parked home screen: readiness and the current setup, Where to?, and update status.

EssentialsHome subclasses upstream's HomeLayout and replaces its home content, reclaiming the legacy header
space. The offroad alerts and update screen retain upstream's header and navigation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row


@dataclass
class HomeState:
  alerts: int = 0
  ignition: bool = False
  setup: str = ""              # "Standard style · Matching speed limits · Auto lane change"
  update_ready: bool = False
  version: str = ""            # the short version ("6.7.9"), see short_version


def setup_line(speed) -> str:
  """e.g. "Standard style · Matching speed limits · Auto lane change"."""
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import STYLES
  lanes = "Auto lane change" if speed.lane_changes else "Nudge to change lanes"
  return f"{STYLES[speed.style]} style · {speed.speed_limit_summary()} · {lanes}"


def readiness(state: HomeState) -> tuple[str, str, rl.Color]:
  """Caption, headline and caption color for the hero card."""
  if state.alerts:
    return "NEEDS ATTENTION", f"Check {state.alerts} alert{'s' if state.alerts != 1 else ''}", T.WARNING
  return "READY", "Press cruise to engage" if state.ignition else "Start the car to drive", T.SUCCESS_TEXT


class Hero(Component):
  """Readiness and the current setup; with a forecast (forecast.outlook), the next 12 hours along the bottom
  (design/homeweather.html)."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], HomeState], on_alerts: Callable[[], None], forecast: Callable[[], object] = lambda: None):
    super().__init__()
    self._state = state
    self._forecast = forecast
    self.set_click_callback(lambda: on_alerts() if self._state().alerts else None)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    caption, headline, ink = readiness(self._state())
    outlook = self._forecast()
    body = inset(rect, x=T.px(28))
    lines = [draw.line_height(T.font_px(15)), draw.line_height(T.font_px(38)), draw.line_height(T.font_px(18))]
    if outlook is not None:
      body = inset(rect, left=T.px(28), right=T.px(24), top=T.px(28), bottom=T.px(20))
      top, strip = column(body, [sum(lines) + T.px(20), FILL])
      self._render_outlook(strip, outlook)
      body = top
    cap, title, setup = column(place(body, body.width, sum(lines) + T.px(20)), lines, T.px(10))
    # The mock's status label is a size up from other captions.
    draw.text(cap, caption.upper(), T.font_px(15), ink, T.FONT_BOLD, tracking=T.CAPTION_TRACKING)
    draw.text(title, headline, T.font_px(38), T.TEXT, T.FONT_EXTRABOLD)
    draw.text(setup, self._state().setup, T.font_px(18), T.TEXT_TERTIARY)

  @staticmethod
  def _render_outlook(rect: rl.Rectangle, outlook) -> None:
    """The line that matters, when it was updated, then a tile an hour; hours with rain or snow tinted as the chips are."""
    t_size, temp_size, glyph_size = T.font_px(15), T.font_px(21), T.px(26)   # read at a glance from the driver's seat
    tile_h = T.px(10) * 2 + draw.line_height(t_size) + T.px(4) + glyph_size + T.px(4) + draw.line_height(temp_size)
    head_h = T.px(24)
    block = place(rect, rect.width, head_h + T.px(12) + tile_h, v=Align.END)
    head, _, tiles = column(block, [head_h, T.px(12), tile_h])
    ink = T.ACCENT_TEXT if outlook.hazard else T.TEXT_TERTIARY
    icon, words = row(head, [T.px(22), FILL], T.px(10))
    draw.icon(icon, outlook.icon, ink, T.px(22))
    draw.text(words, outlook.summary, T.font_px(18), T._hex("DCEBFF") if outlook.hazard else T.TEXT, T.FONT_BOLD)
    draw.text(head, f"Forecast · updated {outlook.updated}", T.font_px(13), T.TEXT_MUTED, T.FONT, Align.END)
    for tile, cell in zip(outlook.tiles, row(tiles, [FILL] * len(outlook.tiles), T.px(6)), strict=True):
      draw.fill(cell, T.ACCENT_SURFACE if tile.hazard else T._hex("1E2227"), T.px(14))
      inner = inset(cell, y=T.px(10))
      when, _, glyph, _, temp = column(inner, [draw.line_height(t_size), T.px(4), glyph_size, T.px(4), draw.line_height(temp_size)])
      draw.text(when, tile.time, t_size, T._hex("DCEBFF") if tile.hazard else T.TEXT_TERTIARY,
                T.FONT_BOLD if tile.hazard else T.FONT_MEDIUM, Align.CENTER)
      draw.icon(glyph, tile.icon, T.ACCENT_TEXT if tile.hazard else T.TEXT_SECONDARY, glyph_size)
      draw.text(temp, f"{tile.temp}°", temp_size, T.TEXT, T.FONT_BOLD, Align.CENTER)


def short_version(description) -> str:
  """The version number from UpdaterCurrentDescription ("6.7.9 / branch / commit / date"): the card has room for it alone."""
  text = description.decode(errors="ignore") if isinstance(description, bytes) else str(description or "")
  return text.split(" / ")[0].strip()


class Card(Component):
  """An icon well, a title and a line; an optional button on the right. The whole card is tappable."""
  grow_touch_target = False

  def __init__(self, glyph_name: str, title: Callable[[], str], line: Callable[[], str], on_click: Callable[[], None] | None,
               button: Button | None = None):
    super().__init__()
    self._glyph = glyph_name
    self._title = title
    self._line = line
    self._button = self._child(button) if button is not None else None
    self.set_click_callback(on_click)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_2, T.RADIUS_PANEL)
    if self.is_pressed:
      draw.pressed(rect, T.RADIUS_PANEL)
    body = inset(rect, x=T.px(20))
    well = place(body, T.ICON_WELL, T.ICON_WELL, Align.START)
    draw.fill(well, T.ACCENT_SURFACE, T.px(16))
    draw.icon(well, self._glyph, T.ACCENT_TEXT, T.px(26))
    body = inset(body, left=T.ICON_WELL + T.px(18))
    if self._button is not None:
      w, h = self._button.preferred_size(body.width / 3)
      self._button.render(place(body, w, h, Align.END))
      body = inset(body, right=w + T.px(14))
    # The line wraps to two lines, as in the mock ("Installs when you turn off / the car").
    line_h = draw.paragraph_height(self._line(), T.font_px(15), T.FONT, body.width, 1.0)
    lines = [draw.line_height(T.font_px(22)), min(line_h, draw.line_height(T.font_px(15)) * 2)]
    title, line = column(place(body, body.width, sum(lines) + T.px(4)), lines, T.px(4))
    draw.text(title, self._title(), T.font_px(22), T.TEXT, T.FONT_BOLD)
    draw.paragraph(line, self._line(), T.font_px(15), T.TEXT_TERTIARY, spacing=1.0, max_lines=2)


class HomeContent(Component):
  """The hero card above, Where to? and the update card below."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], HomeState], on_alerts: Callable[[], None], on_where_to: Callable[[], None],
               on_notes: Callable[[], None], on_software: Callable[[], None] = lambda: None, forecast: Callable[[], object] = lambda: None):
    """The update card opens the release notes when an update is ready, else Settings › Software (on_software)."""
    super().__init__()
    self._state = state
    self._hero = self._child(Hero(state, on_alerts, forecast))
    self._where = self._child(Card("navigate", lambda: "Where to?", lambda: "Home · Work · Recent", on_where_to))
    notes = Button("Notes", on_notes)
    notes.set_visible(lambda: state().update_ready)
    self._update = self._child(Card("download", lambda: "Update ready" if state().update_ready else "Software",
                                    lambda: "Installs when you turn off the car" if state().update_ready else
                                    (f"Up to date · {state().version}" if state().version else "Up to date"),
                                    lambda: on_notes() if state().update_ready else on_software(), notes))

  def _render(self, rect: rl.Rectangle):
    top, bottom = column(rect, [FILL, T.px(100)], T.px(14))
    self._hero.render(top)
    left, right = row(bottom, [FILL, FILL], T.px(14))
    self._where.render(left)
    self._update.render(right)


def essentials_home():
  """Upstream's HomeLayout with the Essentials home content. Imported only on the device."""
  from openpilot.selfdrive.ui.layouts.home import HomeLayout, HomeLayoutState
  from openpilot.selfdrive.ui.ui_state import ui_state
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.settings.speed_steering import SpeedSteering
  from openpilot.selfdrive.ui.tandem.settings.software_tab import notes_text
  from openpilot.selfdrive.ui.tandem.home_alerts import AlertsView, HomeAlert, UpdateView

  class EssentialsHome(HomeLayout):
    def __init__(self):
      super().__init__()
      self._speed = SpeedSteering(SettingsStore())
      self._setup_checked = False
      self._content = HomeContent(self._state, lambda: self._set_state(HomeLayoutState.ALERTS), self._where_to,
                                  lambda: self._set_state(HomeLayoutState.UPDATE), self._open_software, self._outlook)
      home = lambda: self._set_state(HomeLayoutState.HOME)  # noqa: E731
      self._alerts_view = AlertsView(self._home_alerts, home, self._alert_action)
      self._update_view = UpdateView(self._new_version, lambda: notes_text(self.update_alert.release_notes), home,
                                     lambda: self.update_alert.reboot_btn._click_callback())

    def _open_software(self):
      """Settings at its Software tab: MainLayout opens settings as home's settings button does, then the tab moves."""
      from openpilot.selfdrive.ui.tandem.screens import show_settings_tab
      from openpilot.selfdrive.ui.tandem.settings.window import Tab
      if self.settings_callback is not None:
        self.settings_callback()
        show_settings_tab(Tab.SOFTWARE)

    def _show_header(self) -> bool:
      return False   # our alerts and update views carry their own back and title

    def _home_alerts(self) -> list[HomeAlert]:
      return [HomeAlert(a.key, a.text, a.severity > 0) for a in self.offroad_alert.sorted_alerts if a.visible]

    def _alert_action(self):
      """Upstream's one footer action, when it shows one."""
      alert = self.offroad_alert
      if alert.excessive_actuation_btn.is_visible:
        return "Acknowledge excessive actuation", alert.excessive_actuation_btn._click_callback
      if alert.snooze_btn.is_visible:
        return "Snooze update", alert.snooze_btn._click_callback
      return None

    def _new_version(self) -> str:
      description = ui_state.ui_params.get("UpdaterNewDescription") or ""
      return description.split(" / ")[0] or "A new version"

    def _render_alerts_view(self):
      self._alerts_view.render(self.content_rect)

    def _render_update_view(self):
      self._update_view.render(self.content_rect)

    def _state(self) -> HomeState:
      speed = self._speed
      return HomeState(alerts=self.alert_count, ignition=bool(ui_state.ignition), setup=setup_line(speed),
                       update_ready=self.update_available,
                       version=short_version(ui_state.ui_params.get("UpdaterCurrentDescription")))

    def _outlook(self):
      """The next 12 hours (forecast.py), sharing the drive screen's forecast; none while Weather heads-up is off."""
      from openpilot.selfdrive.ui.tandem.forecast import outlook, shared_service, wall_clock
      from openpilot.selfdrive.ui.tandem.prefs import WEATHER_HEADS_UP
      service = shared_service()
      service.tick()   # parked, it refreshes too (from the last GPS fix, once the car has had one since starting)
      if not WEATHER_HEADS_UP.get():
        return None
      from openpilot.selfdrive.ui.tandem.prefs import celsius
      return outlook(service.forecast, wall_clock(), celsius(bool(ui_state.is_metric)))   # General › Temperature

    def _render_home_content(self):
      if not self._setup_checked:   # first-run setup, as soon as onboarding has closed
        from openpilot.selfdrive.ui.tandem.setup import maybe_show_setup
        self._setup_checked = maybe_show_setup()
      self._content.render(self.content_rect)

    def _where_to(self) -> None:
      from openpilot.system.ui.lib.application import gui_app
      from openpilot.selfdrive.ui.tandem.destinations import destinations_screen
      gui_app.push_widget(destinations_screen(gui_app.pop_widget))

  return EssentialsHome()
