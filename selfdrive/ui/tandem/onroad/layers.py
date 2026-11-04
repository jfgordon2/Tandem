"""Essentials onroad layers: the bottom bar, the status chip, the steering headroom arc and the new-limit card.

Each layer reads a small state object through a getter and calls plain callbacks, so it draws the same with real
messages on the device and with made-up state in tests and renders.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.onroad import alerts
from openpilot.selfdrive.ui.tandem.onroad.status import Chip, ChipTone, turn_icon
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

BAR_HEIGHT = T.px(74)
BAR_MARGIN = T.px(16)
BAR_ZONE = BAR_HEIGHT + BAR_MARGIN * 2          # space the bar takes at the bottom of the road view
CONTROL_FILL = draw.alpha(T.CONTROL_NAV, 0.8)    # 80% so controls stay readable over bright scenes
ENGAGED = T.SUCCESS


@dataclass
class BarState:
  engaged: bool = False
  can_engage: bool = False
  set_speed: float = 0.0          # display units; 0 when cruise isn't set
  unit: str = "mph"
  street: str = ""
  navigating: bool = False
  arrive: str = ""                # e.g. "4:52 PM"
  left: str = ""                  # e.g. "12 min · 8.4 mi"
  heading: str = ""               # StarPilot's compass, when on: "NE"
  weather: tuple[str, str] | None = None   # without a route: the weather now, (icon, "34°"), from the forecast


def _glyph_button(name: str, on_click: Callable[[], None]) -> Button:
  return Button(on_click=on_click, style=ButtonStyle.NAV, height=BAR_HEIGHT, width=BAR_HEIGHT, radius=T.RADIUS_CARD,
                glyph=lambda r, c, s: draw.icon(r, name, c, T.px(28)))


class OnroadBar(Component):
  """Menu, MAX − / +, Where to? (without a route, design/onroadwhereto.html), the street name (with arrival, time left and
  End route while navigating), and engage."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], BarState], on_menu: Callable[[], None], on_speed: Callable[[int], None],
               on_engage: Callable[[], None], on_end_route: Callable[[], None], on_where_to: Callable[[], None] | None = None):
    super().__init__()
    self._state = state
    self._menu = self._child(_glyph_button("menu", on_menu))
    # Ghost style over our own tinted fill, as the parked screen's Where to? card's icon well.
    self._where = self._child(Button(on_click=on_where_to, style=ButtonStyle.GHOST, height=BAR_HEIGHT, width=BAR_HEIGHT,
                                     radius=T.RADIUS_CARD, glyph=lambda r, c, s: draw.icon(r, "navigate", T.ACCENT_TEXT, T.px(28))))
    self._has_where = on_where_to is not None
    self._minus = self._child(Button("−", lambda: on_speed(-1), ButtonStyle.GHOST, height=BAR_HEIGHT, width=T.px(56),
                                     font_size=T.font_px(30)))
    self._plus = self._child(Button("+", lambda: on_speed(1), ButtonStyle.GHOST, height=BAR_HEIGHT, width=T.px(56),
                                    font_size=T.font_px(30)))
    # Ghost style, so the fill drawn below (green while engaged) shows through.
    self._engage = self._child(Button(on_click=on_engage, style=ButtonStyle.GHOST, height=BAR_HEIGHT, width=BAR_HEIGHT,
                                      radius=T.RADIUS_CARD, glyph=lambda r, c, s: draw.icon(r, "wheel", T.TEXT, T.px(32))))
    self._end = self._child(Button(N_("End route"), on_end_route, ButtonStyle.DANGER_SOFT, height=T.px(52), font_size=T.font_px(17)))
    for b in (self._minus, self._plus):
      b.set_enabled(lambda: self._state().engaged and self._state().set_speed > 0)

  def where_to_shown(self) -> bool:
    return self._has_where and not self._state().navigating

  def rects(self, rect: rl.Rectangle) -> dict[str, rl.Rectangle]:
    body = rl.Rectangle(rect.x + BAR_MARGIN, rect.y + rect.height - BAR_MARGIN - BAR_HEIGHT, rect.width - BAR_MARGIN * 2, BAR_HEIGHT)
    if self.where_to_shown():
      menu, speed, where, center, engage = row(body, [BAR_HEIGHT, T.px(194), BAR_HEIGHT, FILL, BAR_HEIGHT], T.px(12))
      return {"menu": menu, "speed": speed, "where": where, "center": center, "engage": engage}
    menu, speed, center, engage = row(body, [BAR_HEIGHT, T.px(194), FILL, BAR_HEIGHT], T.px(12))
    return {"menu": menu, "speed": speed, "center": center, "engage": engage}

  def hit_rects(self, rect: rl.Rectangle) -> list[rl.Rectangle]:
    return list(self.rects(rect).values())

  def _render(self, rect: rl.Rectangle):
    state = self._state()
    r = self.rects(rect)
    self._menu.render(r["menu"])
    if "where" in r:
      draw.fill(r["where"], T.ACCENT_SURFACE, T.RADIUS_CARD)
      self._where.render(r["where"])

    draw.fill(r["speed"], CONTROL_FILL, T.RADIUS_CARD)
    minus, value, plus = row(r["speed"], [T.px(56), FILL, T.px(56)])
    self._minus.render(minus)
    self._plus.render(plus)
    label, number = column(place(value, value.width, T.px(56)), [T.px(18), FILL])
    draw.text(label, N_("MAX"), T.font_px(13), T.ACCENT_TEXT, T.FONT_BOLD, Align.CENTER)
    draw.text(number, f"{state.set_speed:.0f}" if state.set_speed else "–", T.font_px(26), T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)

    center = r["center"]
    draw.fill(center, CONTROL_FILL, T.RADIUS_CARD)
    if state.navigating:
      # Arrival and time left at the left, then the street name in what's left, then End route.
      body = inset(center, x=T.px(22))
      w, _ = self._end.preferred_size(body.width)
      self._end.render(place(body, w, T.px(52), Align.END))
      body = inset(body, right=w + T.px(20))
      x = body.x
      if state.heading:   # the compass tag stays first, before the arrival time
        x += heading_tag(rl.Rectangle(x, body.y, body.width, body.height), state.heading) + T.px(20)
      for caption, text in ((N_("ARRIVE"), state.arrive or "–"), (N_("LEFT"), state.left or "–")):
        cell_w = max(draw.text_width(caption, T.SIZE_CAPTION, T.FONT_BOLD, tracking=T.CAPTION_TRACKING), draw.text_width(text, T.font_px(22), T.FONT_BOLD))
        top, bottom = column(place(rl.Rectangle(x, body.y, cell_w, body.height), cell_w, T.px(56)), [T.px(18), FILL], T.px(3))
        draw.caption(top, caption)
        draw.text(bottom, text, T.font_px(22), T.TEXT, T.FONT_BOLD)
        x += cell_w + T.px(24)
      if state.street and x + T.px(80) < body.x + body.width:
        rl.draw_rectangle_rec(rl.Rectangle(x, body.y + body.height * 0.25, T.DIVIDER, body.height * 0.5), T.CONTROL)
        self._street(rl.Rectangle(x + T.px(22), body.y, body.x + body.width - x - T.px(22), body.height), state.street, Align.START)
    else:
      # The compass tag sits where it does while navigating (first, at the start); the street centers in what's left.
      body = inset(center, x=T.px(22))
      if state.heading:
        body = inset(body, left=heading_tag(body, state.heading) + T.px(20))
      if state.weather:   # the weather now at the end, as the compass tag starts it; the street centers between them
        body = inset(body, right=weather_now(body, *state.weather) + T.px(20))
      if state.street:
        self._street(body, state.street, Align.CENTER)

    engage = r["engage"]
    draw.fill(engage, ENGAGED if state.engaged else CONTROL_FILL, T.RADIUS_CARD)
    self._engage.set_enabled(state.engaged or state.can_engage)
    self._engage.render(engage)


  @staticmethod
  def _street(rect: rl.Rectangle, street: str, h: Align) -> None:
    """The road icon and the street name, centered (or at the start) in rect, elided to fit."""
    text_w = min(rect.width - T.px(40), draw.text_width(street, STREET_SIZE, T.FONT_BOLD))
    block = place(rect, T.px(40) + text_w, rect.height, h)
    draw.icon(rl.Rectangle(block.x, block.y, T.px(28), block.height), "road", T.ACCENT_TEXT, T.px(22))
    draw.text(inset(block, left=T.px(40)), draw.fit(street, STREET_SIZE, T.FONT_BOLD, text_w), STREET_SIZE, T.TEXT, T.FONT_BOLD)


