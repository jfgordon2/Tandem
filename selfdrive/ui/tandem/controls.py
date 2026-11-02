"""Buttons, switches, segmented choices, steppers, sliders, badges, chips and progress bars."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import pyray as rl

from openpilot.system.ui.lib.application import MousePos
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Bindable, Component, resolve
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, grid, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_


class Tone(Enum):
  ACCENT = "accent"
  NEUTRAL = "neutral"
  SUCCESS = "success"
  WARNING = "warning"
  DANGER = "danger"


# (fill, text) for chips and badges
_TONE_COLORS = {
  Tone.ACCENT: (T.ACCENT_SURFACE, T.ACCENT_CHIP_TEXT),
  Tone.NEUTRAL: (T.CONTROL, T.TEXT_SECONDARY),
  Tone.SUCCESS: (T.SUCCESS_SURFACE, T.SUCCESS_CHIP_TEXT),
  Tone.WARNING: (T.WARNING_SURFACE, T.WARNING_CHIP_TEXT),
  Tone.DANGER: (T.DANGER_SURFACE, T.DANGER_TEXT),
}
_TONE_INK = {Tone.ACCENT: T.ACCENT_TEXT, Tone.NEUTRAL: T.TEXT_SECONDARY, Tone.SUCCESS: T.SUCCESS_TEXT,
             Tone.WARNING: T.WARNING, Tone.DANGER: T.DANGER_TEXT}


def _approach(current: float, target: float, duration_ms: float) -> float:
  step = rl.get_frame_time() * 1000 / max(duration_ms, 1)
  return target if abs(target - current) <= step else current + step * (1 if target > current else -1)


# ── Button ──

class ButtonStyle(Enum):
  PRIMARY = "primary"            # filled accent, the one main action
  SECONDARY = "secondary"        # filled CONTROL
  GHOST = "ghost"                # text only, for links like "Reset to default"
  DANGER = "danger"              # filled red, destructive confirm
  DANGER_SOFT = "soft"           # tinted red: every destructive entry point (End route, Delete all, Uninstall, Power Off)
  NAV = "nav"                    # back/close squares and onroad controls


_BUTTON_COLORS = {
  ButtonStyle.PRIMARY: (T.ACCENT, T.ACCENT_INK, None),
  ButtonStyle.SECONDARY: (T.CONTROL, T.TEXT, None),
  ButtonStyle.GHOST: (None, T.ACCENT_TEXT, None),
  ButtonStyle.DANGER: (T.DANGER_BUTTON, T.TEXT, None),
  ButtonStyle.DANGER_SOFT: (T.DANGER_SURFACE, T.DANGER_TEXT, None),
  ButtonStyle.NAV: (T.CONTROL_NAV, T.TEXT, None),
}

# Draws a glyph centered in a rect: draw.chevron/cross/plus/... or a custom callable.
Glyph = Callable[[rl.Rectangle, rl.Color, float], None]


def back_glyph(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  draw.chevron(rect, color, size, "left")


class Button(Component):
  def __init__(self, label: Bindable[str] = "", on_click: Callable[[], None] | None = None, style: ButtonStyle = ButtonStyle.SECONDARY,
               glyph: Glyph | None = None, height: float = T.BUTTON_HEIGHT, width: float | None = None,
               font_size: int = T.SIZE_BUTTON, radius: float = T.RADIUS_CONTROL, accessory: Glyph | None = None,
               weight=None, padding: float = T.px(18)):
    """weight overrides the style's weight (e.g. a bold secondary button, as Play sample is in the mock)."""
    super().__init__()
    self._label = label
    self._style = style
    self._glyph = glyph
    self._accessory = accessory          # trailing glyph, e.g. a chevron on value buttons
    self._height = height
    self._width = width
    self._font_size = font_size
    self._radius = radius
    self._padding = padding
    self._weight_override = weight
    self.set_click_callback(on_click)

  def restyle(self, height: float, font_size: int, padding: float, radius: float) -> None:
    """Resize in place, e.g. a sheet giving its header actions the mock's size. The main action goes extra bold, as there."""
    self._height, self._font_size, self._padding, self._radius = height, font_size, padding, radius
    if self._style == ButtonStyle.PRIMARY:
      self._weight_override = T.FONT_EXTRABOLD

  @property
  def _weight(self):
    if self._weight_override is not None:
      return self._weight_override
    return T.FONT_BOLD if self._style in (ButtonStyle.PRIMARY, ButtonStyle.DANGER, ButtonStyle.DANGER_SOFT) else T.FONT_SEMIBOLD

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    if self._width is not None:
      return self._width, self._height
    label = resolve(self._label)
    if not label:
      return self._height, self._height
    width = draw.text_width(label, self._font_size, self._weight) + self._padding * 2
    width += (self._height * 0.45 + T.px(10)) if self._glyph else 0
    width += (self._height * 0.35 + T.px(8)) if self._accessory else 0
    return min(max_width, width), self._height

  def _render(self, rect: rl.Rectangle):
    bg, ink, outline = _BUTTON_COLORS[self._style]
    if not self.enabled:
      bg, ink = (T.CONTROL if bg is not None else None), T.TEXT_MUTED
    if bg is not None:
      draw.fill(rect, bg, self._radius)
    if outline is not None:
      draw.stroke(rect, outline, self._radius)
    if self.is_pressed and self.enabled:
      draw.pressed(rect, self._radius)

    label = resolve(self._label)
    glyph_size = self._height * 0.45
    if not label:
      if self._glyph:
        self._glyph(rect, ink, glyph_size)
      return

    acc_size = self._height * 0.35
    label_w = draw.text_width(label, self._font_size, self._weight)
    content_w = label_w + (glyph_size + T.px(10) if self._glyph else 0) + (acc_size + T.px(8) if self._accessory else 0)
    content = place(rect, min(content_w, rect.width - T.px(12)), rect.height)
    if self._glyph:
      self._glyph(rl.Rectangle(content.x, content.y, glyph_size, content.height), ink, glyph_size)
      content = inset(content, left=glyph_size + T.px(10))
    if self._accessory:
      self._accessory(rl.Rectangle(content.x + content.width - acc_size, content.y, acc_size, content.height), ink, acc_size)
      content = inset(content, right=acc_size + T.px(8))
    draw.text(content, label, self._font_size, ink, self._weight, Align.START)


