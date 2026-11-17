"""Release's settings window (settings/window.py there): four tabs, each with its own page stack, a back or close button,
and dialogs over the page. MainLayout shows it in place of openpilot's settings (screens.settings); essentials.py
supplies each tab's first page from StarPilot 7.
"""
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
# openpilot's PanelType names (MainLayout opens settings at one) to the tab, and section of the Device tab, holding it.
PANEL_TABS = {"DEVICE": Tab.DEVICE, "NETWORK": Tab.CONNECTIONS, "TOGGLES": Tab.DRIVING, "SOFTWARE": Tab.SOFTWARE,
              "FIREHOSE": Tab.DEVICE, "DEVELOPER": Tab.DEVICE}


class SettingsWindow(Widget):
  """Each bottom tab keeps its own page stack and opens dialogs over the current page."""

  def __init__(self, roots: Mapping[Tab, Callable[[], Widget]], on_close: Callable[[], None] = lambda: None, initial: Tab = Tab.DRIVING,
               sections: Mapping[str, int] | None = None,
               auxiliary: Mapping[str, Callable[[], Widget]] | None = None):
    """Makes the window.

    Args:
      roots: Each tab's first page.
      on_close: Closes settings (MainLayout sets it through set_callbacks).
      initial: The tab shown first.
      sections: openpilot PanelType names that open a section of their tab's first page, to the section's index.
      auxiliary: Panels opened directly by native setup, outside the section rail.
    """
    super().__init__()
    self._roots = roots
    self._on_close = on_close
    self._sections = dict(sections or {})
    self._auxiliary = dict(auxiliary or {})
    self._stacks: dict[Tab, list[Widget]] = {}
    self._tab = initial
    self._shown = False
    self._overlay: Widget | None = None
    self._nav = self._child(BottomNav(TABS, lambda: self._tab, self.select_tab, on_leading=self.back,
                                      leading=lambda: "back" if self.can_go_back() else "close"))

  # openpilot's SettingsLayout interface, which MainLayout uses

  def set_callbacks(self, on_close: Callable[[], None]) -> None:
    self._on_close = on_close

  def set_current_panel(self, panel_type: object) -> None:
    """Open settings at an openpilot PanelType, starting that tab from its first page."""
    name = getattr(panel_type, "name", str(panel_type))
    factory = self._auxiliary.get(name)
    self.open_at(PANEL_TABS.get(name, Tab.DRIVING), 0 if factory else self._sections.get(name))
    if factory is not None:
      self.push(factory())

  def open_at(self, tab: Tab, section: int | None = None) -> None:
    """Open a tab from its first page, at one of its sections."""
    from openpilot.selfdrive.ui.tandem.settings.pages import SectionPage
    self.dismiss()
    stack = self._stacks.get(tab)
    while stack is not None and len(stack) > 1:
      page = stack.pop()
      if self._shown and tab == self._tab:
        page.hide_event()
        if len(stack) == 1:
          stack[0].show_event()
    self.select_tab(tab)
    if section is not None and isinstance(self.top, SectionPage):
      self.top.select(section)

  @property
  def shown(self) -> bool:
    """Whether the window is open (StarPilot changes driver preferences only while its settings are shown)."""
    return self._shown

  def notice(self, title: str, message: str) -> None:
    """A message from StarPilot, in our dialog, where its own screen showed an alert box."""
    self.present(Dialog(title, message, "OK", lambda _: self.dismiss(), cancel_label=None))

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