STREET_SIZE = T.font_px(22)   # the street name, and the compass tag beside it at the same size


def weather_now(rect: rl.Rectangle, icon: str, temperature: str) -> float:
  """The weather icon and temperature at the end of rect, at the street name's size. Returns the width used."""
  text_w = draw.text_width(temperature, STREET_SIZE, T.FONT_BOLD)
  w = T.px(26) + T.px(8) + text_w
  icon_box, text = row(rl.Rectangle(rect.x + rect.width - w, rect.y, w, rect.height), [T.px(26), FILL], T.px(8))
  draw.icon(icon_box, icon, T.TEXT_SECONDARY, T.px(26))
  draw.text(text, temperature, STREET_SIZE, T.TEXT, T.FONT_BOLD)
  return w


def heading_width(heading: str) -> float:
  return draw.text_width(heading, STREET_SIZE, T.FONT_EXTRABOLD, tracking=T.px(1)) + T.px(22)


def heading_tag(rect: rl.Rectangle, heading: str) -> float:
  """The compass heading as a blue tag, vertically centered at the start of rect. Returns its width."""
  w = heading_width(heading)
  tag = place(rl.Rectangle(rect.x, rect.y, w, rect.height), w, T.px(40))
  draw.fill(tag, T.ACCENT_SURFACE, T.px(10))
  draw.text(tag, heading, STREET_SIZE, T.ACCENT_TEXT, T.FONT_EXTRABOLD, Align.CENTER, tracking=T.px(1))
  return w


