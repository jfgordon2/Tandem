"""Layout blocks for screens built like the mocks: stacks, cards, columns, labels and inline value lines.

A Stack lays widgets top to bottom; SPACER entries share the leftover height, so an action can sit at a card's
bottom as in the mocks (flex-grow: 1). A Card is a Stack on a rounded surface. Columns split the width by weight.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve, size_of
from openpilot.selfdrive.ui.tandem.layout import Align, Fill, column, inset, place, row
from openpilot.selfdrive.ui.tandem.fonts import Face

SPACER: None = None   # in a Stack, takes up the space left over


class Stack(Component):
  """Widgets in a column, each at its preferred height. Hidden widgets take no room; SPACER (None) items share what's left."""
  grow_touch_target = False

  def __init__(self, items: Sequence[Widget | None], gap: float = T.px(12), grow: int | None = None):
    """Makes a stack.

    Args:
      items: The widgets, top first. SPACER (None) takes a share of the height left over.
      gap: The space between items.
      grow: The index of an item that takes the leftover height instead of a spacer (a card that fills its column).
    """
    super().__init__()
    self._items = list(items)
    self._grow = grow
    for w in items:
      if w is not None:
        self._child(w)
    self._gap = gap

  def _visible(self) -> list[Widget | None]:
    return [w for w in self._items if w is None or w.is_visible]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    items = [w for w in self._visible() if w is not None]
    gaps = max(0, len(self._visible()) - 1) * self._gap
    return max_width, sum(size_of(w, max_width)[1] for w in items) + gaps

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(touch_callback)
    for w in self._items:
      if w is not None:
        w.set_touch_valid_callback(touch_callback)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in self._items:
      if w is not None:
        w.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle) -> None:
    items = self._visible()
    grow = self._items[self._grow] if self._grow is not None else None
    heights = [None if w is None or w is grow else size_of(w, rect.width)[1] for w in items]
    fixed = sum(h for h in heights if h is not None) + max(0, len(items) - 1) * self._gap
    spacers = sum(1 for h in heights if h is None)
    spare = max(0.0, rect.height - fixed) / spacers if spacers else 0.0
    y = rect.y
    for w, h in zip(items, heights, strict=True):
      height = spare if h is None else h
      if w is not None:
        w.render(rl.Rectangle(rect.x, y, rect.width, height))
      y += height + self._gap


class Card(Stack):
  """A rounded surface holding a stack. tone="accent" is the selected/active card (accent fill and edge)."""

  def __init__(self, items: Sequence[Widget | None], gap: float = T.px(12), padding: tuple[float, float] = (T.px(22), T.px(20)),
               tone: str = "plain", background: rl.Color | None = None, grow: int | None = None):
    super().__init__(items, gap, grow)
    self._padding = padding
    self._tone = tone
    self._background = background

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    px, py = self._padding
    _, h = super().preferred_size(max_width - px * 2)
    return max_width, h + py * 2

  def _render(self, rect: rl.Rectangle) -> None:
    accent = self._tone == "accent"
    draw.fill(rect, self._background or (T.ACCENT_SELECTED if accent else T.SURFACE_2), T.RADIUS_PANEL)
    if accent:
      draw.stroke(rect, T.ACCENT_EDGE, T.RADIUS_PANEL, T.px(2))
    px, py = self._padding
    super()._render(inset(rect, x=px, y=py))


class Columns(Component):
  """Widgets side by side. weights are column widths relative to each other (1, 1.2 ...)."""
  grow_touch_target = False

  def __init__(self, items: Sequence[Widget], weights: Sequence[float] | None = None, gap: float = T.px(14)):
    super().__init__()
    self._items = [self._child(w) for w in items]
    self._weights = list(weights) if weights else [1.0] * len(items)
    self._gap = gap

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    widths = row(rl.Rectangle(0, 0, max_width, 0), [Fill(w) for w in self._weights], self._gap)
    return max_width, max(size_of(w, r.width)[1] for w, r in zip(self._items, widths, strict=True))

  def _render(self, rect: rl.Rectangle) -> None:
    for w, r in zip(self._items, row(rect, [Fill(x) for x in self._weights], self._gap), strict=True):
      w.render(r)


