"""One line of text that scrolls when it doesn't fit, as the street name and turn instruction do in the onroad mocks.

Text that fits is drawn still. Text that doesn't rests at its start, slides left until its end shows, rests, then fades
out and starts again, with a soft fade along the right edge while more is hidden. With Reduce Motion (size.py) it is cut
with an ellipsis instead.

The onroad layers draw inside the road view's clip (view.py), and raylib can't nest clip regions, so a scrolling line
clips to itself and then restores `outer`: pass the road view's rectangle.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from collections.abc import Callable
from typing import TYPE_CHECKING

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw
from openpilot.selfdrive.ui.tandem.layout import Align, place
from openpilot.selfdrive.ui.tandem.onroad import size as Z

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.tandem.fonts import Face

REST_S = 2.5     # at the start, and again at the end
SPEED = 40       # mock px a second
FADE_S = 0.4     # out at the end of each pass
EDGE = 28        # the right edge's fade, mock px


@dataclass(frozen=True)
class Pass:
  """Where a scrolling line is t seconds into its loop: how far it has moved and how visible it is."""
  offset: float
  alpha: float


def timing(shift: float, speed: float) -> tuple[float, float]:
  """(seconds sliding, seconds a whole pass takes) for a line that must move shift px."""
  slide = shift / speed
  return slide, REST_S + slide + REST_S + FADE_S


def at(t: float, shift: float, speed: float) -> Pass:
  """Where a scrolling line is at time t: resting at the start, sliding, resting at the end, then fading out.

  Args:
    t: Seconds since the line started.
    shift: How far the line has to move, in px.
    speed: Its sliding speed, in px a second.
  """
  slide, loop = timing(shift, speed)
  t %= loop
  if t < REST_S:
    return Pass(0.0, 1.0)
  t -= REST_S
  if t < slide:
    u = t / slide
    return Pass(shift * u * u * (3 - 2 * u), 1.0)   # eased at both ends
  t -= slide
  if t < REST_S:
    return Pass(shift, 1.0)
  return Pass(shift, max(0.0, 1.0 - (t - REST_S) / FADE_S))


class Scroller:
  """Draws one line in a rect, scrolling it when needed. Keep one per line on screen: it times its own loop and starts
  again from the beginning when the text changes."""

  def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
    self._clock = clock
    self._text = ""
    self._since = 0.0

  def pass_seconds(self, text: str, width: float, size: int, weight: Face) -> float:
    """How long one pass takes for text in width, or 0 when it fits (or Reduce Motion keeps it still)."""
    over = draw.text_width(text, size, weight) - width
    if over <= 0 or Z.reduce_motion():
      return 0.0
    return timing(over + Z.px(EDGE), Z.px(SPEED))[1]

  def draw(self, rect: rl.Rectangle, text: str, size: int, color: rl.Color, weight: Face, outer: rl.Rectangle,
           h: Align = Align.START, fade: rl.Color | None = None) -> float:
    """Draws text in rect, scrolling it when it doesn't fit.

    Args:
      rect: Where the line goes.
      text: The line.
      size: The text size.
      color: The text color.
      weight: The face.
      outer: The clip for the scrolling text.
      h: Where text that fits sits.
      fade: The color behind the text, for the right edge's fade.

    Returns:
      The drawn width.
    """
    now = self._clock()
    if text != self._text:
      self._text, self._since = text, now
    full = draw.text_width(text, size, weight)
    if full <= rect.width + 0.5 or Z.reduce_motion():
      return draw.text(rect, text, size, color, weight, h)
    edge = Z.px(EDGE)
    shift = full - rect.width + edge
    step = at(now - self._since, shift, Z.px(SPEED))
    ink = draw.alpha(color, step.alpha)
    clip = _intersect(rect, outer)
    rl.end_scissor_mode()
    rl.begin_scissor_mode(int(clip.x), int(clip.y), int(clip.width), int(clip.height))
    try:
      line = place(rl.Rectangle(rect.x - step.offset, rect.y, full, rect.height), full, rect.height)
      draw.text(line, text, size, ink, weight, elide=False)
      if fade is not None and step.offset < shift - 0.5:
        rl.draw_rectangle_gradient_h(int(rect.x + rect.width - edge), int(rect.y), edge, int(rect.height), draw.alpha(fade, 0.0), fade)
    finally:
      rl.end_scissor_mode()
      rl.begin_scissor_mode(int(outer.x), int(outer.y), int(outer.width), int(outer.height))
    return rect.width


def _intersect(a: rl.Rectangle, b: rl.Rectangle) -> rl.Rectangle:
  x, y = max(a.x, b.x), max(a.y, b.y)
  return rl.Rectangle(x, y, max(0.0, min(a.x + a.width, b.x + b.width) - x), max(0.0, min(a.y + a.height, b.y + b.height) - y))