class StatusChip(Component):
  """What the car is doing on its own, bottom left just above the bar: a stack of up to four chips, the newest nearest
  the bar (status.ChipStack decides which, and their opacity). Chips slide to their new place as others come and go."""
  grow_touch_target = False
  INK = {ChipTone.INFO: T.ACCENT_TEXT, ChipTone.PAUSED: T.WARNING, ChipTone.WAITING: T.SUCCESS_TEXT, ChipTone.ALERT: T.DANGER_CHIP_ICON}
  HEIGHT, GAP, STEP = T.px(44), T.px(12), T.px(52)
  SLIDE = 0.25   # share of the remaining distance a chip moves each frame

  def __init__(self, chips: Callable[[], list[tuple[Chip, float]]]):
    super().__init__()
    self._chips = chips
    self._slot: dict[str, float] = {}   # each chip's drawn place (0 nearest the bar), easing toward its target

  def size(self, chip: Chip) -> tuple[float, float]:
    return draw.text_width(chip.label, T.font_px(17), T.FONT_SEMIBOLD) + T.px(70), self.HEIGHT

  def _render(self, rect: rl.Rectangle):
    chips = self._chips()
    self._slot = {chip.key: self._slot.get(chip.key, float(i)) for i, (chip, _) in enumerate(chips)}
    bar_top = rect.y + rect.height - BAR_MARGIN - BAR_HEIGHT
    for i, (chip, alpha) in enumerate(chips):
      slot = self._slot[chip.key] = self._slot[chip.key] + (i - self._slot[chip.key]) * self.SLIDE
      if alpha <= 0.01:
        continue
      w, h = self.size(chip)
      box = rl.Rectangle(rect.x + BAR_MARGIN, bar_top - self.GAP - h - slot * self.STEP, w, h)
      body = inset(box, x=T.px(16))
      ink = self.INK[chip.tone]
      label = T.TEXT if chip.tone == ChipTone.INFO else ink
      if chip.tone == ChipTone.ALERT:   # the one chip that needs noticing: red fill and border (design/memorychip.html)
        draw.fill(box, draw.alpha(T.DANGER_CHIP, alpha), T.px(12))
        draw.stroke(box, draw.alpha(T.DANGER, alpha), T.px(12), T.px(2))
        label = T.DANGER_CHIP_TEXT
      else:
        draw.fill(box, draw.alpha(T.BG, 0.8 * alpha), T.px(12))
      draw.icon(rl.Rectangle(body.x, body.y, T.px(22), body.height), chip.icon, draw.alpha(ink, alpha), T.px(22))
      draw.text(inset(body, left=T.px(32)), chip.label, T.font_px(17), draw.alpha(label, alpha), T.FONT_SEMIBOLD)


