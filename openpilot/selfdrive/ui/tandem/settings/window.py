"""Settings navigation from release, with the screen owners supplied by each tab."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import IntEnum

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.chrome import BottomNav
from openpilot.selfdrive.ui.tandem.controls import Tone
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.layout import FILL, column
from openpilot.selfdrive.ui.tandem.overlays import Dialog
from openpilot.selfdrive.ui.tandem.settings.pages import can_go_back, go_back
from openpilot.starpilot.ui.raylib import rl
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.widgets import DialogResult, Widget


class Tab(IntEnum):
  """The settings tabs in release order."""

  DRIVING = 0
  DEVICE = 1
  CONNECTIONS = 2
  SOFTWARE = 3


TABS = [N_("Driving"), N_("Device"), N_("Connections"), N_("Software")]


class SettingsWindow(Widget):
  """Each bottom tab keeps its own page stack and opens dialogs over the current page."""

  def __init__(self, roots: Mapping[Tab, Callable[[], Widget]], on_close: Callable[[], None], initial: Tab = Tab.DRIVING):
    super().__init__()
    self._roots = roots
    self._on_close = on_close
    self._stacks: dict[Tab, list[Widget]] = {}
    self._tab = initial
    self._shown = False
    self._overlay: Widget | None = None
    self._nav = self._child(BottomNav(TABS, lambda: self._tab, self.select_tab, on_leading=self.back,
                                      leading=lambda: "back" if self.can_go_back() else "close"))

  def _stack(self) -> list[Widget]:
    if self._tab not in self._stacks:
      self._stacks[self._tab] = [self._roots[self._tab]()]
    return self._stacks[self._tab]

  @property
  def top(self) -> Widget:
    """The visible page in the selected tab."""
    return self._stack()[-1]

  def show_event(self) -> None:
    """Activate the selected page when the Settings window opens."""
    if not self._shown:
      super().show_event()
      self._shown = True
      self.top.show_event()

  def hide_event(self) -> None:
    """Deactivate the current page and dismiss pending dialogs."""
    if self._shown:
      self.dismiss()
      self.top.hide_event()
      self._shown = False
      super().hide_event()

  def select_tab(self, tab: int) -> None:
    """Switch to a tab, preserving the other tabs' positions."""
    self.dismiss()
    selected = Tab(tab)
    if selected == self._tab:
      return
    if self._shown:
      self.top.hide_event()
    self._tab = selected
    if self._shown:
      self.top.show_event()

  def push(self, page: Widget) -> None:
    """Open a page in the active tab."""
    if self._shown:
      self.top.hide_event()
    self._stack().append(page)
    if self._shown:
      self.top.show_event()

  def can_go_back(self) -> bool:
    """Whether the back button has a page or a nested section to return to."""
    return len(self._stack()) > 1 or can_go_back(self.top)

  def back(self) -> None:
    """Close the overlay, step back through the selected tab, or close Settings."""
    if self._overlay is not None:
      self.dismiss()
      return
    if can_go_back(self.top):
      go_back(self.top)
      return
    stack = self._stack()
    if len(stack) == 1:
      self._on_close()
      return
    current = stack.pop()
    if self._shown:
      current.hide_event()
      self.top.show_event()

  def present(self, overlay: Widget) -> None:
    """Open a modal above the page and navigation."""
    self.dismiss()
    self._overlay = overlay
    overlay.show_event()

  def dismiss(self, callback: Callable[[], None] | None = None) -> None:
    """Close the current modal."""
    if self._overlay is not None:
      overlay, self._overlay = self._overlay, None
      overlay.hide_event()
    if callback is not None:
      callback()

  def _render(self, rect: rl.Rectangle) -> None:
    body, nav = column(rect, [FILL, T.NAV_HEIGHT])
    draw.fill(body, T.BG)
    overlay = self._overlay
    events = gui_app.mouse_events
    held = list(events) if overlay is not None else None
    if held is not None:
      events.clear()
    try:
      self.top.render(body)
      self._nav.render(nav)
    finally:
      if held is not None:
        events[:] = held
    if overlay is not None:
      overlay.render(rect)


def confirm(window: SettingsWindow, title: str, message: str, label: str, action: Callable[[], None],
            danger: bool = True, icon: str = "trash") -> None:
  """Present the release confirmation dialog and run the action only after confirmation."""
  def done(result: DialogResult) -> None:
    window.dismiss()
    if result == DialogResult.CONFIRM:
      action()

  window.present(Dialog(title, message, label, done, tone=Tone.DANGER if danger else Tone.ACCENT,
                        glyph=lambda r, c, s: draw.icon(r, icon, c, s)))