class ButtonRow(Component):
  """Buttons side by side at equal widths, e.g. Restart and Power Off. Hidden buttons give up their space."""
  grow_touch_target = False

  def __init__(self, buttons: list[Button], height: float = T.px(52), gap: float = T.px(10)):
    super().__init__()
    self._buttons = [self._child(b) for b in buttons]
    self._height = height
    self._gap = gap

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._height

  def _render(self, rect: rl.Rectangle):
    visible = [b for b in self._buttons if b.is_visible]
    for button, cell in zip(visible, row(rect, [FILL] * len(visible), self._gap), strict=True):
      button.render(cell)


class ToggleButton(Component):
  """A compact on/off button: label, then On or Off. Used where a full row would be too much, e.g. the power-user strip."""

  def __init__(self, label: str, value: Bindable[bool], on_change: Callable[[bool], None], height: float = T.px(44)):
    super().__init__()
    self._label = label
    self._value = value
    self._height = height
    self.set_click_callback(lambda: on_change(not resolve(value)))

  def _state(self) -> str:
    return N_("On") if resolve(self._value) else N_("Off")

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    width = draw.text_width(self._label, T.font_px(16), T.FONT_SEMIBOLD) + T.px(10) + draw.text_width(N_("Off"), T.font_px(14), T.FONT_MEDIUM)
    return min(max_width, width + T.px(32)), self._height

  def _render(self, rect: rl.Rectangle):
    on = resolve(self._value)
    draw.fill(rect, T.ACCENT_SURFACE if on else T.SURFACE_3, T.RADIUS_CONTROL)
    if self.is_pressed:
      draw.pressed(rect, T.RADIUS_CONTROL)
    body = inset(rect, x=T.px(16))
    w = draw.text(body, self._label, T.font_px(16), T.TEXT, T.FONT_SEMIBOLD)
    draw.text(inset(body, left=w + T.px(10)), self._state(), T.font_px(14), T.ACCENT_TEXT if on else T.TEXT_MUTED, T.FONT_MEDIUM,
              elide=False)