# ── Steering headroom ──

COMFORTABLE, WORKING, AT_LIMIT = "comfortable", "working", "at_limit"
WORKING_FROM, LIMIT_FROM, LIMIT_HOLD = 0.60, 0.85, 0.5
LIMIT_RELEASE = 0.80
LIMIT_LANE_COLOR = rl.Color(255, 138, 77, 255)
LIMIT_BORDER_COLOR = rl.Color(224, 162, 58, 255)


class Headroom:
  """Debounce limit entry and release below 80%, so bumps and threshold noise don't repeat warnings."""

  def __init__(self):
    self._over_since: float | None = None
    self._at_limit = False

  def stage(self, usage: float, now: float, active: bool = True) -> str:
    if not active:
      self._over_since = None
      self._at_limit = False
      return COMFORTABLE
    usage = abs(usage)
    if self._at_limit and usage >= LIMIT_RELEASE:
      return AT_LIMIT
    self._at_limit = False
    if usage >= LIMIT_FROM:
      self._over_since = now if self._over_since is None else self._over_since
      if now - self._over_since >= LIMIT_HOLD:
        self._at_limit = True
        return AT_LIMIT
    else:
      self._over_since = None
    return WORKING if usage >= WORKING_FROM else COMFORTABLE


@dataclass
class ArcState:
  usage: float = 0.0       # -1..1, signed toward the turn
  preview: float = 0.0     # what the planned path needs 2–3 s ahead, same scale
  active: bool = False     # openpilot is steering
  stage: str = COMFORTABLE


@dataclass(frozen=True)
class ArcShape:
  """The arc as the mocks draw it: a quadratic curve whose ends span `chord` of the road view's width, with its control
  point `rise` of the width above the ends (the middle sits half that above them), stroked `stroke` mock px wide, with its
  ends `lift` mock px above the bottom of the road view."""
  chord: float
  rise: float
  stroke: float
  lift: float


# The road views are 531 mock px tall: onroad.html's ends sit 23 above the bar, onroaddev.html's 19 above its strip.
ARC = ArcShape(chord=432 / 1093, rise=32 / 1093, stroke=10, lift=531 - 424)     # M330 424 Q546 392 762 424
DEV_ARC = ArcShape(chord=326 / 827, rise=28 / 827, stroke=9, lift=531 - 388)   # M250 388 Q413 360 576 388
STAGE_STYLE = {COMFORTABLE: (T.TEXT, None), WORKING: (T.WARNING, T.px(13)), AT_LIMIT: (rl.Color(255, 112, 67, 255), T.px(18))}
ARC_STEPS = 48


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
    out = math.degrees(math.atan2(end.y - inner.y, end.x - inner.x))
    rl.draw_circle_sector(end, half, out - 90, out + 90, 16, ink)