class Label(Component):
  """One line of text sized to its font: a card's title, a big name, a caption. icon draws a mock icon before it."""
  grow_touch_target = False

  def __init__(self, text: Bindable[str], size: int = T.SIZE_PANEL_TITLE, color: Bindable[rl.Color] = T.TEXT, weight: Face = T.FONT_BOLD,
               caption: bool = False, h: Align = Align.START, icon: Bindable[str | None] = None, icon_color: Bindable[rl.Color] | None = None,
               fit: bool = False):
    """fit: as wide as the text, e.g. "7 settings" beside a panel title."""
    super().__init__()
    self._fit = fit
    self._text, self._size, self._color, self._weight, self._caption, self._h = text, size, color, weight, caption, h
    self._icon, self._icon_color = icon, icon_color

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    size = T.SIZE_CAPTION if self._caption else self._size
    width = draw.text_width(resolve(self._text), size, self._weight) + T.px(2) if self._fit else max_width
    return min(width, max_width), draw.line_height(size)

  def _render(self, rect: rl.Rectangle) -> None:
    name = resolve(self._icon)
    if name:
      size = round(self._size * 1.1)
      draw.icon(rl.Rectangle(rect.x, rect.y, size, rect.height), name, resolve(self._icon_color or self._color), size)
      rect = inset(rect, left=size + T.px(8))
    if self._caption:
      draw.caption(rect, resolve(self._text), resolve(self._color), self._h)
    else:
      draw.text(rect, resolve(self._text), self._size, resolve(self._color), self._weight, self._h)


class ValueLine(Component):
  """"Engage and disengage chimes ........ 60%": a muted label with its value at the right. Tappable with on_click."""

  def __init__(self, label: Bindable[str], value: Bindable[str], on_click: Callable[[], None] | None = None, size: int = T.font_px(16),
               height: float | None = None):
    """Makes a label and value line.

    Args:
      label: The name on the left.
      value: The value on the right, or a getter for it.
      on_click: Runs on a tap.
      size: The text size.
      height: Makes it a finger-sized tile (a filled row with a chevron) instead of a bare line.
    """
    super().__init__()
    self._label, self._value, self._size, self._height = label, value, size, height
    self.set_click_callback(on_click)
    self.grow_touch_target = False

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._height or draw.line_height(self._size) + T.px(6)

  def _render(self, rect: rl.Rectangle) -> None:
    if self._height:
      draw.fill(rect, T.SURFACE_4, T.px(14))
      if self._click_callback and self.is_pressed:
        draw.pressed(rect, T.px(14))
      rect = inset(rect, x=T.px(16))
      if self._click_callback:
        size = T.px(16)
        draw.chevron(rl.Rectangle(rect.x + rect.width - size, rect.y, size, rect.height), T.TEXT_TERTIARY, size)
        rect = inset(rect, right=size + T.px(12))
    elif self._click_callback and self.is_pressed:
      draw.pressed(rect, T.px(8))
    w = draw.text(rect, resolve(self._value), self._size, T.TEXT, T.FONT_SEMIBOLD, Align.END)
    draw.text(inset(rect, right=w + T.px(12)), resolve(self._label), self._size, T.TEXT_SECONDARY if self._height else T.TEXT_TERTIARY)


class Sized(Component):
  """Gives a widget a fixed height in a stack (e.g. a 76 px switch row card)."""
  grow_touch_target = False

  def __init__(self, child: Widget, height: float):
    super().__init__()
    self._content = self._child(child)
    self._height = height

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._height

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._content.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle) -> None:
    self._content.render(rect)