@dataclass(frozen=True)
class TallCards:
  """ChoiceCards drawn tall, with the title at the top and the line wrapping under it."""
  title_size: int
  subtitle_size: int
  padding: tuple[float, float]   # x, y
  radius: float
  background: rl.Color
  gap: float


SETUP_CARDS = TallCards(T.font_px(26), T.font_px(16), (T.px(24), T.px(24)), T.px(24), T.SURFACE_2, T.px(16))
TILE_CARDS = TallCards(T.font_px(21), T.SIZE_SUBTITLE, (T.px(18), T.px(16)), T.px(18), T.SURFACE_4, T.px(10))   # Vehicle Profile


class ChoiceCards(Component):
  """Pick one of a few options shown as cards, each with a title and a line explaining it."""
  grow_touch_target = False

  def __init__(self, options: list[tuple[str, str]], selected: Bindable[int], on_change: Callable[[int], None],
               columns: int = 2, card_height: float = T.px(92), large: TallCards | None = None):
    """large: tall cards that fill their rect (first-run setup, Vehicle Profile); " · recommended" in a title becomes a badge."""
    super().__init__()
    self._large = large
    self._options = options
    self._selected = selected
    self._on_change = on_change
    self._columns = columns
    self._card_height = card_height
    self._pressed_card: int | None = None

  def _rows(self) -> int:
    return -(-len(self._options) // self._columns)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    rows = self._rows()
    return max_width, rows * self._card_height + (rows - 1) * T.px(12)

  def card_rects(self) -> list[rl.Rectangle]:
    return grid(self._rect, self._columns, self._rows(), self._large.gap if self._large else T.px(12))[:len(self._options)]

  def _hit(self, pos: MousePos) -> int | None:
    return next((i for i, r in enumerate(self.card_rects()) if rl.check_collision_point_rec(pos, r)), None)

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    self._pressed_card = self._hit(mouse_pos)

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    hit = self._hit(mouse_pos)
    if hit is not None and hit == self._pressed_card and hit != resolve(self._selected):
      self._on_change(hit)
    self._pressed_card = None

  def _render(self, rect: rl.Rectangle):
    selected = resolve(self._selected)
    radius = self._large.radius if self._large else T.RADIUS_CARD
    for i, ((title, subtitle), r) in enumerate(zip(self._options, self.card_rects(), strict=True)):
      chosen = i == selected
      draw.fill(r, T.ACCENT_SELECTED if chosen else (self._large.background if self._large else T.SURFACE_4), radius)
      if chosen:
        draw.stroke(r, T.ACCENT, radius, T.px(2))
      elif self.is_pressed and i == self._pressed_card:
        draw.pressed(r, radius)
      if self._large:
        self._render_large(inset(r, x=self._large.padding[0], y=self._large.padding[1]), title, subtitle, self._large)
        continue
      body = inset(r, x=T.px(18))
      lines = [draw.line_height(T.font_px(19)), draw.line_height(T.SIZE_SUBTITLE)]
      title_rect, sub_rect = column(place(body, body.width, sum(lines) + T.px(4)), lines, T.px(4))
      draw.text(title_rect, title, T.font_px(19), T.TEXT, T.FONT_BOLD)
      draw.text(sub_rect, subtitle, T.SIZE_SUBTITLE, T.TEXT_TERTIARY)

  @staticmethod
  def _render_large(body: rl.Rectangle, title: str, subtitle: str, style: TallCards) -> None:
    name, recommended = title.removesuffix(" · recommended"), title.endswith(" · recommended")
    size = style.title_size
    title_rect = rl.Rectangle(body.x, body.y, body.width, draw.line_height(size))
    w = draw.text(title_rect, name, size, T.TEXT, T.FONT_EXTRABOLD)
    if recommended:
      label = N_("RECOMMENDED")
      badge = place(inset(title_rect, left=w + T.px(10)), draw.text_width(label, T.SIZE_BADGE, T.FONT_BOLD) + T.px(16), T.px(26), Align.START)
      draw.fill(badge, T.ACCENT, T.RADIUS_BADGE)
      draw.text(badge, label, T.SIZE_BADGE, T.ACCENT_INK, T.FONT_BOLD, Align.CENTER)
    draw.paragraph(inset(body, top=title_rect.height + T.px(6 if style.title_size < T.font_px(24) else 10)), subtitle, style.subtitle_size,
                   T.TEXT_TERTIARY)


class ValueButton(Button):
  """A secondary button showing the current choice with a chevron, e.g. "Sequential >". Opens a picker."""

  def __init__(self, value: Bindable[str], on_click: Callable[[], None] | None = None):
    super().__init__(value, on_click, ButtonStyle.SECONDARY, font_size=T.font_px(17),
                     accessory=lambda r, c, s: draw.chevron(r, c, s))

  @property
  def _weight(self):
    return T.FONT_BOLD


# ── Switch ──

class Switch(Component):
  def __init__(self, value: Bindable[bool], on_change: Callable[[bool], None] | None = None,
               width: float = T.SWITCH_WIDTH, height: float = T.SWITCH_HEIGHT):
    super().__init__()
    self._value = value
    self._on_change = on_change
    self._size = (width, height)
    self._knob = 1.0 if resolve(value) else 0.0

  @property
  def value(self) -> bool:
    return bool(resolve(self._value))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._size

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    if self._on_change:
      self._on_change(not self.value)

  def _render(self, rect: rl.Rectangle):
    on = self.value
    self._knob = _approach(self._knob, 1.0 if on else 0.0, T.SWITCH_MS)
    track = place(rect, *self._size)
    track_color = T.SWITCH_TRACK_ON if on else T.SWITCH_TRACK_OFF
    knob_color = T.SWITCH_KNOB_ON if on else T.SWITCH_KNOB_OFF
    if not self.enabled:
      track_color, knob_color = draw.alpha(track_color, T.DISABLED_ALPHA), draw.alpha(knob_color, T.DISABLED_ALPHA)
    draw.fill(track, track_color, track.height / 2)
    pad = track.height * 0.1
    d = track.height - pad * 2
    x = track.x + pad + (track.width - pad * 2 - d) * self._knob
    rl.draw_circle_v(rl.Vector2(x + d / 2, track.y + track.height / 2), d / 2, knob_color)


# ── Segmented ──

class Segmented(Component):
  """One choice out of a few, shown side by side."""

  def __init__(self, options: list[str], selected: Bindable[int], on_change: Callable[[int], None] | None = None,
               height: float = T.SEGMENT_HEIGHT, font_size: int = T.SIZE_BUTTON, equal: bool = False):
    super().__init__()
    self._options = options
    self._selected = selected
    self._on_change = on_change
    self._height = height
    self._font_size = font_size
    self._equal = equal
    self._inset = T.px(4)
    self._pad = T.px(16)

  @property
  def selected(self) -> int:
    return int(resolve(self._selected))

  def _widths(self) -> list[float]:
    return [draw.text_width(o, self._font_size, T.FONT_BOLD) + self._pad * 2 for o in self._options]

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    widths = self._widths()
    total = (max(widths) * len(widths) if self._equal else sum(widths)) + self._inset * 2
    return min(max_width, total), self._height

  def segment_rects(self) -> list[rl.Rectangle]:
    inner = inset(self._rect, self._inset)
    if self._equal:
      return row(inner, [1.0 * inner.width / len(self._options)] * len(self._options))
    widths = self._widths()
    scale = min(1.0, inner.width / sum(widths)) if sum(widths) else 1.0
    return row(inner, [w * scale for w in widths])

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    for i, r in enumerate(self.segment_rects()):
      if r.x <= mouse_pos.x < r.x + r.width:
        if i != self.selected and self._on_change:
          self._on_change(i)
        return

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.CONTROL, T.RADIUS_SEGMENT_TRACK)
    for i, (label, r) in enumerate(zip(self._options, self.segment_rects(), strict=True)):
      chosen = i == self.selected
      if chosen:
        draw.fill(r, T.ACCENT if self.enabled else T.TEXT_MUTED, T.RADIUS_SEGMENT)
      ink = T.ACCENT_INK if chosen else (T.TEXT_SECONDARY if self.enabled else T.TEXT_MUTED)
      draw.text(r, label, self._font_size, ink, T.FONT_BOLD if chosen else T.FONT_SEMIBOLD, Align.CENTER)