class HeadroomArc(Component):
  """The arc above the bar. A faint track, the current use toward the turn, and a lighter preview of the curve ahead."""
  grow_touch_target = False

  ABOVE_CARD = T.px(23)   # the gap the mock leaves between the arc's ends and the bar, kept above the Help steer card

  def __init__(self, state: Callable[[], ArcState], shape: Callable[[], ArcShape] = lambda: ARC,
               help_steer: Callable[[], bool] = lambda: False):
    """help_steer: whether the Help steer card is up, in the bar's place; the arc then sits above the card."""
    super().__init__()
    self._state = state
    self._shape = shape
    self._help_steer = help_steer

  def _render(self, rect: rl.Rectangle):
    s, shape = self._state(), self._shape()
    half = rect.width * shape.chord / 2
    cx, end_y = rect.x + rect.width / 2, rect.y + rect.height - T.px(shape.lift)   # rect is the whole road view
    if self._help_steer():
      end_y = min(end_y, help_steer_box(rect).y - self.ABOVE_CARD)
    rise = rect.width * shape.rise

    def at(t: float) -> rl.Vector2:
      u = 1 - t
      return rl.Vector2(cx - half * u * u + half * t * t, end_y - 2 * u * t * rise)

    color, thickness = STAGE_STYLE[s.stage]
    thickness = thickness or T.px(shape.stroke)
    alpha = 1.0 if s.active else 0.35

    def arc(t0: float, t1: float, width: float, ink: rl.Color) -> None:
      if abs(t1 - t0) < 0.002:
        return
      lo, hi = min(t0, t1), max(t0, t1)
      steps = max(2, int(ARC_STEPS * (hi - lo)))
      draw_stroke([at(lo + (hi - lo) * i / steps) for i in range(steps + 1)], width, ink)

    arc(0.0, 1.0, T.px(shape.stroke), draw.alpha(T.TEXT, 0.18 * alpha))
    reach = lambda share: 0.5 + 0.5 * max(-1.0, min(1.0, share))  # noqa: E731
    if s.active and abs(s.preview) > abs(s.usage) + 0.05:
      arc(0.5, reach(s.preview), thickness, draw.alpha(color, 0.3))
    arc(0.5, reach(s.usage), thickness, draw.alpha(color, 0.95 * alpha))
    if abs(s.usage) < 0.03:
      rl.draw_circle_v(at(0.5), T.px(5), draw.alpha(T.TEXT, 0.8 * alpha))


HELP_STEER = (N_("Help steer"), N_("Steering is at its limit for this curve"))


def help_steer_box(rect: rl.Rectangle) -> rl.Rectangle:
  return alerts.box(rect, alerts.WARNING, *HELP_STEER)


class HelpSteer(Component):
  """The at-limit warning, drawn as every other Warning alert is: the amber card along the bottom, in the bar's place (the
  view hides the bar and chips while it shows, as for other alerts). The view requests its one-shot sound through soundd."""
  grow_touch_target = False

  def _render(self, rect: rl.Rectangle):
    alerts.draw_alert(help_steer_box(rect), alerts.WARNING, *HELP_STEER, 1.0)


# ── New speed limit ──

@dataclass
class LimitOffer:
  limit: float          # display units
  target: float         # what cruise would go to, with the offset
  unit: str
  source: str
  seconds_left: float
  total: float = 30.0   # how long the offer lasts, for the countdown bar
  vienna: bool = False  # the round sign used outside the US
  lower: bool = False   # below the limit in use: Slow down to, rather than Speed up to


VIENNA_RED = rl.Color(0xD9, 0x43, 0x4F, 255)


