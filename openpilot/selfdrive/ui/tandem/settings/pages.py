"""Settings pages with a section sidebar or a full-width body."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from functools import partial
from openpilot.starpilot.ui.raylib import rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve
from openpilot.selfdrive.ui.tandem.chrome import PageHeader, Sidebar, SidebarItem
from openpilot.selfdrive.ui.tandem.controls import Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row


def can_go_back(page: Widget) -> bool:
  """True when the page has its own level to step back from (e.g. a sub-page inside a hosted panel)."""
  check = getattr(page, "can_go_back", None)
  return bool(check and check())


def go_back(page: Widget) -> None:
  go = getattr(page, "go_back", None)
  if callable(go):
    go()


def body_rect(rect: rl.Rectangle) -> rl.Rectangle:
  return inset(rect, left=T.PAGE_INSET, right=T.PAGE_INSET, top=T.px(18), bottom=T.px(14))


@dataclass
class Section:
  """One entry in a section page's sidebar and the page it opens."""
  label: str
  page: Callable[[], Widget]
  value: Bindable[str] | None = None
  visible: Bindable[bool] = True
  value_tone: Tone = Tone.NEUTRAL
  dot: Bindable[bool] = False


class SectionPage(Component):
  """A sidebar of sections; the chosen section fills the rest. Sections are built when first chosen."""
  grow_touch_target = False

  def __init__(self, caption: str, sections: list[Section], selected: int = 0, tone: Tone = Tone.ACCENT,
               footer: Sequence[Widget] | None = None):
    """Makes a section page.

    Args:
      caption: The sidebar's caption.
      sections: The sidebar's entries.
      selected: The entry shown first.
      tone: Colors the caption and selection (WARNING for Tuner Mode).
      footer: Widgets at the bottom of the sidebar.
    """
    super().__init__()
    self._sections = sections
    self._pages: dict[int, Widget] = {}
    self._selected = selected
    self._shown = False
    items = [SidebarItem(s.label, on_select=partial(self.select, i), value=s.value, value_tone=s.value_tone,
                         visible=s.visible, dot=s.dot) for i, s in enumerate(sections)]
    self._sidebar = self._child(Sidebar(caption, items, selected=lambda: self._selected, tone=tone, footer=footer))

  @property
  def selected(self) -> int:
    return self._selected

  @property
  def current(self) -> Widget:
    if self._selected not in self._pages:
      self._pages[self._selected] = self._sections[self._selected].page()
    return self._pages[self._selected]

  def select(self, index: int) -> None:
    if index == self._selected or not 0 <= index < len(self._sections) or not resolve(self._sections[index].visible):
      return
    if self._shown:
      self.current.hide_event()
    self._selected = index
    if self._shown:
      self.current.show_event()

  def can_go_back(self) -> bool:
    return can_go_back(self.current)

  def go_back(self) -> None:
    go_back(self.current)

  def show_event(self) -> None:
    super().show_event()
    self._shown = True
    self.current.show_event()

  def hide_event(self) -> None:
    super().hide_event()
    self._shown = False
    self.current.hide_event()

  def _update_state(self) -> None:
    # A section can hide (e.g. Tuner sections when Tuner Mode turns off); fall back to the first one.
    if not resolve(self._sections[self._selected].visible):
      self.select(0)

  def _render(self, rect: rl.Rectangle) -> None:
    side, content = row(body_rect(rect), [T.SIDEBAR_WIDTH, FILL], T.PANEL_GAP)
    self._sidebar.render(inset(side, top=T.px(8)))
    self.current.render(content)


class PanelPage(Component):
  """One panel filling the page, for screens without a sidebar (e.g. Alerts)."""
  grow_touch_target = False

  def __init__(self, panel: Widget):
    super().__init__()
    self._panel = self._child(panel)

  def _render(self, rect: rl.Rectangle) -> None:
    self._panel.render(body_rect(rect))


class TitledPage(Component):
  """A page title with its subtitle beside it, then a body filling the rest (usually Columns), as on Alerts."""
  grow_touch_target = False

  def __init__(self, title: str, subtitle: str, body: Widget):
    super().__init__()
    self._header = self._child(PageHeader(title, subtitle))
    self._body = self._child(body)

  def _render(self, rect: rl.Rectangle) -> None:
    body = inset(body_rect(rect), top=T.px(2))
    header, content = column(body, [self._header.preferred_height(body.width), FILL], T.px(14))
    self._header.render(header)
    self._body.render(content)