# ── Stepper ──

class Stepper(Component):
  """− value + with hold-to-repeat."""
  REPEAT_DELAY = 0.4
  REPEAT_INTERVAL = 0.08

  def __init__(self, value: Bindable[float], on_change: Callable[[float], None], minimum: float, maximum: float, step: float = 1,
               fmt: Callable[[float], str] = lambda v: f"{v:g}", value_width: float = T.px(74), height: float = T.px(48),
               button_size: float = T.px(44), font_size: int = T.font_px(17)):
    super().__init__()
    self._value = value
    self._on_change = on_change
    self._min, self._max, self._step = minimum, maximum, step
    self._fmt = fmt
    self._value_width = value_width
    self._height = height
    self._button_size = button_size
    self._font_size = font_size
    self._direction = 0
    self._repeat_at: float | None = None
    self._repeated = False

  @property
  def value(self) -> float:
    return float(resolve(self._value))

  def stepped(self, direction: int) -> float:
    steps = round((self.value - self._min) / self._step) + direction
    return min(self._max, max(self._min, self._min + steps * self._step))

  def _apply(self, direction: int) -> None:
    new = self.stepped(direction)
    if new != self.value:
      self._on_change(new)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._button_size * 2 + self._value_width + T.px(8), self._height

  def _parts(self) -> list[rl.Rectangle]:
    return row(inset(self._rect, T.px(4)), [self._button_size, self._value_width, self._button_size])

  def _handle_mouse_press(self, mouse_pos: MousePos) -> None:
    minus_rect, _, plus_rect = self._parts()
    self._direction = -1 if mouse_pos.x < minus_rect.x + minus_rect.width + self._value_width / 2 else 1
    self._repeat_at = rl.get_time() + self.REPEAT_DELAY
    self._repeated = False

  def _handle_mouse_release(self, mouse_pos: MousePos) -> None:
    super()._handle_mouse_release(mouse_pos)
    if not self._repeated and self._direction:
      self._apply(self._direction)
    self._direction, self._repeat_at = 0, None

  def _update_state(self):
    if self._repeat_at is not None and not self.is_pressed:
      self._direction, self._repeat_at = 0, None
    elif self._repeat_at is not None and rl.get_time() >= self._repeat_at:
      self._apply(self._direction)
      self._repeated = True
      self._repeat_at = rl.get_time() + self.REPEAT_INTERVAL

  def _render(self, rect: rl.Rectangle):
    draw.fill(rect, T.CONTROL, T.RADIUS_SEGMENT_TRACK)
    minus_rect, value_rect, plus_rect = self._parts()
    ink = T.TEXT if self.enabled else T.TEXT_MUTED
    for r, d in ((minus_rect, -1), (plus_rect, 1)):
      if self.is_pressed and self._direction == d:
        draw.pressed(r, T.RADIUS_SEGMENT)
      at_limit = self.stepped(d) == self.value
      glyph_ink = T.TEXT_MUTED if at_limit else ink
      (draw.minus if d < 0 else draw.plus)(r, glyph_ink, self._button_size * 0.6)
    draw.text(value_rect, self._fmt(self.value), self._font_size, ink, T.FONT_BOLD, Align.CENTER)