class LimitCard(Component):
  """Asks before matching a new limit, higher or lower, when Speed Limits says to ask for that direction. It sits over StarPilot's speed limit sign, top left,
  with the new limit's sign in it, and a bar that drains until the offer is ignored."""
  grow_touch_target = False
  WIDTH, PAD = T.px(360), T.px(12)   # the pad puts the card's sign exactly where the plain sign sits

  def __init__(self, offer: Callable[[], LimitOffer | None], on_match: Callable[[], None], on_ignore: Callable[[], None],
               top: Callable[[], float] = lambda: T.px(16)):
    """top: how far down the card sits, below the turn card while navigating."""
    super().__init__()
    self._offer = offer
    self._top = top
    self._match = self._child(Button(N_("Match"), on_match, ButtonStyle.PRIMARY, height=T.px(60), font_size=T.font_px(18),
                                     radius=T.px(16), weight=T.FONT_EXTRABOLD))
    self._ignore = self._child(Button(N_("Ignore"), on_ignore, ButtonStyle.SECONDARY, height=T.px(60), font_size=T.font_px(18),
                                      radius=T.px(16), weight=T.FONT_BOLD))

  def box(self, rect: rl.Rectangle) -> rl.Rectangle:
    height = self.PAD * 2 + SIGN_SIZE[1] + T.px(14) + T.px(60) + T.px(14) + T.px(4)
    return rl.Rectangle(rect.x + T.px(16), rect.y + self._top(), self.WIDTH, height)

  def _render(self, rect: rl.Rectangle):
    offer = self._offer()
    if offer is None:
      return
    box = self.box(rect)
    draw.fill(box, draw.alpha(T.SURFACE_2, 0.96), T.px(22))
    draw.stroke(box, T.ACCENT, T.px(22), T.px(2))
    body = inset(box, self.PAD)
    top, buttons, bar = column(body, [SIGN_SIZE[1], T.px(60), T.px(4)], T.px(14))
    sign, text = row(top, [SIGN_SIZE[0], FILL], T.px(16))
    draw_sign(sign, f"{offer.limit:.0f}", offer.vienna)
    lines = [draw.line_height(T.font_px(22)), draw.line_height(T.font_px(16)), draw.line_height(T.font_px(13))]
    title, question, source = column(place(text, text.width, sum(lines) + T.px(8)), lines, T.px(4))
    draw.text(title, t_("New limit {}", f"{offer.limit:.0f}"), T.font_px(22), T.TEXT, T.FONT_EXTRABOLD)
    verb = N_("Slow down") if offer.lower else N_("Speed up")
    draw.text(question, t_("{} to {} {}?", verb, f"{offer.target:.0f}", offer.unit), T.font_px(16), T.TEXT_SECONDARY)
    draw.text(source, t_("From {} · ignored in {} s", offer.source.lower() or 'map', max(0, math.ceil(offer.seconds_left))), T.font_px(13),
              T.TEXT_MUTED)
    ignore, match = row(buttons, [FILL, FILL], T.px(10))
    self._ignore.render(ignore)
    self._match.render(match)
    draw.fill(bar, T.TRACK, T.px(2))
    left = max(0.0, min(1.0, offer.seconds_left / offer.total)) if offer.total > 0 else 0.0
    if left > 0:
      draw.fill(rl.Rectangle(bar.x, bar.y, max(bar.height, bar.width * left), bar.height), T.ACCENT, T.px(2))


# ── Speed, speed limit sign and turn card, as in the onroad mocks ──

HUD_PILL = rl.Color(0x0B, 0x0D, 0x10, 230)
SPEED_UNIT = rl.Color(0xC9, 0xD0, 0xDA, 255)
TURN_LINE = rl.Color(0xC9, 0xD8, 0xEA, 255)
SIGN_TILE = (T.px(82), T.px(98))
SIGN_SIZE = (T.px(62), T.px(78))   # the US sign inside the tile; the new-limit card draws it at the same size and spot
SIGN_MARGIN = T.px(18)


SIGNAL_BRIGHT, SIGNAL_DIM = T.SUCCESS_BRIGHT, rl.Color(0x2A, 0x8F, 0x5E, 255)
SIGNAL_SIZE = (T.px(46), T.px(30))   # both chevrons, as in the onroad mock
SIGNAL_GAP = T.px(22)
SIGNAL_STEP = 0.4                    # seconds each chevron leads, so the light steps outward