class Surface(Component):
  """A widget on a rounded fill, e.g. the "Use recommended" box inside the active model card."""
  grow_touch_target = False

  def __init__(self, child: Widget, background: rl.Color = T.SURFACE_1, radius: float = T.px(16), padding: float = 0):
    super().__init__()
    self._content = self._child(child)
    self._background, self._radius, self._padding = background, radius, padding

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    _, h = size_of(self._content, max_width - self._padding * 2)
    return max_width, h + self._padding * 2

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._content.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle) -> None:
    draw.fill(rect, self._background, self._radius)
    self._content.render(inset(rect, self._padding) if self._padding else rect)


class Inline(Component):
  """A widget at its own width in a stack (a badge, a link button), aligned left by default."""
  grow_touch_target = False

  def __init__(self, child: Widget, h: Align = Align.START):
    super().__init__()
    self._content = self._child(child)
    self._h = h

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, size_of(self._content, max_width)[1]

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    self._content.set_parent_rect(parent_rect)

  def _render(self, rect: rl.Rectangle) -> None:
    w, h = size_of(self._content, rect.width)
    self._content.render(place(rect, w, h, self._h))


class IconTitle(Component):
  """An icon well beside a title and a line, as at the top of the Offline Maps region card."""
  grow_touch_target = False

  def __init__(self, icon: str, title: Bindable[str], line: Bindable[str], size: int = T.font_px(22)):
    super().__init__()
    self._icon, self._title, self._line, self._size = icon, title, line, size

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(60)

  def _render(self, rect: rl.Rectangle) -> None:
    well = rl.Rectangle(rect.x, rect.y, T.px(60), T.px(60))
    draw.fill(well, T.ACCENT_SURFACE, T.px(16))
    draw.icon(well, self._icon, T.ACCENT_TEXT, T.px(28))
    text = inset(rect, left=T.px(76))
    lines = [draw.line_height(self._size), draw.line_height(T.font_px(15))]
    title, line = column(place(text, text.width, sum(lines) + T.px(3)), lines, T.px(3))
    draw.text(title, resolve(self._title), self._size, T.TEXT, T.FONT_BOLD)
    draw.text(line, resolve(self._line), T.font_px(15), T.TEXT_TERTIARY)


class Field(Component):
  """A labelled box showing a value or its placeholder; tapping it edits the value (with the keyboard)."""

  def __init__(self, label: str, value: Bindable[str], placeholder: str, on_click: Callable[[], None], height: float = T.px(44)):
    super().__init__()
    self._label, self._value, self._placeholder, self._height = label, value, placeholder, height
    self.set_click_callback(on_click)
    self.grow_touch_target = False

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, draw.line_height(T.SIZE_SUBTITLE) + T.px(6) + self._height

  def _render(self, rect: rl.Rectangle) -> None:
    label_h = draw.line_height(T.SIZE_SUBTITLE)
    draw.text(rl.Rectangle(rect.x, rect.y, rect.width, label_h), self._label, T.SIZE_SUBTITLE, T.TEXT_SECONDARY, T.FONT_SEMIBOLD)
    box = rl.Rectangle(rect.x, rect.y + label_h + T.px(6), rect.width, self._height)
    draw.fill(box, T.SURFACE_4, T.px(12))
    draw.stroke(box, T.TRACK, T.px(12), T.px(1))
    if self.is_pressed:
      draw.pressed(box, T.px(12))
    value = resolve(self._value)
    text = inset(box, x=T.px(12))
    draw.text(rl.Rectangle(text.x, text.y, text.width, min(text.height, T.px(44))), value or self._placeholder, T.font_px(15),
              T.TEXT if value else T.TEXT_MUTED)