# ── Slider ──

class Slider(Component):
  """A track with a draggable thumb. `floor` blocks values below it (drawn hatched), e.g. the 25% minimum for safety alerts.

  floor_label names that zone above it. Marks at the same value share one label ("Normal · Loud"), and the end labels stay
  inside the slider.
  """

  def __init__(self, value: Bindable[float], on_change: Callable[[float], None], minimum: float, maximum: float, step: float = 1,
               default: float | None = None, floor: float | None = None, marks: list[tuple[float, str]] | None = None,
               height: float = T.px(66), floor_label: str | None = None):
    super().__init__()
    self._floor_label = floor_label
    self._value = value
    self._on_change = on_change
    self._min, self._max, self._step = minimum, maximum, step
    self._default = default
    self._floor = floor
    self._marks = marks or []
    self._height = height

  @property
  def value(self) -> float:
    return float(resolve(self._value))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._height + (T.px(28) if self._marks else 0)

  def merged_marks(self) -> list[tuple[float, str]]:
    merged: dict[float, list[str]] = {}
    for value, label in self._marks:
      merged.setdefault(value, []).append(label)
    return [(value, " · ".join(labels)) for value, labels in merged.items()]

  def _track(self) -> rl.Rectangle:
    thumb = T.px(32)
    return rl.Rectangle(self._rect.x + thumb / 2, self._rect.y + T.px(28), self._rect.width - thumb, T.px(14))

  def x_for(self, value: float) -> float:
    track = self._track()
    return track.x + track.width * (value - self._min) / (self._max - self._min)

  def value_at(self, x: float) -> float:
    track = self._track()
    t = min(1.0, max(0.0, (x - track.x) / track.width)) if track.width else 0.0
    value = self._min + round(t * (self._max - self._min) / self._step) * self._step
    return max(value, self._floor) if self._floor is not None else value

  def _handle_mouse_event(self, mouse_event) -> None:
    if self.is_pressed and mouse_event.left_down:
      new = self.value_at(mouse_event.pos.x)
      if new != self.value:
        self._on_change(new)

  def _render(self, rect: rl.Rectangle):
    track = self._track()
    draw.fill(track, T.TRACK, track.height / 2)
    start = track.x
    if self._floor is not None and self._floor > self._min:
      floor_x = self.x_for(self._floor)
      zone = rl.Rectangle(track.x, track.y, floor_x - track.x, track.height)
      # The mock's 135° hatch: equal 6 px bands of two reds, measured across the stripes.
      draw.fill(zone, T.DANGER_STRIPE, track.height / 2)
      band = T.px(6)
      step = band * 2 * math.sqrt(2)   # 12 px across the stripes is this far along the track at 45°
      rl.begin_scissor_mode(int(zone.x), int(zone.y), int(zone.width), int(zone.height))
      x = zone.x - zone.height - step
      while x < zone.x + zone.width + step:
        rl.draw_line_ex(rl.Vector2(x, zone.y + zone.height), rl.Vector2(x + zone.height, zone.y), band, T.DANGER_SURFACE)
        x += step
      rl.end_scissor_mode()
      start = floor_x
    thumb_x = self.x_for(self.value)
    ink = T.ACCENT if self.enabled else T.TEXT_MUTED
    fill = rl.Rectangle(start, track.y, max(0.0, thumb_x - start), track.height)
    draw.fill(fill, ink, track.height / 2)
    if start > track.x and fill.width > track.height / 2:   # square where it meets the safety floor, as in the mock
      draw.fill(rl.Rectangle(start, track.y, track.height / 2, track.height), ink)

    if self._floor_label and self._floor is not None:
      draw.text(rl.Rectangle(track.x, rect.y, rect.width, T.px(18)), self._floor_label, T.SIZE_CAPTION, T.DANGER_TEXT, T.FONT_SEMIBOLD)
    elif self._default is not None:
      draw.caption(rl.Rectangle(self.x_for(self._default) - T.px(60), rect.y, T.px(120), T.px(14)), N_("Default"), h=Align.CENTER)
    for value, label in self.merged_marks():
      x = self.x_for(value)
      rl.draw_rectangle_rec(rl.Rectangle(x - 1, track.y + track.height + T.px(6), 2, T.px(8)), T.TEXT_MUTED)
      w = draw.text_width(label, T.SIZE_CAPTION, T.FONT) + T.px(4)
      lx = min(max(x - w / 2, rect.x), rect.x + rect.width - w)   # keep "Quiet" and "Loud" inside at the ends
      draw.text(rl.Rectangle(lx, track.y + track.height + T.px(16), w, T.px(16)), label, T.SIZE_CAPTION, T.TEXT_MUTED, h=Align.CENTER)

    r = T.px(16)
    rl.draw_circle_v(rl.Vector2(thumb_x, track.y + track.height / 2), r, T.ACCENT)
    rl.draw_circle_v(rl.Vector2(thumb_x, track.y + track.height / 2), r - T.px(4), T.TEXT)