def draw_signal(rect: rl.Rectangle, side: str, now: float) -> None:
  """Two chevrons pointing the way of the turn. The bright one steps outward, from beside the speed to the edge."""
  w, h = SIGNAL_SIZE
  box = place(rect, w, h)
  stroke = T.px(5)
  outer_bright = int(now / SIGNAL_STEP) % 2 == 1
  for i, x0 in enumerate((T.px(18), T.px(36))):   # the mock's chevron tips: at 8 and 26 of 46, arms out to 18 and 36
    outer = i == 0
    color = SIGNAL_BRIGHT if outer == outer_bright else SIGNAL_DIM
    tip_x, arm_x = x0 - T.px(10), x0
    if side == "right":
      tip_x, arm_x = w - tip_x, w - arm_x
    tip = rl.Vector2(box.x + tip_x, box.y + h / 2)
    for arm in (rl.Vector2(box.x + arm_x, box.y + h / 2 - T.px(10)), rl.Vector2(box.x + arm_x, box.y + h / 2 + T.px(10))):
      rl.draw_line_ex(arm, tip, stroke, color)
      rl.draw_circle_v(arm, stroke / 2, color)
    rl.draw_circle_v(tip, stroke / 2, color)


def draw_speed(rect: rl.Rectangle, speed: float, unit: str, offset_y: float = 0.0, left: bool = False, right: bool = False,
               now: float = 0.0) -> None:
  """The current speed, top center on a dark pill. A blinker adds our turn signal on its side; the number stays centered."""
  number, size = f"{round(speed)}", T.font_px(62)
  lines = [draw.line_height(size), draw.line_height(T.font_px(17))]
  w = max(draw.text_width(number, size, T.FONT_EXTRABOLD), draw.text_width(unit, T.font_px(17))) + T.px(80)
  h = sum(lines) + T.px(20) - T.px(6)
  center = rl.Rectangle(rect.x + (rect.width - w) / 2, rect.y + T.px(16) + offset_y, w, h)
  extra = SIGNAL_SIZE[0] + SIGNAL_GAP - T.px(10)   # the mock's pill is 10 px tighter on the signal side
  pill = rl.Rectangle(center.x - (extra if left else 0), center.y, w + (extra if left else 0) + (extra if right else 0), h)
  draw.fill(pill, HUD_PILL, T.px(22))
  value, label = column(inset(center, y=T.px(10)), [lines[0] - T.px(6), lines[1]])
  draw.text(value, number, size, T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(label, unit, T.font_px(17), SPEED_UNIT, h=Align.CENTER)
  for side, on in (("left", left), ("right", right)):
    if on:
      x = pill.x + T.px(30) if side == "left" else pill.x + pill.width - T.px(30) - SIGNAL_SIZE[0]
      draw_signal(rl.Rectangle(x, pill.y, SIGNAL_SIZE[0], pill.height), side, now)


def sign_tile(rect: rl.Rectangle) -> rl.Rectangle:
  """Where the speed limit sign sits: top left."""
  return rl.Rectangle(rect.x + SIGN_MARGIN, rect.y + SIGN_MARGIN, *SIGN_TILE)


def draw_speed_limit(tile: rl.Rectangle, limit: str, vienna: bool, note: str = "") -> None:
  """The posted limit on a dark tile. note is Developer View's source and offset ("MAP · +3")."""
  draw.fill(tile, rl.Color(0x0B, 0x0D, 0x10, 255), T.px(14))
  draw_sign(place(tile, *SIGN_SIZE), limit, vienna, note)


def draw_sign(area: rl.Rectangle, limit: str, vienna: bool, note: str = "") -> None:
  """A US sign filling area, or Vienna's red ring centered on it (a little wider than the US sign, as in the mock). A note
  sits small under the US sign's number, or under Vienna's ring."""
  if vienna:
    sign = place(area, T.px(72), T.px(72))
    draw.fill(sign, VIENNA_RED, sign.width / 2)
    draw.fill(inset(sign, T.px(8)), rl.WHITE, sign.width / 2)
    draw.text(sign, limit, T.font_px(28), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
    if note:
      draw.text(rl.Rectangle(area.x - T.px(10), sign.y + sign.height, area.width + T.px(20), T.px(14)), note, T.font_px(9), T.TEXT_TERTIARY,
                T.FONT_EXTRABOLD, Align.CENTER)
    return
  sign = area
  draw.fill(sign, rl.WHITE, T.px(8))
  draw.stroke(inset(sign, T.px(2)), T.BG, T.px(7), T.px(3))
  body = inset(sign, x=T.px(5), y=T.px(9))
  top, middle, number, small = column(body, [T.px(12), T.px(12), FILL, T.px(11) if note else 0])
  draw.text(top, "SPEED", T.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)   # the US sign's own words: never translated
  draw.text(middle, "LIMIT", T.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(number, limit, T.font_px(28 if note else 32), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  if note:
    draw.text(small, note, T.font_px(9), T._hex("3A4552"), T.FONT_EXTRABOLD, Align.CENTER)


DM_TILE = T.px(64)
DM_RING = (T.px(50), T.px(3))     # diameter and width


def dm_tile(rect: rl.Rectangle) -> rl.Rectangle:
  """The driver monitor's place: the top right corner, inset like the sign is on the left."""
  return rl.Rectangle(rect.x + rect.width - SIGN_MARGIN - DM_TILE, rect.y + SIGN_MARGIN, DM_TILE, DM_TILE)


def draw_driver_monitor(tile: rl.Rectangle, opacity: float, attentive: float, watching: bool) -> None:
  """The driver on a dark tile, ringed green while attentive and amber as attention drops. Without a camera policy
  (watching False) the ring is a quiet track and the whole tile is dimmed by the caller's opacity."""
  if opacity <= 0.01:
    return
  draw.fill(tile, draw.alpha(rl.Color(0x0B, 0x0D, 0x10, 255), opacity), T.px(14))
  ring = place(tile, DM_RING[0], DM_RING[0])
  if watching:
    color = mix(T.WARNING, T.SUCCESS_BRIGHT, attentive)
  else:
    color = draw.alpha(T.TEXT, 0.25)
  draw.stroke(ring, draw.alpha(color, opacity), ring.width / 2, DM_RING[1])
  draw.icon(tile, "driver", draw.alpha(T.TEXT, opacity), T.px(26))


def mix(a: rl.Color, b: rl.Color, t: float) -> rl.Color:
  """a at t=0, b at t=1."""
  t = min(1.0, max(0.0, t))
  return rl.Color(*(round(x + (y - x) * t) for x, y in zip((a.r, a.g, a.b, a.a), (b.r, b.g, b.b, b.a), strict=True)))


TURN_CARD_WIDTH = T.px(330)
TURN_CARD_TOP = T.px(16)
TURN_BELOW_SIGN = SIGN_MARGIN + SIGN_TILE[1] + T.px(12)   # the card's top while the sign holds the corner


def draw_turn_card(rect: rl.Rectangle, distance: str, text: str, maneuver: str, modifier: str,
                   top: float = TURN_CARD_TOP) -> rl.Rectangle:
  """The next turn, top left (below the sign when there is one): its arrow, the distance and the instruction. Returns the card's box."""
  lines = [draw.line_height(T.font_px(30)), draw.line_height(T.font_px(17))]
  box = rl.Rectangle(rect.x + SIGN_MARGIN, rect.y + top, TURN_CARD_WIDTH, max(T.px(54), sum(lines)) + T.px(28))
  draw.fill(box, T.ACCENT_SURFACE, T.px(20))
  body = inset(box, x=T.px(18), y=T.px(14))
  icon, words = row(body, [T.px(54), FILL], T.px(16))
  draw.icon(icon, turn_icon(maneuver, modifier), T.TEXT, T.px(54))
  dist, line = column(place(words, words.width, sum(lines) + T.px(2)), lines, T.px(2))
  draw.text(dist, distance, T.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
  draw.text(line, text, T.font_px(17), TURN_LINE)
  return box

