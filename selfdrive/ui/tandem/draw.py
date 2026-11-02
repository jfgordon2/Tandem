"""Drawing primitives shared by every Essentials component."""
from __future__ import annotations

import math
from pathlib import Path

import pyray as rl

from openpilot.system.ui.lib import application
from openpilot.system.ui.lib.application import FONT_SCALE, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.lib.wrap_text import wrap_text
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.fonts import Face, font
from openpilot.selfdrive.ui.tandem.layout import Align, place

SEGMENTS = 16
ELLIPSIS = "…"


def alpha(color: rl.Color, factor: float) -> rl.Color:
  return rl.Color(color.r, color.g, color.b, int(color.a * factor))


def _roundness(rect: rl.Rectangle, radius: float) -> float:
  short = min(rect.width, rect.height)
  return 0.0 if short <= 0 or radius <= 0 else min(1.0, 2 * radius / short)


def fill(rect: rl.Rectangle, color: rl.Color, radius: float = 0) -> None:
  if radius <= 0:
    rl.draw_rectangle_rec(rect, color)
  else:
    rl.draw_rectangle_rounded(rect, _roundness(rect, radius), SEGMENTS, color)


def stroke(rect: rl.Rectangle, color: rl.Color, radius: float = 0, width: float = T.DIVIDER) -> None:
  """An outline inside rect, as a CSS border is. raylib draws its lines outside the rectangle it's given, which would make
  outlined cards bigger than their fill and get clipped at the edge of a scrolling list."""
  inner = rl.Rectangle(rect.x + width, rect.y + width, rect.width - width * 2, rect.height - width * 2)
  rl.draw_rectangle_rounded_lines_ex(inner, _roundness(inner, max(0.0, radius - width)), SEGMENTS, width, color)


def lerp(a: rl.Color, b: rl.Color, t: float) -> rl.Color:
  """The color t of the way from a to b."""
  t = max(0.0, min(1.0, t))
  return rl.Color(*(round(x + (y - x) * t) for x, y in ((a.r, b.r), (a.g, b.g), (a.b, b.b), (a.a, b.a))))


def gradient_v(rect: rl.Rectangle, top: rl.Color, bottom: rl.Color) -> None:
  rl.draw_rectangle_gradient_v(int(rect.x), int(rect.y), int(rect.width), int(rect.height), top, bottom)


GLOW_HEIGHT = T.px(40)


def _corner_inset(radius: float, d: float) -> float:
  """How far a rounded corner of radius cuts into a row d pixels from the edge it rounds."""
  if d >= radius:
    return 0.0
  return radius - math.sqrt(max(0.0, radius * radius - (radius - d) ** 2))


def _edge_glow(rect: rl.Rectangle, top: bool, radius: float) -> None:
  """The glow along one edge, the pane's full width; where that edge has rounded corners, each row follows the curve."""
  edge, clear = alpha(T.ACCENT, 0.32), alpha(T.ACCENT, 0.0)
  height = GLOW_HEIGHT
  curved = min(radius, height)
  # Past the corners: one gradient across the full width
  if top:
    gradient_v(rl.Rectangle(rect.x, rect.y + curved, rect.width, height - curved), lerp(edge, clear, curved / height), clear)
  else:
    gradient_v(rl.Rectangle(rect.x, rect.y + rect.height - height, rect.width, height - curved), clear,
               lerp(edge, clear, curved / height))
  # Through the corners: a line per pixel row, narrowed to the curve
  for d in range(int(curved)):
    x = _corner_inset(radius, d + 0.5)
    y = rect.y + d if top else rect.y + rect.height - 1 - d
    color = lerp(edge, clear, d / height)
    if d < T.px(2):
      color = alpha(T.ACCENT, 0.6)
    rl.draw_rectangle(int(rect.x + x), int(y), int(rect.width - 2 * x), 1, color)
  if curved < T.px(2):   # a straight edge: the bright line along it
    y = rect.y if top else rect.y + rect.height - T.px(2)
    fill(rl.Rectangle(rect.x, y, rect.width, T.px(2)), alpha(T.ACCENT, 0.6), T.px(1))


def scroll_glow(rect: rl.Rectangle, offset: float, content: float, round_top: float = 0.0, round_bottom: float = 0.0) -> None:
  """A soft accent glow at each edge of a scrolling list that has more past it: the top once scrolled down, the bottom
  while there's more below. offset is the scroll offset (0 or less) and content the list's full height. round_top and
  round_bottom are the corner radii where the list's edge is also its pane's rounded edge (0 where it meets a header or
  footer), so the glow spans the pane and follows its corners."""
  if offset < -0.5:
    _edge_glow(rect, True, round_top)
  if content + offset > rect.height + 0.5:
    _edge_glow(rect, False, round_bottom)


def hline(x: float, y: float, width: float, color: rl.Color = T.CONTROL) -> None:
  rl.draw_rectangle_rec(rl.Rectangle(x, y, width, T.DIVIDER), color)


def pressed(rect: rl.Rectangle, radius: float = 0) -> None:
  fill(rect, T.PRESSED_OVERLAY, radius)


# ── Text ──

class _OwnFont:
  """Tandem's text is English (it doesn't go through StarPilot's translations), so it keeps Figtree when the language
  picked needs unifont: upstream's font_fallback is off just while these functions measure and draw it."""

  depth = 0   # nesting-safe: the flag goes back to off only when the outermost use ends

  def __enter__(self):
    _OwnFont.depth += 1
    application.KEEP_FONT = True

  def __exit__(self, *_):
    _OwnFont.depth -= 1
    if not _OwnFont.depth:
      application.KEEP_FONT = False