# ── Badge, Chip, Progress ──

class Badge(Component):
  """ACTIVE / OVERRIDE / DEFAULT / LEARNED labels."""

  def __init__(self, label: Bindable[str], tone: Bindable[Tone] = Tone.NEUTRAL, solid: bool = False):
    """solid fills with the accent itself (the ACTIVE badge on an active card)."""
    super().__init__()
    self._label = label
    self._tone = tone
    self._solid = solid

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return draw.text_width(resolve(self._label).upper(), T.SIZE_BADGE, T.FONT_BOLD) + T.px(20), T.px(26)

  def _render(self, rect: rl.Rectangle):
    tone = resolve(self._tone)
    draw.fill(rect, T.ACCENT if self._solid else _TONE_COLORS[tone][0], T.RADIUS_BADGE)
    draw.text(rect, resolve(self._label).upper(), T.SIZE_BADGE, T.ACCENT_INK if self._solid else _TONE_INK[tone], T.FONT_BOLD, Align.CENTER)


class Chip(Component):
  """Status chips ("Slowing for curve") and inline statuses ("Offline maps ready")."""

  def __init__(self, label: Bindable[str], tone: Bindable[Tone] = Tone.ACCENT, glyph: Glyph | None = None,
               height: float = T.STATUS_CHIP_HEIGHT, font_size: int = T.font_px(17)):
    super().__init__()
    self._label = label
    self._tone = tone
    self._glyph = glyph
    self._height = height
    self._font_size = font_size

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    glyph = (self._height * 0.5 + T.px(10)) if self._glyph else 0
    return min(max_width, draw.text_width(resolve(self._label), self._font_size, T.FONT_SEMIBOLD) + glyph + T.px(28)), self._height

  def _render(self, rect: rl.Rectangle):
    tone = resolve(self._tone)
    surface, ink = _TONE_COLORS[tone]
    draw.fill(rect, surface, T.px(14))
    content = inset(rect, x=T.px(14))
    if self._glyph:
      size = self._height * 0.5
      self._glyph(rl.Rectangle(content.x, content.y, size, content.height), _TONE_INK[tone], size)
      content = inset(content, left=size + T.px(10))
    draw.text(content, resolve(self._label), self._font_size, ink, T.FONT_SEMIBOLD)


class ProgressBar(Component):
  def __init__(self, progress: Bindable[float], color: rl.Color = T.ACCENT, height: float = T.px(10)):
    super().__init__()
    self._progress = progress
    self._color = color
    self._height = height

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, self._height

  def _render(self, rect: rl.Rectangle):
    bar = place(rect, rect.width, self._height, v=Align.CENTER)
    draw.fill(bar, T.TRACK, bar.height / 2)
    done = min(1.0, max(0.0, float(resolve(self._progress))))
    if done > 0:
      draw.fill(rl.Rectangle(bar.x, bar.y, bar.width * done, bar.height), self._color, bar.height / 2)
