"""Page scaffolding: bottom nav, sidebar, headers, hub tiles, and SettingsPage which assembles a screen."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.system.ui.lib.application import MousePos
from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Glyph, Tone, back_glyph
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row


def close_glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.cross(rect, color, size)


class BottomNav(Component):
  """Back or close on the left, then equal tabs; the current tab is a filled pill."""
  grow_touch_target = False

  def __init__(self, tabs: list[str], selected: Bindable[int], on_select: Callable[[int], None],
               on_leading: Callable[[], None] | None = None, leading: Bindable[str] = "back"):
    """leading is "back" or "close"; pass a getter to switch as the user moves deeper."""
    super().__init__()
    self._tabs = tabs
    self._selected = selected
    self._on_select = on_select
    self._leading_kind = leading
    self._leading = self._child(Button(on_click=on_leading, style=ButtonStyle.NAV, height=T.NAV_BUTTON, width=T.NAV_BUTTON,
                                       radius=T.RADIUS_CARD, glyph=self._leading_glyph))
    self._pressed_tab: int | None = None

  def _leading_glyph(self, rect: rl.Rectangle, color: rl.Color, size: float) -> None:
    (back_glyph if resolve(self._leading_kind) == "back" else close_glyph)(rect, color, size)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.NAV_HEIGHT

  def tab_rects(self) -> list[rl.Rectangle]:
    body = inset(self._rect, x=T.px(16))
    _, tabs = row(place(body, body.width, T.NAV_BUTTON), [T.NAV_BUTTON, FILL], T.px(10))
    return row(tabs, [FILL] * len(self._tabs), T.px(6))

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    self._pressed_tab = next((i for i, r in enumerate(self.tab_rects()) if rl.check_collision_point_rec(mouse_pos, r)), None)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = next((i for i, r in enumerate(self.tab_rects()) if rl.check_collision_point_rec(mouse_pos, r)), None)
    if hit is not None and hit == self._pressed_tab and hit != resolve(self._selected):
      self._on_select(hit)
    self._pressed_tab = None

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.NAV_BAR)
    draw.hline(rect.x, rect.y, rect.width, T.NAV_BAR_EDGE)
    body = inset(rect, x=T.px(16))
    self._leading.render(place(body, T.NAV_BUTTON, T.NAV_BUTTON, Align.START))
    selected = resolve(self._selected)
    for i, (label, r) in enumerate(zip(self._tabs, self.tab_rects(), strict=True)):
      if i == selected:
        draw.fill(r, T.ACCENT, T.RADIUS_CARD)
      elif self.is_pressed and i == self._pressed_tab:
        draw.pressed(r, T.RADIUS_CARD)
      draw.text(r, label, T.SIZE_BODY, T.ACCENT_INK if i == selected else T.TEXT_SECONDARY,
                T.FONT_BOLD if i == selected else T.FONT_SEMIBOLD, Align.CENTER)


@dataclass
class SidebarItem:
  label: str
  on_select: Callable[[], None] | None = None
  value: Bindable[str] | None = None        # short state on the right, e.g. "Car", "Auto"
  value_tone: Tone = Tone.NEUTRAL           # WARNING for Tuner Mode's "1 changed"
  visible: Bindable[bool] = True
  dot: Bindable[bool] = False               # a red dot on the right: something new to look at (Device › RAM)


class Sidebar(Component):
  """Caption, then items; footer widgets sit at the bottom (e.g. "Advanced tuning", "Reset all")."""
  grow_touch_target = False

  def __init__(self, caption: str, items: list[SidebarItem], selected: Bindable[int], tone: Tone = Tone.ACCENT,
               footer: list[Widget] | None = None, width: float = T.SIDEBAR_WIDTH):
    super().__init__()
    self._caption = caption
    self._items = items
    self._selected = selected
    self._tone = tone
    self._footer = [self._child(w) for w in footer or []]
    self._width = width
    self._pressed_item: int | None = None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._width, self._rect.height

  def _visible(self) -> list[tuple[int, SidebarItem]]:
    return [(i, item) for i, item in enumerate(self._items) if resolve(item.visible)]

  def item_rects(self) -> list[tuple[int, rl.Rectangle]]:
    y = self._rect.y + T.px(8) + T.px(40)
    rects = []
    for i, _ in self._visible():
      rects.append((i, rl.Rectangle(self._rect.x, y, self._rect.width, T.SIDEBAR_ITEM_HEIGHT)))
      y += T.SIDEBAR_ITEM_HEIGHT + T.px(6)
    return rects

  def _hit(self, pos: MousePos) -> int | None:
    return next((i for i, r in self.item_rects() if rl.check_collision_point_rec(pos, r)), None)

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    self._pressed_item = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed_item and hit != resolve(self._selected) and self._items[hit].on_select:
      self._items[hit].on_select()
    self._pressed_item = None

  def _render(self, rect: rl.Rectangle):
    accent = self._tone == Tone.WARNING
    draw.caption(rl.Rectangle(rect.x + T.px(16), rect.y + T.px(8), rect.width, T.px(24)), self._caption,
                 T.WARNING if accent else T.ACCENT_TEXT)
    selected = resolve(self._selected)
    for i, r in self.item_rects():
      item = self._items[i]
      chosen = i == selected
      if chosen:
        draw.fill(r, T.WARNING_SURFACE if accent else T.ACCENT_SURFACE, T.RADIUS_ITEM)
      elif self.is_pressed and i == self._pressed_item:
        draw.pressed(r, T.RADIUS_ITEM)
      body = inset(r, x=T.px(16))
      if resolve(item.dot):
        draw.disc(rl.Vector2(body.x + body.width - T.px(5), body.y + body.height / 2), T.px(5), T.DANGER)
        body = inset(body, right=T.px(20))
      value = resolve(item.value) if item.value is not None else None
      if value:
        ink = T.WARNING if item.value_tone == Tone.WARNING else (T.TEXT_TERTIARY if chosen else T.TEXT_MUTED)
        w = draw.text(body, value, T.SIZE_LABEL, ink, T.FONT_SEMIBOLD if item.value_tone == Tone.WARNING else T.FONT_MEDIUM, Align.END)
        body = inset(body, right=w + T.px(10))
      draw.text(body, item.label, T.SIZE_BODY, T.TEXT if chosen else T.TEXT_SECONDARY, T.FONT_SEMIBOLD)

    y = rect.y + rect.height
    for w in reversed(self._footer):
      _, h = size_of(w, rect.width)
      y -= h
      w.render(rl.Rectangle(rect.x, y, rect.width, h))
      y -= T.px(8)


class PageHeader(Component):
  """Screen title with a subtitle beside it, and an optional control on the right."""
  grow_touch_target = False

  def __init__(self, title: Bindable[str], subtitle: Bindable[str] | None = None, trailing: Widget | None = None,
               size: int = T.SIZE_TITLE):
    super().__init__()
    self._size = size
    self._title = title
    self._subtitle = subtitle
    self._trailing = self._child(trailing) if trailing is not None else None

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    trailing = size_of(self._trailing, max_width / 2)[1] if self._trailing is not None else 0
    return max_width, max(T.px(36), trailing)   # the mock's 30 px title at line-height 1.2, or the control's height

  def _render(self, rect: rl.Rectangle):
    body = inset(rect, x=T.px(6))
    if self._trailing is not None:
      w, h = size_of(self._trailing, body.width / 2)
      self._trailing.render(place(body, w, h, Align.END))
      body = inset(body, right=w + T.px(14))
    w = draw.text(body, resolve(self._title), self._size, T.TEXT, T.FONT_EXTRABOLD)
    if self._subtitle is not None:
      draw.text(inset(body, left=w + T.px(16), top=T.px(4)), resolve(self._subtitle), T.font_px(16), T.TEXT_TERTIARY)


class HubTile(Component):
  """A hub card: icon well, title and up to two status lines."""

  def __init__(self, title: str, lines: list[Bindable[str]], on_click: Callable[[], None] | None = None,
               glyph: Glyph | None = None, icon: str | None = None, highlight_line: int | None = None):
    super().__init__()
    self._title = title
    self._lines = lines
    self._glyph = glyph
    self._icon = icon
    self._highlight_line = highlight_line
    self.set_click_callback(on_click)

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.SURFACE_3, T.RADIUS_PANEL)
    if self.is_pressed:
      draw.pressed(rect, T.RADIUS_PANEL)
    body = inset(rect, T.px(20))
    well = place(body, T.ICON_WELL, T.ICON_WELL, Align.START)
    draw.fill(well, T.ACCENT_SURFACE, T.px(16))
    if self._glyph:
      self._glyph(well, T.ACCENT_TEXT, T.ICON_WELL * 0.48)
    elif self._icon:
      draw.icon(well, self._icon, T.ACCENT_TEXT, T.ICON_WELL * 0.48)
    text = inset(body, left=T.ICON_WELL + T.px(18))
    heights = [draw.line_height(T.SIZE_CARD_TITLE)] + [draw.line_height(T.font_px(15))] * len(self._lines)
    block = place(text, text.width, sum(heights) + T.px(5) * len(self._lines))
    rects = column(block, heights, T.px(5))
    draw.text(rects[0], self._title, T.SIZE_CARD_TITLE, T.TEXT, T.FONT_BOLD)
    for i, (line, r) in enumerate(zip(self._lines, rects[1:], strict=True)):
      draw.text(r, resolve(line), T.font_px(15), T.ACCENT_TEXT if i == self._highlight_line else T.TEXT_TERTIARY)


class HubGrid(Component):
  """Tiles in rows. rows gives the tile count per row (e.g. [3, 2]); by default, rows of `columns`."""
  grow_touch_target = False

  def __init__(self, tiles: list[HubTile], columns: int = 3, tile_height: float = T.px(128), rows: list[int] | None = None):
    super().__init__()
    self._tiles = [self._child(t) for t in tiles]
    self._rows = rows or [min(columns, len(tiles) - i) for i in range(0, len(tiles), columns)]
    assert sum(self._rows) == len(tiles)
    self._tile_height = tile_height

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    n = len(self._rows)
    return max_width, n * self._tile_height + (n - 1) * T.px(14)

  def _render(self, rect: rl.Rectangle):
    tiles = iter(self._tiles)
    for count, line in zip(self._rows, column(rect, [self._tile_height] * len(self._rows), T.px(14)), strict=True):
      for cell in row(line, [FILL] * count, T.px(14)):
        next(tiles).render(cell)


class SettingsPage(Component):
  """A whole settings screen: optional header, optional sidebar, the content, and the bottom nav.

  Every StarPilot screen is one of these, so pages only declare their rows.
  """
  grow_touch_target = False

  def __init__(self, content: Widget, nav: BottomNav | None = None, sidebar: Sidebar | None = None,
               header: PageHeader | None = None):
    super().__init__()
    self._content = self._child(content)
    self._nav = self._child(nav) if nav is not None else None
    self._sidebar = self._child(sidebar) if sidebar is not None else None
    self._header = self._child(header) if header is not None else None

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.BG)
    body = rect
    if self._nav is not None:
      body, nav_rect = column(rect, [FILL, T.NAV_HEIGHT])
      self._nav.render(nav_rect)
    body = inset(body, left=T.PAGE_INSET, right=T.PAGE_INSET, top=T.px(18), bottom=T.px(14))
    if self._header is not None:
      header_rect, body = column(body, [self._header.preferred_height(body.width), FILL], T.px(14))
      self._header.render(header_rect)
    if self._sidebar is not None:
      side_rect, body = row(body, [self._sidebar.preferred_size(body.width)[0], FILL], T.PANEL_GAP)
      self._sidebar.render(inset(side_rect, top=T.px(8)))
    self._content.render(body)