_own_font = _OwnFont()


def text_width(text: str, size: int, weight: Face = T.FONT, tracking: float = 0) -> float:
  with _own_font:
    return measure_text_cached(font(weight), text, size, tracking).x


def line_height(size: int) -> float:
  return size * FONT_SCALE


def fit(text: str, size: int, weight: Face, max_width: float, tracking: float = 0) -> str:
  max_width += 0.5  # layout math leaves float error; text measured for a rect must still fit in it
  if text_width(text, size, weight, tracking) <= max_width:
    return text
  while text and text_width(text + ELLIPSIS, size, weight, tracking) > max_width:
    text = text[:-1]
  return text.rstrip() + ELLIPSIS if text else ""


def text(rect: rl.Rectangle, value: str, size: int, color: rl.Color, weight: Face = T.FONT,
         h: Align = Align.START, v: Align = Align.CENTER, tracking: float = 0, elide: bool = True) -> float:
  """Draw one line inside rect. Returns the drawn width."""
  if elide:
    value = fit(value, size, weight, rect.width, tracking)
  width = text_width(value, size, weight, tracking)
  box = place(rect, width, line_height(size), h, v)
  with _own_font:
    rl.draw_text_ex(font(weight), value, rl.Vector2(round(box.x), round(box.y)), size, tracking, color)
  return width


def caption(rect: rl.Rectangle, value: str, color: rl.Color = T.TEXT_MUTED, h: Align = Align.START, v: Align = Align.CENTER) -> float:
  """Section labels: small bold capitals with tracking."""
  return text(rect, value.upper(), T.SIZE_CAPTION, color, T.FONT_BOLD, h, v, tracking=T.CAPTION_TRACKING)


def paragraph_lines(value: str, size: int, weight: Face, width: float) -> list[str]:
  with _own_font:
    return wrap_text(font(weight), value, size, int(width))


def paragraph_height(value: str, size: int, weight: Face, width: float, spacing: float = 1.3) -> float:
  return len(paragraph_lines(value, size, weight, width)) * line_height(size) * spacing


def paragraph(rect: rl.Rectangle, value: str, size: int, color: rl.Color, weight: Face = T.FONT, spacing: float = 1.3,
              max_lines: int | None = None) -> float:
  """Wrapped text from the top of rect. Returns the height used. With max_lines, the last line ends in an ellipsis
  when the text would run longer."""
  y = rect.y
  step = line_height(size) * spacing
  lines = paragraph_lines(value, size, weight, rect.width)
  if max_lines is not None and len(lines) > max_lines:
    lines = lines[:max_lines - 1] + [fit(" ".join(lines[max_lines - 1:]) + ELLIPSIS, size, weight, rect.width)]
  for line in lines:
    with _own_font:
      rl.draw_text_ex(font(weight), line, rl.Vector2(round(rect.x), round(y)), size, 0, color)
    y += step
  return y - rect.y


# ── Icons ──
# Line icons from the design mocks, rasterized to white PNGs in icons/ (tools/build_icons.js) and tinted here.
# size is the icon's box, as the mocks size their SVGs; the strokes keep the mock's weight at any size.

ICON_DIR = Path(__file__).resolve().parent / "icons"
MIRRORED = {"lane_left": "lane_right", "turn_left": "turn_right", "signal_right": "signal"}   # drawn from another icon, flipped


def icon(rect: rl.Rectangle, name: str, color: rl.Color, size: float) -> None:
  """A mock icon by name (icons/svg/<name>.svg), tinted and centered in rect."""
  flip = name in MIRRORED
  texture = gui_app.texture((ICON_DIR / f"{MIRRORED.get(name, name)}.png").as_posix(), int(size), int(size), flip_x=flip)
  box = place(rect, texture.width, texture.height)
  rl.draw_texture_pro(texture, rl.Rectangle(0, 0, texture.width, texture.height), rl.Rectangle(round(box.x), round(box.y), texture.width,
                      texture.height), rl.Vector2(0, 0), 0, color)


def chevron(rect: rl.Rectangle, color: rl.Color, size: float, direction: str = "right") -> None:
  icon(rect, "chevron" if direction == "right" else "back", color, size)


def cross(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  icon(rect, "close", color, size)


def plus(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  icon(rect, "plus", color, size)


def minus(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  box = place(rect, size * 0.58, size)   # the plus icon's bar, which has no icon of its own
  w = max(2.0, size / 12)
  ends = rl.Vector2(box.x, box.y + size / 2), rl.Vector2(box.x + box.width, box.y + size / 2)
  rl.draw_line_ex(*ends, w, color)
  for end in ends:
    rl.draw_circle_v(end, w / 2, color)


def check(rect: rl.Rectangle, color: rl.Color, size: float) -> None:
  icon(rect, "check", color, size)


def disc(center: rl.Vector2, radius: float, color: rl.Color) -> None:
  """A filled circle, e.g. the voice typing mic and its halo."""
  rl.draw_circle_v(center, radius, color)


def arc(center: rl.Vector2, radius: float, width: float, start: float, end: float, color: rl.Color) -> None:
  """A ring segment of the given stroke width, angles in degrees clockwise from 3 o'clock, with round ends (a spinner)."""
  rl.draw_ring(center, radius - width / 2, radius + width / 2, start, end, 48, color)
  for angle in (start, end):
    a = math.radians(angle)
    rl.draw_circle_v(rl.Vector2(center.x + radius * math.cos(a), center.y + radius * math.sin(a)), width / 2, color)
