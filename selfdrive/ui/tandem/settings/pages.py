"""Page shapes the settings window is built from: a hub of tiles, and a sidebar of sections."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.chrome import HubGrid, HubTile, PageHeader, Sidebar, SidebarItem
from openpilot.selfdrive.ui.tandem.controls import Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, column, inset, row


def can_go_back(page: Widget) -> bool:
  """True when the page has its own level to step back from (e.g. a sub-page inside a hosted panel)."""
  check = getattr(page, "can_go_back", None)
  return bool(check and check())


def go_back(page: Widget) -> None:
  page.go_back()  # type: ignore[attr-defined]


def body_rect(rect: rl.Rectangle) -> rl.Rectangle:
  return inset(rect, left=T.PAGE_INSET, right=T.PAGE_INSET, top=T.px(18), bottom=T.px(14))


class HubPage(Component):
  """Title and subtitle, a grid of tiles, then an optional strip (e.g. the power-user switches)."""
  grow_touch_target = False

  def __init__(self, title: str, subtitle: str, tiles: list[HubTile], rows: list[int] | None = None, strip: Component | None = None,
               trailing: Widget | None = None):
    """trailing sits at the right of the title (the Search settings button)."""
    super().__init__()
    self._header = self._child(PageHeader(title, subtitle, trailing=trailing, size=T.font_px(30)))
    self._grid = self._child(HubGrid(tiles, rows=rows))
    self._strip = self._child(strip) if strip is not None else None

  def _render(self, rect: rl.Rectangle):
    body = inset(body_rect(rect), top=T.px(6))   # the hub's 24 px top padding, against 18 on other pages
    sizes = [self._header.preferred_height(body.width), self._grid.preferred_height(body.width)]
    if self._strip is not None:
      sizes.append(self._strip.preferred_height(body.width))
    header, grid, *rest = column(body, sizes, T.px(14))
    self._header.render(header)
    self._grid.render(grid)
    if self._strip is not None:
      self._strip.render(rest[0])


class Strip(Component):
  """A tinted bar: caption, a short line, and controls on the right."""
  grow_touch_target = False

  def __init__(self, caption: str, text: str, controls: list[Widget]):
    super().__init__()
    self._caption = caption
    self._text = text
    self._controls = [self._child(c) for c in controls]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(60)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_1, T.RADIUS_CARD)
    draw.stroke(rect, T.STRIP_EDGE, T.RADIUS_CARD)
    body = inset(rect, left=T.px(20), right=T.px(10), y=T.px(8))
    x = body.x + body.width
    for control in reversed(self._controls):
      w, h = size_of(control, body.width / 3)
      x -= w
      control.render(rl.Rectangle(x, body.y + (body.height - h) / 2, w, h))
      x -= T.px(12)
    w = draw.caption(body, self._caption, T.TEXT_MUTED)
    draw.text(rl.Rectangle(body.x + w + T.px(12), body.y, x - body.x - w - T.px(12), body.height), self._text, T.font_px(15), T.TEXT_TERTIARY)


@dataclass
class Section:
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
               footer: list[Widget] | None = None):
    """tone colors the caption and selection (WARNING for Tuner Mode); footer sits at the bottom of the sidebar."""
    super().__init__()
    self._sections = sections
    self._pages: dict[int, Widget] = {}
    self._selected = selected
    self._shown = False
    items = [SidebarItem(s.label, on_select=lambda i=i: self.select(i), value=s.value, value_tone=s.value_tone,
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
    if index == self._selected:
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

  def show_event(self):
    super().show_event()
    self._shown = True
    self.current.show_event()

  def hide_event(self):
    super().hide_event()
    self._shown = False
    self.current.hide_event()

  def _update_state(self):
    # A section can hide (e.g. Tuner sections when Tuner Mode turns off); fall back to the first one.
    if not resolve(self._sections[self._selected].visible):
      self.select(0)

  def _render(self, rect: rl.Rectangle):
    side, content = row(body_rect(rect), [T.SIDEBAR_WIDTH, FILL], T.PANEL_GAP)
    self._sidebar.render(inset(side, top=T.px(8)))
    self.current.render(content)


class PanelPage(Component):
  """One panel filling the page, for screens without a sidebar (e.g. Alerts)."""
  grow_touch_target = False

  def __init__(self, panel: Widget):
    super().__init__()
    self._panel = self._child(panel)

  def _render(self, rect: rl.Rectangle):
    self._panel.render(body_rect(rect))


class TitledPage(Component):
  """A page title with its subtitle beside it, then a body filling the rest (usually Columns), as on Alerts."""
  grow_touch_target = False

  def __init__(self, title: str, subtitle: str, body: Widget):
    super().__init__()
    self._header = self._child(PageHeader(title, subtitle))
    self._body = self._child(body)

  def _render(self, rect: rl.Rectangle):
    body = inset(body_rect(rect), top=T.px(2))
    header, content = column(body, [self._header.preferred_height(body.width), FILL], T.px(14))
    self._header.render(header)
    self._body.render(content)


class FillPage(Component):
  """A body filling the page, for column layouts without a title (e.g. Vehicle)."""
  grow_touch_target = False

  def __init__(self, body: Widget):
    super().__init__()
    self._body = self._child(body)

  def _render(self, rect: rl.Rectangle):
    self._body.render(inset(body_rect(rect), top=T.px(2)))
