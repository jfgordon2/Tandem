"""The approved bottom bar with independent cruise and disengage permissions."""
from __future__ import annotations

from collections.abc import Callable

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.onroad import size as Z
from openpilot.selfdrive.ui.tandem.onroad.scroll import Scroller
from openpilot.selfdrive.ui.tandem.onroad.state import BarState
from openpilot.starpilot.ui.raylib import rl


def bar_height() -> int:
  return Z.px(74)


def bar_margin() -> int:
  return Z.px(14)


class OnroadBar(Component):
  """Menu, MAX, street name and the qualified disengage button."""

  grow_touch_target = False

  def __init__(self, state: Callable[[], BarState], on_menu: Callable[[], None], on_speed: Callable[[int], None],
               on_disengage: Callable[[], None]):
    super().__init__()
    self._state = state
    self._menu = self._child(Button(on_click=on_menu, style=ButtonStyle.GHOST,
                                    glyph=lambda rect, color, size: draw.icon(rect, "menu", T.TEXT, Z.px(28))))
    self._minus = self._child(Button(on_click=lambda: on_speed(-1), style=ButtonStyle.GHOST,
                                     glyph=lambda rect, color, size: draw.minus(rect, T.TEXT, Z.px(18))))
    self._plus = self._child(Button(on_click=lambda: on_speed(1), style=ButtonStyle.GHOST,
                                    glyph=lambda rect, color, size: draw.plus(rect, T.TEXT, Z.px(18))))
    self._wheel = self._child(Button(on_click=on_disengage, style=ButtonStyle.GHOST,
                                     glyph=lambda rect, color, size: draw.icon(rect, "wheel", T.TEXT, Z.px(32))))
    self._wheel.set_enabled(lambda: self._state().disengage)
    for step in (self._minus, self._plus):
      step.set_enabled(lambda: self._state().adjust_speed)
      step.set_visible(lambda: self._state().adjust_speed)
    self._street = Scroller()

  def rects(self, rect: rl.Rectangle) -> tuple[rl.Rectangle, rl.Rectangle, rl.Rectangle, rl.Rectangle]:
    """The four bottom-bar tiles. A read-only MAX uses a narrower tile."""
    h, m = bar_height(), bar_margin()
    body = rl.Rectangle(rect.x + m, rect.y + rect.height - m - h, rect.width - m * 2, h)
    menu, cruise, street, wheel = row(body, [h, Z.px(194 if self._state().adjust_speed else 96), FILL, h], Z.px(12))
    return menu, cruise, street, wheel

  def _render(self, rect: rl.Rectangle) -> None:
    state = self._state()
    menu, cruise, street, wheel = self.rects(rect)
    radius = Z.px(18)
    for tile in (menu, cruise, street):
      draw.fill(tile, T.ONROAD_CONTROL, radius)
    self._menu.render(menu)
    value = cruise
    if state.adjust_speed:
      minus, value, plus = row(cruise, [Z.px(56), FILL, Z.px(56)])
      for control, box in ((self._minus, minus), (self._plus, plus)):
        control.restyle(box.height, Z.font_px(28), Z.px(9), radius)
        control.render(box)
    tag, number = column(place(value, value.width, Z.px(48)), [Z.px(16), FILL], Z.px(2))
    draw.text(tag, N_("MAX"), Z.font_px(12), T.ACCENT_TEXT, T.FONT_BOLD, Align.CENTER)
    draw.text(number, "–" if state.set_speed is None else f"{round(state.set_speed)}",
              Z.font_px(30), T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)
    if state.street:
      text = inset(street, x=Z.px(20))
      width = min(text.width, draw.text_width(state.street, Z.font_px(28), T.FONT_BOLD))
      self._street.draw(place(text, width, text.height), state.street, Z.font_px(28), T.TEXT, T.FONT_BOLD, rect, fade=T.ONROAD_CONTROL)
    draw.fill(wheel, T.SUCCESS if state.engaged else T.ONROAD_CONTROL, radius)
    if state.disengage:
      self._wheel.render(wheel)
    else:
      draw.icon(wheel, "wheel", T.TEXT if state.engaged else T.TEXT_MUTED, Z.px(32))
