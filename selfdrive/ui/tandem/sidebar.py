"""The sidebar beside home and the onroad view: Settings, then a status card (network, comma connect, temperature, vehicle, maps).

EssentialsSidebar subclasses upstream's Sidebar. Upstream still tracks the device state and owns the callbacks;
this redraws it in the Essentials style and adds a Maps row. Onroad, the bottom button saves a clip, as upstream's
flag button does, and the microphone indicator shows while cabin audio is being recorded.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_

WIDTH = T.px(288)       # the mock's sidebar, including its 18 px margin


class Health(Enum):
  GOOD = "good"
  WARN = "warn"
  BAD = "bad"
  OFF = "off"


DOT = {Health.GOOD: T.SUCCESS_BRIGHT, Health.WARN: T.WARNING, Health.BAD: T.DANGER, Health.OFF: T.TEXT_MUTED}


@dataclass
class Status:
  label: str
  value: str
  health: Health


@dataclass
class SidebarState:
  rows: list[Status] = field(default_factory=list)
  onroad: bool = False
  recording_audio: bool = False


def gear(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.icon(rect, "gear", color, T.px(26))


class SidebarView(Component):
  grow_touch_target = False

  def __init__(self, state: Callable[[], SidebarState], on_settings: Callable[[], None], on_clip: Callable[[], None],
               on_microphone: Callable[[], None]):
    super().__init__()
    self._state = state
    self._settings = self._child(Button(N_("Settings"), on_settings, ButtonStyle.NAV, glyph=gear, height=T.px(74), radius=T.RADIUS_CARD,
                                        font_size=T.font_px(19)))
    self._clip = self._child(Button(N_("Save a clip"), on_clip, ButtonStyle.SECONDARY, height=T.px(60)))
    self._clip.set_visible(lambda: self._state().onroad)
    self._mic = self._child(Button(N_("Recording audio"), on_microphone, ButtonStyle.DANGER_SOFT, height=T.px(44)))
    self._mic.set_visible(lambda: self._state().recording_audio)

  def _render(self, rect: rl.Rectangle):
    state = self._state()
    draw.fill(rect, T.BG)
    body = inset(rect, left=T.px(18), right=T.px(10), y=T.px(18))
    top, card = column(body, [T.px(74), FILL], T.px(12))
    self._settings.render(top)

    draw.fill(card, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(card, x=T.px(18), y=T.px(16))
    y = inner.y
    row_h = T.px(33)
    for status in state.rows:
      line = rl.Rectangle(inner.x, y, inner.width, row_h)
      dot, text = row(line, [T.px(10), FILL], T.px(14))
      draw.fill(place(dot, T.px(10), T.px(10)), DOT[status.health], T.px(5))
      value_w = draw.text(text, status.value, T.font_px(15), T.TEXT_TERTIARY, h=Align.END)
      draw.text(inset(text, right=value_w + T.px(10)), status.label, T.font_px(16), T.TEXT, T.FONT_MEDIUM)
      y += row_h

    bottom = rl.Rectangle(inner.x, inner.y + inner.height - T.px(60), inner.width, T.px(60))
    if self._mic.is_visible:
      self._mic.render(rl.Rectangle(inner.x, y + T.px(10), inner.width, T.px(44)))
    if self._clip.is_visible:
      self._clip.render(bottom)


def connect_status(health: Health) -> Status:
  """comma connect: online, offline (no ping yet), or an error (no ping for 80 s), as upstream decides."""
  return Status(N_("comma connect"), {Health.GOOD: N_("Online"), Health.WARN: N_("Offline"), Health.BAD: N_("Error")}.get(health, N_("Offline")), health)


def network_status(kind: str, strength: int) -> Status:
  if kind in ("", "--"):
    return Status(N_("Network"), N_("Offline"), Health.OFF)
  return Status(N_("Network"), kind, Health.GOOD if strength >= 2 else Health.WARN)


def essentials_sidebar():
  """Upstream's Sidebar with the Essentials look. Imported only on the device."""
  from openpilot.selfdrive.ui.layouts.sidebar import Colors, Sidebar
  from openpilot.selfdrive.ui.ui_state import ui_state

  class EssentialsSidebar(Sidebar):
    def __init__(self):
      super().__init__()
      self._view = SidebarView(self._state, lambda: self._call(self._on_settings_click), lambda: self._call(self._on_flag_click),
                               lambda: self._call(self._open_settings_callback))
      self._maps = Status(N_("Maps"), N_("Checking"), Health.OFF)
      self._maps_checked = -1e9

    @staticmethod
    def _call(callback) -> None:
      if callback is not None:
        callback()

    def _health(self, color: rl.Color) -> Health:
      if color == Colors.DANGER:
        return Health.BAD
      return Health.WARN if color == Colors.WARNING else Health.GOOD

    def _maps_status(self) -> Status:
      import time
      now = time.monotonic()
      if now - self._maps_checked > 10:   # a param read, so not every frame
        from openpilot.starpilot.common.maps_download_progress import MAPS_STORAGE_CACHE_PARAM, load_maps_storage_cache
        self._maps_checked = now
        cache = load_maps_storage_cache(ui_state.ui_params.get(MAPS_STORAGE_CACHE_PARAM, encoding="utf-8") or "")
        if ui_state.params_memory.get_bool("DownloadMaps"):
          self._maps = Status(N_("Maps"), N_("Downloading"), Health.WARN)
        elif cache.maps_present:
          self._maps = Status(N_("Maps"), N_("Up to date"), Health.GOOD)
        else:
          self._maps = Status(N_("Maps"), N_("Not downloaded"), Health.OFF)
      return self._maps

    def _state(self) -> SidebarState:
      temp = self._temp_status
      temperature = {Health.GOOD: N_("Good"), Health.WARN: N_("Warm"), Health.BAD: N_("Hot")}[self._health(temp.color)]
      vehicle_ok = self._health(self._panda_status.color) == Health.GOOD
      return SidebarState(rows=[
        network_status(self._net_type, self._net_strength),
        connect_status(self._health(self._connect_status.color)),
        Status(N_("Temperature"), temperature, self._health(temp.color)),
        Status(N_("Vehicle"), N_("Connected") if vehicle_ok else N_("Not connected"), Health.GOOD if vehicle_ok else Health.BAD),
        self._maps_status(),
      ], onroad=bool(ui_state.started), recording_audio=bool(self._recording_audio))

    def _render(self, rect: rl.Rectangle):
      self._view.render(rect)

    def _handle_mouse_release(self, mouse_pos) -> None:
      pass   # the view's buttons handle their own taps

  return EssentialsSidebar()
