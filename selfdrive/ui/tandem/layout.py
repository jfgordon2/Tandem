"""Rectangle math for laying out components. Nothing here draws."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

import pyray as rl


class Align(IntEnum):
  """Where a box sits along one axis of the rect it's placed in."""
  START = 0
  CENTER = 1
  END = 2


@dataclass(frozen=True)
class Fill:
  """A share of the space left after fixed sizes and gaps, split by weight."""
  weight: float = 1.0


FILL = Fill()

Size = float | Fill


def inset(rect: rl.Rectangle, amount: float = 0, *, x: float | None = None, y: float | None = None,
          left: float | None = None, top: float | None = None, right: float | None = None, bottom: float | None = None) -> rl.Rectangle:
  left = left if left is not None else (x if x is not None else amount)
  right = right if right is not None else (x if x is not None else amount)
  top = top if top is not None else (y if y is not None else amount)
  bottom = bottom if bottom is not None else (y if y is not None else amount)
  return rl.Rectangle(rect.x + left, rect.y + top, max(0.0, rect.width - left - right), max(0.0, rect.height - top - bottom))


def split(rect: rl.Rectangle, sizes: Sequence[Size], gap: float = 0, horizontal: bool = True) -> list[rl.Rectangle]:
  """Cut rect into consecutive pieces along one axis. Fixed sizes come first; Fill pieces share what's left."""
  total = rect.width if horizontal else rect.height
  fixed = sum(s for s in sizes if not isinstance(s, Fill))
  weights = sum(s.weight for s in sizes if isinstance(s, Fill))
  free = max(0.0, total - fixed - gap * max(0, len(sizes) - 1))

  rects = []
  pos = rect.x if horizontal else rect.y
  for s in sizes:
    length = free * s.weight / weights if isinstance(s, Fill) else s
    if horizontal:
      rects.append(rl.Rectangle(pos, rect.y, length, rect.height))
    else:
      rects.append(rl.Rectangle(rect.x, pos, rect.width, length))
    pos += length + gap
  return rects


def row(rect: rl.Rectangle, sizes: Sequence[Size], gap: float = 0) -> list[rl.Rectangle]:
  return split(rect, sizes, gap, horizontal=True)


def column(rect: rl.Rectangle, sizes: Sequence[Size], gap: float = 0) -> list[rl.Rectangle]:
  return split(rect, sizes, gap, horizontal=False)


def grid(rect: rl.Rectangle, columns: int, rows: int, gap: float = 0) -> list[rl.Rectangle]:
  """Equal cells, left to right then top to bottom."""
  return [cell for line in column(rect, [FILL] * rows, gap) for cell in row(line, [FILL] * columns, gap)]


def place(rect: rl.Rectangle, width: float, height: float, h: Align = Align.CENTER, v: Align = Align.CENTER) -> rl.Rectangle:
  """A width x height box positioned inside rect."""
  x = rect.x + (rect.width - width) * h / 2
  y = rect.y + (rect.height - height) * v / 2
  return rl.Rectangle(x, y, width, height)


def grow(rect: rl.Rectangle, min_width: float, min_height: float) -> rl.Rectangle:
  """Expand rect around its center to at least the given size (touch targets)."""
  width, height = max(rect.width, min_width), max(rect.height, min_height)
  return rl.Rectangle(rect.x - (width - rect.width) / 2, rect.y - (height - rect.height) / 2, width, height)
