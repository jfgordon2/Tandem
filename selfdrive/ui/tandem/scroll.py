"""Tandem gesture rejection; upstream's scroll panel retains its original behavior."""
from typing import Any

import pyray as rl

from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2, ScrollState
from openpilot.system.ui.lib.application import MouseEvent


class ScrollPanel(GuiScrollPanel2):
  """Upstream's scroll panel, except a touch that scrolled the list doesn't also tap what it lifted over."""

  def __init__(self, *args: Any, **kwargs: Any) -> None:
    super().__init__(*args, **kwargs)
    self._touch_scrolled = False

  def _handle_mouse_event(self, event: MouseEvent, bounds: rl.Rectangle, bounds_size: float, content_size: float) -> None:
    if event.left_pressed:
      self._touch_scrolled = False
      self._snap_target = None
    if content_size <= bounds_size:
      self._touch_scrolled = False
    if self.state == ScrollState.AUTO_SCROLL and event.left_pressed and not rl.check_collision_point_rec(event.pos, bounds):
      event = event._replace(left_pressed=False)
    super()._handle_mouse_event(event, bounds, bounds_size, content_size)
    if self.state == ScrollState.MANUAL_SCROLL:
      self._touch_scrolled = True

  def is_touch_valid(self) -> bool:
    return super().is_touch_valid() and not self._touch_scrolled
