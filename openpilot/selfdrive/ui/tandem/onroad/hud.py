"""Tandem's speed, speed limit and driver monitoring layers."""
from __future__ import annotations

import math
from collections.abc import Callable

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.i18n import N_, t_
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.onroad import size as Z
from openpilot.selfdrive.ui.tandem.onroad.state import Chip, ChipTone, LimitOffer
from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem.onroad.bar import bar_height, bar_margin


HUD_PILL = T.ONROAD_CARD
SPEED_UNIT = T.TEXT_SECONDARY
def sign_tile_size() -> tuple[int, int]:
  return Z.px(82), Z.px(98)


def sign_size() -> tuple[int, int]:
  """The US sign inside the tile; the new-limit card draws it at the same size and spot."""
  return Z.px(62), Z.px(78)


def sign_margin() -> int:
  return Z.px(18)


SIGNAL_BRIGHT, SIGNAL_DIM = T.SUCCESS_BRIGHT, rl.Color(0x2A, 0x8F, 0x5E, 255)
def signal_size() -> tuple[int, int]:
  """Both chevrons, as in the onroad mock."""
  return Z.px(46), Z.px(30)


def signal_gap() -> int:
  return Z.px(22)

SIGNAL_STEP = 0.4                    # seconds each chevron leads, so the light steps outward


def draw_signal(rect: rl.Rectangle, side: str, now: float) -> None:
  """Two chevrons pointing the way of the turn. The bright one steps outward, from beside the speed to the edge."""
  w, h = signal_size()
  box = place(rect, w, h)
  stroke = Z.px(5)
  outer_bright = int(now / SIGNAL_STEP) % 2 == 1
  for i, x0 in enumerate((Z.px(18), Z.px(36))):   # the mock's chevron tips: at 8 and 26 of 46, arms out to 18 and 36
    outer = i == 0
    color = SIGNAL_BRIGHT if outer == outer_bright else SIGNAL_DIM
    tip_x, arm_x = x0 - Z.px(10), x0
    if side == "right":
      tip_x, arm_x = w - tip_x, w - arm_x
    tip = rl.Vector2(box.x + tip_x, box.y + h / 2)
    for arm in (rl.Vector2(box.x + arm_x, box.y + h / 2 - Z.px(10)), rl.Vector2(box.x + arm_x, box.y + h / 2 + Z.px(10))):
      rl.draw_line_ex(arm, tip, stroke, color)
      rl.draw_circle_v(arm, stroke / 2, color)
    rl.draw_circle_v(tip, stroke / 2, color)


