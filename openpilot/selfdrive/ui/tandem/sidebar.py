"""The sidebar beside home and the onroad view: Settings, then a status card (network, comma connect, temperature, vehicle, maps).

EssentialsSidebar subclasses upstream's Sidebar. Upstream still tracks the device state and owns the callbacks;
this redraws it in the Essentials style and adds a Maps row, read from StarPilot's map manager. Onroad, the bottom button saves a clip, as upstream's
flag button does, and the microphone indicator shows while cabin audio is being recorded.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
import time

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.system.ui.lib.application import MousePos

WIDTH = T.px(288)       # the mock's sidebar, including its 18 px margin


class Health(Enum):
  """How a sidebar status row is colored."""
  GOOD = "good"
  WARN = "warn"
  BAD = "bad"
  OFF = "off"


DOT = {Health.GOOD: T.SUCCESS_BRIGHT, Health.WARN: T.WARNING, Health.BAD: T.DANGER, Health.OFF: T.TEXT_MUTED}


@dataclass
class Status:
  """One status row in the sidebar: a label, its value, and how healthy that is."""
  label: str
  value: str
  health: Health


@dataclass
class SidebarState:
  """Everything the sidebar draws, read from upstream's state each frame."""
  rows: list[Status] = field(default_factory=list)
  onroad: bool = False
  recording_audio: bool = False


