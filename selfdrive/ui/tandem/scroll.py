"""Tandem gesture rejection; upstream's scroll panel retains its original behavior."""
import pyray as rl

from openpilot.system.ui.lib.scroll_panel2 import GuiScrollPanel2, ScrollState


class ScrollPanel(GuiScrollPanel2):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._touch_scrolled = False

  def _handle_mouse_event(self, event, bounds, bounds_size, content_size):
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