class Grid(Component):
  """Widgets in rows of `columns`, each row as tall as its tallest item (or row_height)."""
  grow_touch_target = False

  def __init__(self, items: Sequence[Widget], columns: int = 2, gap: float = T.px(10), row_height: float | None = None):
    super().__init__()
    self._items = [self._child(w) for w in items]
    self._columns, self._gap, self._row_height = columns, gap, row_height

  def _rows(self) -> list[list[Widget]]:
    visible = [w for w in self._items if w.is_visible]
    return [visible[i:i + self._columns] for i in range(0, len(visible), self._columns)]

  def _cell_width(self, width: float) -> float:
    return (width - self._gap * (self._columns - 1)) / self._columns

  def _height(self, items: list[Widget], width: float) -> float:
    return self._row_height or max(size_of(w, self._cell_width(width))[1] for w in items)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    rows = self._rows()
    return max_width, sum(self._height(r, max_width) for r in rows) + self._gap * max(0, len(rows) - 1)

  def set_parent_rect(self, parent_rect: rl.Rectangle) -> None:
    super().set_parent_rect(parent_rect)
    for w in self._items:
      w.set_parent_rect(parent_rect)

  def set_touch_valid_callback(self, touch_callback: Callable[[], bool]) -> None:
    super().set_touch_valid_callback(touch_callback)
    for w in self._items:
      w.set_touch_valid_callback(touch_callback)

  def _render(self, rect: rl.Rectangle) -> None:
    w = self._cell_width(rect.width)
    y = rect.y
    for items in self._rows():
      h = self._height(items, rect.width)
      for i, item in enumerate(items):
        item.render(rl.Rectangle(rect.x + i * (w + self._gap), y, w, h))
      y += h + self._gap


class InfoCard(Component):
  """A small card: an optional icon, a title and a line (Weather's conditions)."""
  grow_touch_target = False

  def __init__(self, title: Bindable[str], line: Bindable[str], icon: str | None = None, background: rl.Color = T.SURFACE_4):
    super().__init__()
    self._title, self._line, self._icon, self._background = title, line, icon, background

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, draw.line_height(T.font_px(17)) + T.px(3) + draw.line_height(T.SIZE_SUBTITLE) + T.px(28)

  def _render(self, rect: rl.Rectangle) -> None:
    draw.fill(rect, self._background, T.px(16))
    body = inset(rect, x=T.px(16), y=T.px(14))
    if self._icon:
      draw.icon(rl.Rectangle(body.x, body.y, T.px(24), body.height), self._icon, self.ink(T.ACCENT_TEXT), T.px(24))
      body = inset(body, left=T.px(36))
    title, line = column(body, [draw.line_height(T.font_px(17)), draw.line_height(T.SIZE_SUBTITLE)], T.px(3))
    draw.text(title, resolve(self._title), T.font_px(17), self.ink(T.TEXT), T.FONT_BOLD)
    draw.text(line, resolve(self._line), T.SIZE_SUBTITLE, self.ink(T.TEXT_TERTIARY))

  def ink(self, color: rl.Color) -> rl.Color:
    return color if self.enabled else T.TEXT_MUTED


class Icon(Component):
  """A mock icon as a widget, e.g. leading a row (Home, Work)."""
  grow_touch_target = False

  def __init__(self, name: str, size: float = T.px(22), color: rl.Color = T.ACCENT_TEXT):
    super().__init__()
    self._name, self._size, self._color = name, size, color

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._size, self._size

  def _render(self, rect: rl.Rectangle) -> None:
    draw.icon(rect, self._name, self._color if self.enabled else T.TEXT_MUTED, self._size)


class Rule(Component):
  """A divider line across a stack, as between Vehicle Profile's cards and Trailer Load. dim fades it with a disabled row."""
  grow_touch_target = False

  def __init__(self, dim: Bindable[bool] = False):
    super().__init__()
    self._dim = dim

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.DIVIDER

  def _render(self, rect: rl.Rectangle) -> None:
    draw.hline(rect.x, rect.y, rect.width, draw.alpha(T.CONTROL, 0.4) if resolve(self._dim) else T.CONTROL)