def draw_speed(rect: rl.Rectangle, speed: float | None, unit: str, offset_y: float = 0.0, left: bool = False, right: bool = False,
               now: float = 0.0) -> None:
  """The current speed, top center on a dark pill. A blinker adds our turn signal on its side; the number stays centered."""
  number, size = ("–" if speed is None else f"{round(speed)}"), Z.font_px(62)
  lines = [draw.line_height(size), draw.line_height(Z.font_px(17))]
  w = max(draw.text_width(number, size, T.FONT_EXTRABOLD), draw.text_width(unit, Z.font_px(17))) + Z.px(80)
  h = sum(lines) + Z.px(20) - Z.px(6)
  center = rl.Rectangle(rect.x + (rect.width - w) / 2, rect.y + Z.px(16) + offset_y, w, h)
  extra = signal_size()[0] + signal_gap() - Z.px(10)   # the mock's pill is 10 px tighter on the signal side
  pill = rl.Rectangle(center.x - (extra if left else 0), center.y, w + (extra if left else 0) + (extra if right else 0), h)
  draw.fill(pill, HUD_PILL, Z.px(22))
  value, label = column(inset(center, y=Z.px(10)), [lines[0] - Z.px(6), lines[1]])
  draw.text(value, number, size, T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(label, unit, Z.font_px(17), SPEED_UNIT, h=Align.CENTER)
  for side, on in (("left", left), ("right", right)):
    if on:
      x = pill.x + Z.px(30) if side == "left" else pill.x + pill.width - Z.px(30) - signal_size()[0]
      draw_signal(rl.Rectangle(x, pill.y, signal_size()[0], pill.height), side, now)


def sign_tile(rect: rl.Rectangle) -> rl.Rectangle:
  """Where the speed limit sign sits: top left."""
  return rl.Rectangle(rect.x + sign_margin(), rect.y + sign_margin(), *sign_tile_size())


def draw_speed_limit(tile: rl.Rectangle, limit: str, vienna: bool) -> None:
  """The posted limit on a dark tile.

  Args:
    tile: The tile.
    limit: The limit, formatted.
    vienna: Draw a round Vienna Convention sign instead of a U.S. one.
  """
  draw.fill(tile, T.SCRIM, Z.px(14))
  draw_sign(place(tile, *sign_size()), limit, vienna)


def draw_sign(area: rl.Rectangle, limit: str, vienna: bool) -> None:
  """Draw a US sign or the Vienna Convention red ring in the same tile."""
  if vienna:
    sign = place(area, Z.px(72), Z.px(72))
    draw.fill(sign, T.DANGER, sign.width / 2)
    draw.fill(inset(sign, Z.px(8)), rl.WHITE, sign.width / 2)
    draw.text(sign, limit, Z.font_px(28), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
    return
  sign = area
  draw.fill(sign, rl.WHITE, Z.px(8))
  draw.stroke(inset(sign, Z.px(2)), T.BG, Z.px(7), Z.px(3))
  body = inset(sign, x=Z.px(5), y=Z.px(9))
  top, middle, number = column(body, [Z.px(12), Z.px(12), FILL])
  draw.text(top, "SPEED", Z.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)   # the US sign's own words: never translated
  draw.text(middle, "LIMIT", Z.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(number, limit, Z.font_px(32), T.BG, T.FONT_EXTRABOLD, Align.CENTER)


def dm_tile_size() -> int:
  return Z.px(64)


def dm_ring() -> tuple[int, int]:
  """The ring's diameter and width."""
  return Z.px(50), Z.px(3)


def dm_tile(rect: rl.Rectangle) -> rl.Rectangle:
  """The driver monitor's place: the top right corner, inset like the sign is on the left."""
  t = dm_tile_size()
  return rl.Rectangle(rect.x + rect.width - sign_margin() - t, rect.y + sign_margin(), t, t)


def draw_driver_monitor(tile: rl.Rectangle, opacity: float, attentive: float, watching: bool) -> None:
  """The driver on a dark tile, ringed green while attentive and amber as attention drops.

  Args:
    tile: The tile.
    opacity: The whole tile's opacity.
    attentive: Driver monitoring's awareness, from 0 (not fully aware) to 1.
    watching: Driver monitoring has a camera policy; without one the ring is a quiet track.
  """
  if opacity <= 0.01:
    return
  draw.fill(tile, draw.alpha(T.SCRIM, opacity), Z.px(14))
  ring = place(tile, dm_ring()[0], dm_ring()[0])
  if watching:
    color = mix(T.WARNING, T.SUCCESS_BRIGHT, attentive)
  else:
    color = draw.alpha(T.TEXT, 0.25)
  draw.stroke(ring, draw.alpha(color, opacity), ring.width / 2, dm_ring()[1])
  draw.icon(tile, "driver", draw.alpha(T.TEXT, opacity), Z.px(26))


def mix(a: rl.Color, b: rl.Color, t: float) -> rl.Color:
  """a at t=0, b at t=1."""
  t = min(1.0, max(0.0, t))
  return rl.Color(*(round(x + (y - x) * t) for x, y in zip((a.r, a.g, a.b, a.a), (b.r, b.g, b.b, b.a), strict=True)))



class LimitCard(Component):
  """Asks before matching a new limit, higher or lower, when Speed Limits says to ask for that direction. It sits over StarPilot's speed limit sign, top left,
  with the new limit's sign in it, and a bar that drains until the offer is ignored."""
  grow_touch_target = False

  @staticmethod
  def width() -> int:
    """At Larger text the card is narrowed to end before the speed (design/onroadlarge-limit.html)."""
    return Z.pick(360, 405)

  @staticmethod
  def pad() -> int:
    return Z.px(12)   # puts the card's sign exactly where the plain sign sits

  @staticmethod
  def button_height() -> int:
    return Z.pick(60, 72)

  def __init__(self, offer: Callable[[], LimitOffer | None], on_match: Callable[[], None], on_ignore: Callable[[], None],
               ):
    super().__init__()
    self._offer = offer
    self._match = self._child(Button(N_("Match"), on_match, ButtonStyle.PRIMARY, height=self.button_height(), font_size=Z.font_px(18),
                                     radius=Z.px(16), weight=T.FONT_EXTRABOLD))
    self._ignore = self._child(Button(N_("Ignore"), on_ignore, ButtonStyle.SECONDARY, height=self.button_height(), font_size=Z.font_px(18),
                                      radius=Z.px(16), weight=T.FONT_BOLD))
    self._zoom = Z.zoom()

  def box(self, rect: rl.Rectangle) -> rl.Rectangle:
    height = self.pad() * 2 + sign_size()[1] + Z.px(14) + self.button_height() + Z.px(14) + Z.px(4)
    return rl.Rectangle(rect.x + Z.px(16), rect.y + Z.px(16), self.width(), height)

  def _render(self, rect: rl.Rectangle) -> None:
    offer = self._offer()
    if offer is None:
      return
    if Z.zoom() != self._zoom:   # follow Text Size: buttons keep their size from when they were made
      self._zoom = Z.zoom()
      for b in (self._match, self._ignore):
        b.restyle(self.button_height(), Z.font_px(18), b._padding, Z.px(16))
    box = self.box(rect)
    draw.fill(box, draw.alpha(T.SURFACE_2, 0.96), Z.px(22))
    draw.stroke(box, T.ACCENT, Z.px(22), Z.px(2))
    body = inset(box, self.pad())
    top, buttons, bar = column(body, [sign_size()[1], self.button_height(), Z.px(4)], Z.px(14))
    sign, text = row(top, [sign_size()[0], FILL], Z.px(16))
    draw_sign(sign, f"{offer.limit:.0f}", offer.vienna)
    lines = [draw.line_height(Z.font_px(22)), draw.line_height(Z.font_px(16)), draw.line_height(Z.font_px(13))]
    title, question, source = column(place(text, text.width, sum(lines) + Z.px(8)), lines, Z.px(4))
    draw.text(title, t_("New limit {}", f"{offer.limit:.0f}"), Z.font_px(22), T.TEXT, T.FONT_EXTRABOLD)
    adjusted = t_("Adjusted limit {} {}", f"{offer.target:.0f}", offer.unit) if offer.target is not None else ""
    draw.text(question, adjusted, Z.font_px(16), T.TEXT_SECONDARY)
    draw.text(source, t_("From {} · ignored in {} s", offer.source, max(0, math.ceil(offer.seconds_left))), Z.font_px(13),
              T.TEXT_MUTED)
    ignore, match = row(buttons, [FILL, FILL], Z.px(10))
    self._ignore.render(ignore)
    self._match.render(match)
    draw.fill(bar, T.TRACK, Z.px(2))
    left = max(0.0, min(1.0, offer.seconds_left / offer.total)) if offer.total > 0 else 0.0
    if left > 0:
      draw.fill(rl.Rectangle(bar.x, bar.y, max(bar.height, bar.width * left), bar.height), T.ACCENT, Z.px(2))




class StatusChip(Component):
  """What the car is doing on its own, bottom left just above the bar: a stack of up to four chips, the newest nearest
  the bar (status.ChipStack decides which, and their opacity). Chips slide to their new place as others come and go."""
  grow_touch_target = False
  INK = {ChipTone.INFO: T.ACCENT_TEXT, ChipTone.PAUSED: T.WARNING, ChipTone.WAITING: T.SUCCESS_TEXT, ChipTone.ALERT: T.DANGER_CHIP_ICON}
  SLIDE = 0.25   # share of the remaining distance a chip moves each frame

  def __init__(self, chips: Callable[[], list[tuple[Chip, float]]]):
    super().__init__()
    self._chips = chips
    self._slot: dict[str, float] = {}   # each chip's drawn place (0 nearest the bar), easing toward its target

  @staticmethod
  def height() -> int:
    return Z.px(44)

  @staticmethod
  def gap() -> int:
    return Z.px(12)

  @staticmethod
  def step() -> int:
    return Z.px(52)

  def size(self, chip: Chip) -> tuple[float, float]:
    return draw.text_width(chip.label, Z.font_px(17), T.FONT_SEMIBOLD) + Z.px(70), self.height()

  def _render(self, rect: rl.Rectangle) -> None:
    chips = self._chips()
    self._slot = {chip.key: self._slot.get(chip.key, float(i)) for i, (chip, _) in enumerate(chips)}
    bar_top = rect.y + rect.height - bar_margin() - bar_height()
    for i, (chip, alpha) in enumerate(chips):
      slot = self._slot[chip.key] = self._slot[chip.key] + (i - self._slot[chip.key]) * self.SLIDE
      if alpha <= 0.01:
        continue
      w, h = self.size(chip)
      w = min(w, rect.width - 2 * bar_margin())
      box = rl.Rectangle(rect.x + bar_margin(), bar_top - self.gap() - h - slot * self.step(), w, h)
      body = inset(box, x=Z.px(16))
      ink = self.INK[chip.tone]
      label = T.TEXT if chip.tone == ChipTone.INFO else ink
      if chip.tone == ChipTone.ALERT:   # the one chip that needs noticing: red fill and border (design/memorychip.html)
        draw.fill(box, draw.alpha(T.DANGER_CHIP, alpha), Z.px(12))
        draw.stroke(box, draw.alpha(T.DANGER, alpha), Z.px(12), Z.px(2))
        label = T.DANGER_CHIP_TEXT
      else:
        draw.fill(box, draw.alpha(T.BG, 0.8 * alpha), Z.px(12))
      draw.icon(rl.Rectangle(body.x, body.y, Z.px(22), body.height), chip.icon, draw.alpha(ink, alpha), Z.px(22))
      draw.text(inset(body, left=Z.px(32)), chip.label, Z.font_px(17), draw.alpha(label, alpha), T.FONT_SEMIBOLD)




def draw_stroke(points: list[rl.Vector2], width: float, ink: rl.Color) -> None:
  """A round-capped line through points as one triangle strip and two half discs, so a translucent ink never
  overlaps itself (separate segments and caps darken where they meet)."""
  half = width / 2
  strip: list[rl.Vector2] = []
  for i, p in enumerate(points):
    a, b = points[max(0, i - 1)], points[min(len(points) - 1, i + 1)]
    dx, dy = b.x - a.x, b.y - a.y
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * half, dx / length * half
    strip += [rl.Vector2(p.x - nx, p.y - ny), rl.Vector2(p.x + nx, p.y + ny)]   # raylib culls the other winding
  rl.draw_triangle_strip(strip, len(strip), ink)
  for end, inner in ((points[0], points[1]), (points[-1], points[-2])):
    outward = math.atan2(end.y - inner.y, end.x - inner.x)
    cap = [end]
    for i in range(17):
      # The fan faces the camera when its vertices run counterclockwise on screen.
      angle = outward + math.pi / 2 - math.pi * i / 16
      cap.append(rl.Vector2(end.x + half * math.cos(angle), end.y + half * math.sin(angle)))
    rl.draw_triangle_fan(cap, len(cap), ink)



def draw_torque(rect: rl.Rectangle, usage: float) -> None:
  """Draw the qualified steering demand above the bar."""
  half = rect.width * (216 / 1093)
  rise = rect.width * (32 / 1093)
  cx = rect.x + rect.width / 2
  end_y = rect.y + rect.height - T.px(107)

  def point(t: float) -> rl.Vector2:
    return rl.Vector2(cx + half * (2 * t - 1), end_y - 2 * (1 - t) * t * rise)

  draw_stroke([point(i / 48) for i in range(49)], T.px(10), T.STEER_ARC_TRACK)
  reach = 0.5 + 0.5 * max(-1.0, min(1.0, usage))
  if abs(reach - 0.5) < 0.003:
    rl.draw_circle_v(point(0.5), T.px(5), T.STEER_ARC_COMFORT)
    return
  lo, hi = sorted((0.5, reach))
  draw_stroke([point(lo + (hi - lo) * i / 16) for i in range(17)], T.px(10), T.STEER_ARC_COMFORT)
