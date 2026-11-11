"""The base every Tandem component builds on: values that can be bound to a getter, and a widget with a preferred size.

Components take a ``Bindable`` wherever a value may change while the screen is up, such as a row's subtitle that reads
Params, and call ``resolve`` as they draw, so nothing has to be pushed to them.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeAlias, TypeVar

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.layout import grow

V = TypeVar("V")
Bindable: TypeAlias = V | Callable[[], V]   # a value, or a function returning it, read each frame


def resolve(value: Bindable[V]) -> V:
  """Components take either a value or a getter, so rows can read Params every frame."""
  # raylib structs (colors, rectangles) report callable() but are values
  return value() if callable(value) and not isinstance(value, rl.ffi.CData) else value


def size_of(widget: Widget, max_width: float) -> tuple[float, float]:
  """Preferred size for Essentials components, current size for any other Widget."""
  return widget.preferred_size(max_width) if isinstance(widget, Component) else (widget.rect.width, widget.rect.height)


class Component(Widget):
  """Widget plus a preferred size, so containers can lay children out without hard-coded heights."""

  # Controls smaller than MIN_TOUCH still accept touches across MIN_TOUCH; containers turn this off.
  grow_touch_target = True

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self._rect.width, self._rect.height

  def preferred_height(self, width: float) -> float:
    return self.preferred_size(width)[1]

  @property
  def _hit_rect(self) -> rl.Rectangle:
    rect = grow(self._rect, T.MIN_TOUCH, T.MIN_TOUCH) if self.grow_touch_target else self._rect
    return rect if self._parent_rect is None else rl.get_collision_rec(rect, self._parent_rect)