def gear(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.icon(rect, "gear", color, size * 26 / 74 / 0.45)   # 26 px at the Settings button's 74


def zoom(state: SidebarState) -> float:
  """Larger text (onroad/size.py) applies while driving: the sidebar opened from the drive screen's menu grows its text at
  the same width (design/onroadlarge-menu.html); beside the parked home screen it stays as it is."""
  from openpilot.selfdrive.ui.tandem.onroad import size as Z
  return Z.zoom() if state.onroad else 1.0


class SidebarView(Component):
  """The onroad and offroad sidebar drawn as design/sidebar.html: status rows, settings, and the clip and microphone buttons."""
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
    self._zoom = 1.0

  def _resize(self, k: float) -> None:
    """Follow Text Size while driving: buttons keep their size from when they were made."""
    self._zoom = k
    px = lambda v: round(T.px(v) * k)  # noqa: E731
    self._settings.restyle(px(74), px(19), self._settings._padding, T.RADIUS_CARD)
    self._clip.restyle(px(60), px(17), self._clip._padding, self._clip._radius)
    self._mic.restyle(px(44), px(15), self._mic._padding, self._mic._radius)

  def _render(self, rect: rl.Rectangle) -> None:
    state = self._state()
    k = zoom(state)
    if k != self._zoom:
      self._resize(k)
    px = lambda v: round(T.px(v) * k)  # noqa: E731   text and rows grow; the sidebar's width and margins don't
    draw.fill(rect, T.BG)
    body = inset(rect, left=T.px(18), right=T.px(10), y=T.px(18))
    top, card = column(body, [px(74), FILL], T.px(12))
    self._settings.render(top)

    draw.fill(card, T.SURFACE_2, T.RADIUS_PANEL)
    inner = inset(card, x=T.px(18) if k == 1.0 else T.px(14), y=T.px(16))   # the larger mock's card is a little tighter
    y = inner.y
    row_h = px(33)
    for status in state.rows:
      line = rl.Rectangle(inner.x, y, inner.width, row_h)
      dot, text = row(line, [px(10), FILL], px(14) if k == 1.0 else T.px(14))
      draw.fill(place(dot, px(10), px(10)), DOT[status.health], px(5))
      value_w = draw.text(text, status.value, T.font_px(15) if k == 1.0 else T.font_px(19), T.TEXT_TERTIARY, h=Align.END)
      draw.text(inset(text, right=value_w + T.px(10)), status.label, px(16), T.TEXT, T.FONT_MEDIUM)
      y += row_h

    # Save a clip at the bottom while driving, with Recording audio just above it (design/onroadmenu.html).
    bottom = rl.Rectangle(inner.x, inner.y + inner.height - px(60), inner.width, px(60))
    if self._mic.is_visible:
      above = bottom.y - T.px(10) - px(44) if self._clip.is_visible else y + T.px(10)
      self._mic.render(rl.Rectangle(inner.x, above, inner.width, px(44)))
    if self._clip.is_visible:
      self._clip.render(bottom)


def connect_status(health: Health) -> Status:
  """comma connect: online, offline (no ping yet), or an error (no ping for 80 s), as upstream decides."""
  return Status(N_("comma connect"), {Health.GOOD: N_("Online"), Health.WARN: N_("Offline"), Health.BAD: N_("Error")}.get(health, N_("Offline")), health)


def network_status(kind: str, strength: int) -> Status:
  if kind in ("", "--"):
    return Status(N_("Network"), N_("Offline"), Health.OFF)
  return Status(N_("Network"), kind, Health.GOOD if strength >= 2 else Health.WARN)


def _rgba(color: rl.Color) -> tuple[int, int, int, int]:
  return color.r, color.g, color.b, color.a


def health_of(color: rl.Color, danger: rl.Color, warning: rl.Color) -> Health:
  """How healthy upstream's status color says a row is. Raylib's colors compare by identity, so this compares channels."""
  if _rgba(color) == _rgba(danger):
    return Health.BAD
  return Health.WARN if _rgba(color) == _rgba(warning) else Health.GOOD


MAP_WORK = ("transferring", "validating", "selecting")   # the map manager's states while it downloads and installs


def maps_status(status: dict | None, last: Status) -> Status:
  """The Maps row from the map manager's status, or the last one shown while it can't be asked (it answers only parked).

  StarPilot 7 selects a map snapshot rather than tracking updates, so a selected map is "Ready", not "Up to date".
  """
  if not isinstance(status, dict) or status.get("state") == "unavailable":
    return last
  if status.get("state") in MAP_WORK:
    return Status(N_("Maps"), N_("Downloading"), Health.WARN)
  if status.get("selectedGeneration"):
    return Status(N_("Maps"), N_("Ready"), Health.GOOD)
  return Status(N_("Maps"), N_("Not downloaded"), Health.OFF)


def _ask_map_manager() -> dict | None:
  from openpilot.starpilot.maps.operation_owner import request_operation
  response = request_operation({"version": 1, "op": "status"}, timeout_s=0.75)
  if not isinstance(response, dict) or response.get("ok") is not True or not isinstance(response.get("result"), dict):
    return None
  return response["result"]


class MapsWatch:
  """Asks StarPilot's map manager for its status every REFRESH_S on a worker thread, so drawing never waits on its socket."""
  REFRESH_S = 10.0

  def __init__(self, ask: Callable[[], dict | None] = _ask_map_manager, clock: Callable[[], float] = time.monotonic):
    self._ask = ask
    self._clock = clock
    self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-maps")
    self._pending: Future[dict | None] | None = None
    self._next = 0.0
    self.status = Status(N_("Maps"), N_("Checking"), Health.OFF)

  def poll(self) -> Status:
    """The row to draw now; starts a new question when the last answer is old enough."""
    if self._pending is not None and self._pending.done():
      try:
        answer = self._pending.result()
      except (OSError, RuntimeError, ValueError):
        answer = None
      self.status = maps_status(answer, self.status)
      self._pending = None
    now = self._clock()
    if self._pending is None and now >= self._next:
      self._pending = self._worker.submit(self._ask)
      self._next = now + self.REFRESH_S
    return self.status

  def close(self) -> None:
    self._worker.shutdown(wait=False, cancel_futures=True)


def essentials_sidebar() -> Widget:
  """Upstream's Sidebar with the Essentials look. Imported only on the device."""
  from openpilot.selfdrive.ui.layouts.sidebar import Colors, Sidebar
  from openpilot.selfdrive.ui.ui_state import ui_state

  class EssentialsSidebar(Sidebar):
    def __init__(self) -> None:
      super().__init__()
      self._view = SidebarView(self._state, lambda: self._call(self._on_settings_click), lambda: self._call(self._on_flag_click),
                               lambda: self._call(self._open_settings_callback))
      self._maps = MapsWatch()

    @staticmethod
    def _call(callback: Callable[[], None] | None) -> None:
      if callback is not None:
        callback()

    def _health(self, color: rl.Color) -> Health:
      return health_of(color, Colors.DANGER, Colors.WARNING)

    def _state(self) -> SidebarState:
      temp = self._temp_status
      temperature = {Health.GOOD: N_("Good"), Health.WARN: N_("Warm"), Health.BAD: N_("Hot")}[self._health(temp.color)]
      vehicle_ok = self._health(self._panda_status.color) == Health.GOOD
      return SidebarState(rows=[
        network_status(self._net_type, self._net_strength),
        connect_status(self._health(self._connect_status.color)),
        Status(N_("Temperature"), temperature, self._health(temp.color)),
        Status(N_("Vehicle"), N_("Connected") if vehicle_ok else N_("Not connected"), Health.GOOD if vehicle_ok else Health.BAD),
        self._maps.poll(),
      ], onroad=bool(ui_state.started), recording_audio=bool(self._recording_audio))

    def _render(self, rect: rl.Rectangle) -> None:
      self._view.render(rect)

    def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
      pass   # the view's buttons handle their own taps

  return EssentialsSidebar()
