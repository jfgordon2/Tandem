"""The number editor sheet: big value with − and +, a slider with the default marked, quick picks, and reset."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle, Chip, Slider, Stepper, Tone
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, place, row
from openpilot.selfdrive.ui.tandem.overlays import Sheet
from openpilot.selfdrive.ui.tandem.i18n import N_, t_


@dataclass(frozen=True)
class NumberSpec:
  minimum: float
  maximum: float
  step: float
  default: float
  fmt: Callable[[float], str] = lambda v: f"{v:g}"
  picks: tuple[float, ...] = ()


def split_unit(text: str) -> tuple[str, str]:
  """ "0.80 m/s²" → ("0.80", "m/s²"); "+3" → ("+3", "")."""
  number, _, unit = text.partition(" ")
  return number, unit


class BigStepper(Stepper):
  """The editor's stepper as the mock draws it (design/valueeditor.html): − and + as separate squares, the value large
  between them with its unit below. Hold − or + to repeat."""
  SQUARE = T.px(88)
  VALUE_W = T.px(320)

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return self.SQUARE * 2 + self.VALUE_W + T.px(48), T.px(120)

  def _parts(self) -> list[rl.Rectangle]:
    r = self._rect
    square = lambda x: rl.Rectangle(x, r.y + (r.height - self.SQUARE) / 2, self.SQUARE, self.SQUARE)  # noqa: E731
    return [square(r.x), rl.Rectangle(r.x + self.SQUARE + T.px(24), r.y, self.VALUE_W, r.height),
            square(r.x + r.width - self.SQUARE)]

  def _handle_mouse_press(self, mouse_pos) -> None:
    minus_rect, _, plus_rect = self._parts()
    self._direction = -1 if rl.check_collision_point_rec(mouse_pos, minus_rect) else (
      1 if rl.check_collision_point_rec(mouse_pos, plus_rect) else 0)
    self._repeat_at = rl.get_time() + self.REPEAT_DELAY if self._direction else None
    self._repeated = False

  def _render(self, rect: rl.Rectangle):
    minus_rect, value_rect, plus_rect = self._parts()
    ink = T.TEXT if self.enabled else T.TEXT_MUTED
    for r, d in ((minus_rect, -1), (plus_rect, 1)):
      draw.fill(r, T.CONTROL, T.px(20))
      if self.is_pressed and self._direction == d:
        draw.pressed(r, T.px(20))
      glyph_ink = T.TEXT_MUTED if self.stepped(d) == self.value else ink
      (draw.minus if d < 0 else draw.plus)(r, glyph_ink, T.px(30))
    number, unit = split_unit(self._fmt(self.value))
    size = T.font_px(64)
    if unit:
      top, bottom = column(place(value_rect, value_rect.width, draw.line_height(size) + draw.line_height(T.font_px(18))),
                           [draw.line_height(size), draw.line_height(T.font_px(18))])
      draw.text(top, number, size, ink, T.FONT_EXTRABOLD, Align.CENTER)
      draw.text(bottom, unit, T.font_px(18), T.TEXT_SECONDARY, T.FONT_MEDIUM, Align.CENTER)
    else:
      draw.text(value_rect, number, size, ink, T.FONT_EXTRABOLD, Align.CENTER)


class NumberEditor(Component):
  grow_touch_target = False

  def __init__(self, spec: NumberSpec, value: Callable[[], float], on_change: Callable[[float], None]):
    super().__init__()
    self._spec = spec
    self._value = value
    s = spec
    self._stepper = self._child(BigStepper(value, on_change, s.minimum, s.maximum, s.step, fmt=s.fmt))
    self._slider = self._child(Slider(value, on_change, s.minimum, s.maximum, s.step, default=s.default,
                                      marks=[(s.minimum, s.fmt(s.minimum)), (s.maximum, s.fmt(s.maximum))]))
    self._picks = [self._child(Chip(s.fmt(p), Tone.NEUTRAL, height=T.px(40), font_size=T.font_px(16))) for p in s.picks]
    for chip, pick in zip(self._picks, s.picks, strict=True):
      chip.set_click_callback(lambda p=pick: on_change(p))
    self._reset = self._child(Button(N_("Reset to default"), lambda: on_change(s.default), ButtonStyle.GHOST, weight=T.FONT_BOLD))

  def preferred_size(self, max_width: float) -> tuple[float, float]:
    return max_width, T.px(120) + self._slider.preferred_height(max_width) + T.px(120)

  def step_note(self) -> str:
    unit = split_unit(self._spec.fmt(self._spec.default))[1]
    return t_("Steps of {}{}. Hold − or + to move faster.", f"{self._spec.step:g}", ' ' + unit if unit else '')

  def _render(self, rect: rl.Rectangle):
    top, slider, bottom = column(rect, [T.px(120), self._slider.preferred_height(rect.width), FILL], T.px(18))
    w, h = self._stepper.preferred_size(rect.width)
    self._stepper.render(rl.Rectangle(top.x + (top.width - w) / 2, top.y, w, h))
    self._slider.render(slider)
    picks, reset = row(column(bottom, [T.BUTTON_HEIGHT, FILL])[0], [FILL, self._reset.preferred_size(rect.width)[0]])
    x = picks.x
    if self._picks:
      label_w = draw.text(picks, N_("Quick picks"), T.SIZE_SUBTITLE, T.TEXT_MUTED)
      x += label_w + T.px(14)
    for chip in self._picks:
      cw, ch = chip.preferred_size(picks.width)
      chip.render(rl.Rectangle(x, picks.y + (picks.height - ch) / 2, cw, ch))
      x += cw + T.px(8)
    note = rl.Rectangle(x + T.px(16), reset.y, reset.x - x - T.px(32), reset.height)
    draw.text(note, draw.fit(self.step_note(), T.SIZE_SUBTITLE, T.FONT, note.width), T.SIZE_SUBTITLE, T.TEXT_TERTIARY, h=Align.END)
    self._reset.render(reset)


def number_sheet(window, title: str, subtitle: str, spec: NumberSpec, value: Callable[[], float],
                 on_change: Callable[[float], None]) -> Sheet:
  return Sheet(title, NumberEditor(spec, value, on_change), subtitle=subtitle,
               actions=[Button(N_("Done"), window.dismiss, ButtonStyle.PRIMARY)], on_dismiss=window.dismiss)
