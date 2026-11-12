"""Essentials onroad layers: the bottom bar, the status chip, the steering headroom arc and the new-limit card.

Each layer reads a small state object through a getter and calls plain callbacks, so it draws the same with real
messages on the device and with made-up state in tests and renders. Sizes come from onroad/size.py as they draw, so
Text Size (Standard or Larger) takes effect on the next frame.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.base import Component
from openpilot.selfdrive.ui.tandem.controls import Button, ButtonStyle
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, column, inset, place, row
from openpilot.selfdrive.ui.tandem.onroad import alerts, size as Z
from openpilot.selfdrive.ui.tandem.onroad.scroll import Scroller
from openpilot.selfdrive.ui.tandem.onroad.status import Chip, ChipTone, turn_icon
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

CONTROL_FILL = draw.alpha(T.CONTROL_NAV, 0.8)    # 80% so controls stay readable over bright scenes
ENGAGED = T.SUCCESS


def bar_height() -> int:
  return Z.px(74)


def bar_margin() -> int:
  return Z.px(16)


def bar_zone() -> int:
  """The space the bar takes at the bottom of the road view."""
  return bar_height() + bar_margin() * 2


def radius() -> int:
  """The bar's controls and the chips' corner, as the onroad mocks round them."""
  return Z.px(18)


@dataclass
class BarState:
  """What the bottom bar shows: engagement, the set speed and its unit, and the street or route."""
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


def _glyph_button(name: str, on_click: Callable[[], None], ink: rl.Color | None = None, glyph: float = 28) -> Button:
  return Button(on_click=on_click, style=ButtonStyle.NAV, height=bar_height(), width=bar_height(), radius=radius(),
                glyph=lambda r, c, s: draw.icon(r, name, ink or c, Z.px(glyph)))


# The larger navigation bar takes turns: arrival and time left, then the street name (design/onroadlarge-nav.html).
ARRIVAL_S = 6.0       # arrival's turn
STREET_S = 4.0        # the street's turn, at least; longer while a long name finishes scrolling
CROSSFADE_S = 0.3     # instant with Reduce Motion


class OnroadBar(Component):
  """Menu, MAX − / +, Where to? (without a route, design/onroadwhereto.html), the street name (with arrival, time left and
  End route while navigating), and engage. A street name that doesn't fit scrolls (onroad/scroll.py). At Larger text the
  navigating bar can't fit arrival, time left, the street and End route, so arrival and the street take turns."""
  grow_touch_target = False

  def __init__(self, state: Callable[[], BarState], on_menu: Callable[[], None], on_speed: Callable[[int], None],
               on_engage: Callable[[], None], on_end_route: Callable[[], None], on_where_to: Callable[[], None] | None = None,
               clock: Callable[[], float] = time.monotonic):
    super().__init__()
    self._state = state
    self._clock = clock
    self._menu = self._child(_glyph_button("menu", on_menu))
    # Ghost style over our own tinted fill, as the parked screen's Where to? card's icon well.
    self._where = self._child(Button(on_click=on_where_to, style=ButtonStyle.GHOST, height=bar_height(), width=bar_height(),
                                     radius=radius(), glyph=lambda r, c, s: draw.icon(r, "navigate", T.ACCENT_TEXT, Z.px(28))))
    self._has_where = on_where_to is not None
    self._minus = self._child(Button("−", lambda: on_speed(-1), ButtonStyle.GHOST, height=bar_height(), width=Z.px(56),
                                     font_size=Z.font_px(30)))
    self._plus = self._child(Button("+", lambda: on_speed(1), ButtonStyle.GHOST, height=bar_height(), width=Z.px(56),
                                    font_size=Z.font_px(30)))
    # Ghost style, so the fill drawn below (green while engaged) shows through.
    self._engage = self._child(Button(on_click=on_engage, style=ButtonStyle.GHOST, height=bar_height(), width=bar_height(),
                                      radius=radius(), glyph=lambda r, c, s: draw.icon(r, "wheel", T.TEXT, Z.px(32))))
    self._end = self._child(Button(N_("End route"), on_end_route, ButtonStyle.DANGER_SOFT, height=Z.px(52), font_size=Z.font_px(17)))
    for b in (self._minus, self._plus):
      b.set_enabled(lambda: self._state().engaged and self._state().set_speed > 0)
    self._zoom = Z.zoom()
    self._street_scroll = Scroller(clock)
    self._turn_since: float | None = None   # when the larger navigating bar's current turn began
    self._street_turn = False

  def _resize(self) -> None:
    """Follow Text Size: the buttons keep their size from when they were made."""
    self._zoom = Z.zoom()
    for b in (self._menu, self._where, self._engage):
      b.restyle(bar_height(), b._font_size, b._padding, radius())
      b._width = bar_height()
    for b in (self._minus, self._plus):
      b.restyle(bar_height(), Z.font_px(30), b._padding, b._radius)
      b._width = Z.px(56)
    self._end.restyle(Z.px(52), Z.font_px(17), Z.px(18), self._end._radius)

  def where_to_shown(self) -> bool:
    return self._has_where and not self._state().navigating

  def rects(self, rect: rl.Rectangle) -> dict[str, rl.Rectangle]:
    h, m = bar_height(), bar_margin()
    body = rl.Rectangle(rect.x + m, rect.y + rect.height - m - h, rect.width - m * 2, h)
    if self.where_to_shown():
      menu, speed, where, center, engage = row(body, [h, Z.px(194), h, FILL, h], Z.px(12))
      return {"menu": menu, "speed": speed, "where": where, "center": center, "engage": engage}
    menu, speed, center, engage = row(body, [h, Z.px(194), FILL, h], Z.px(12))
    return {"menu": menu, "speed": speed, "center": center, "engage": engage}

  def hit_rects(self, rect: rl.Rectangle) -> list[rl.Rectangle]:
    return list(self.rects(rect).values())

  def _render(self, rect: rl.Rectangle) -> None:
    if Z.zoom() != self._zoom:
      self._resize()
    state = self._state()
    r = self.rects(rect)
    self._menu.render(r["menu"])
    if "where" in r:
      draw.fill(r["where"], T.ACCENT_SURFACE, radius())
      self._where.render(r["where"])

    draw.fill(r["speed"], CONTROL_FILL, radius())
    minus, value, plus = row(r["speed"], [Z.px(56), FILL, Z.px(56)])
    self._minus.render(minus)
    self._plus.render(plus)
    label, number = column(place(value, value.width, Z.px(56)), [Z.px(18), FILL])
    draw.text(label, N_("MAX"), Z.font_px(13), T.ACCENT_TEXT, T.FONT_BOLD, Align.CENTER)
    draw.text(number, f"{state.set_speed:.0f}" if state.set_speed else "–", Z.font_px(26), T.TEXT, T.FONT_EXTRABOLD, Align.CENTER)

    center = r["center"]
    draw.fill(center, CONTROL_FILL, radius())
    if state.navigating:
      self._navigating(center, state, rect)
    else:
      self._turn_since = None
      # The compass tag sits where it does while navigating (first, at the start); the street centers in what's left.
      body = inset(center, x=Z.px(22))
      if state.heading:
        body = inset(body, left=heading_tag(body, state.heading) + Z.px(20))
      if state.weather:   # the weather now at the end, as the compass tag starts it; the street centers between them
        body = inset(body, right=weather_now(body, *state.weather) + Z.px(20))
      if state.street:
        self._street(body, state.street, Align.CENTER, rect)

    engage = r["engage"]
    draw.fill(engage, ENGAGED if state.engaged else CONTROL_FILL, radius())
    self._engage.set_enabled(state.engaged or state.can_engage)
    self._engage.render(engage)

  def _navigating(self, center: rl.Rectangle, state: BarState, outer: rl.Rectangle) -> None:
    """Arrival and time left at the left, then the street name in what's left, then End route. At Larger text there's no
    room for both, so they take turns."""
    body = inset(center, x=Z.px(22))
    w, _ = self._end.preferred_size(body.width)
    self._end.render(place(body, w, Z.px(52), Align.END))
    body = inset(body, right=w + Z.px(20))
    if state.heading:   # the compass tag stays first, before the arrival time
      body = inset(body, left=heading_tag(body, state.heading) + Z.px(20))
    if not Z.larger():
      self._turn_since = None
      x = self._arrival(body, state, 1.0)
      if state.street and x + Z.px(80) < body.x + body.width:
        rl.draw_rectangle_rec(rl.Rectangle(x, body.y + body.height * 0.25, T.DIVIDER, body.height * 0.5), T.CONTROL)
        self._street(rl.Rectangle(x + Z.px(22), body.y, body.x + body.width - x - Z.px(22), body.height), state.street, Align.START, outer)
      return
    arrival, street = self._turns(body, state)
    if arrival > 0:
      self._arrival(body, state, arrival)
    if street > 0 and state.street:
      self._street(body, state.street, Align.START, outer, street)

  def _turns(self, body: rl.Rectangle, state: BarState) -> tuple[float, float]:
    """How visible arrival and the street are, as the larger bar takes turns between them."""
    now = self._clock()
    if not state.street:
      self._turn_since, self._street_turn = None, False
      return 1.0, 0.0
    if self._turn_since is None:   # arrival shows at once; only the changes between turns fade
      self._turn_since, self._street_turn = now - CROSSFADE_S, False
    street_s = max(STREET_S, self._street_scroll.pass_seconds(state.street, body.width, street_size(), T.FONT_BOLD))
    length = street_s if self._street_turn else ARRIVAL_S
    if now - self._turn_since >= length:
      self._turn_since, self._street_turn = now, not self._street_turn
    fade = 0.0 if Z.reduce_motion() else CROSSFADE_S
    shown = min(1.0, (now - self._turn_since) / fade) if fade else 1.0
    return (1.0 - shown, shown) if self._street_turn else (shown, 1.0 - shown)

  @staticmethod
  def _arrival(body: rl.Rectangle, state: BarState, alpha: float) -> float:
    """Arrival and time left, from the start of body. Returns where they end."""
    x = body.x
    caption, value = Z.font_px(13), Z.font_px(22)
    for label, text in ((N_("ARRIVE"), state.arrive or "–"), (N_("LEFT"), state.left or "–")):
      cell_w = max(draw.text_width(label, caption, T.FONT_BOLD, tracking=T.CAPTION_TRACKING), draw.text_width(text, value, T.FONT_BOLD))
      top, bottom = column(place(rl.Rectangle(x, body.y, cell_w, body.height), cell_w, Z.px(56)), [Z.px(18), FILL], Z.px(3))
      draw.caption(top, label, draw.alpha(T.TEXT_MUTED, alpha), size=caption)
      draw.text(bottom, text, value, draw.alpha(T.TEXT, alpha), T.FONT_BOLD)
      x += cell_w + Z.px(24)
    return x

  def _street(self, rect: rl.Rectangle, street: str, h: Align, outer: rl.Rectangle, alpha: float = 1.0) -> None:
    """Draw the street name in the available space and scroll it if needed."""
    if rect.width <= 0:
      return
    text_w = min(rect.width, draw.text_width(street, street_size(), T.FONT_BOLD))
    block = place(rect, text_w, rect.height, h)
    self._street_scroll.draw(block, street, street_size(), draw.alpha(T.TEXT, alpha), T.FONT_BOLD, outer,
                             fade=CONTROL_FILL)


def street_size() -> int:
  """The street name, and the compass tag and weather beside it at the same size."""
  return Z.font_px(28)


def weather_now(rect: rl.Rectangle, icon: str, temperature: str) -> float:
  """The weather icon and temperature at the end of rect, at the street name's size. Returns the width used."""
  text_w = draw.text_width(temperature, street_size(), T.FONT_BOLD)
  w = Z.px(26) + Z.px(8) + text_w
  icon_box, text = row(rl.Rectangle(rect.x + rect.width - w, rect.y, w, rect.height), [Z.px(26), FILL], Z.px(8))
  draw.icon(icon_box, icon, T.TEXT_SECONDARY, Z.px(26))
  draw.text(text, temperature, street_size(), T.TEXT, T.FONT_BOLD)
  return w


def heading_width(heading: str) -> float:
  return draw.text_width(heading, street_size(), T.FONT_EXTRABOLD, tracking=Z.px(1)) + Z.px(22)


def heading_tag(rect: rl.Rectangle, heading: str) -> float:
  """The compass heading as a blue tag, vertically centered at the start of rect. Returns its width."""
  w = heading_width(heading)
  tag = place(rl.Rectangle(rect.x, rect.y, w, rect.height), w, Z.px(40))
  draw.fill(tag, T.ACCENT_SURFACE, Z.px(10))
  draw.text(tag, heading, street_size(), T.ACCENT_TEXT, T.FONT_EXTRABOLD, Align.CENTER, tracking=Z.px(1))
  return w


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


# ── Steering headroom ──

COMFORTABLE, WORKING, AT_LIMIT = "comfortable", "working", "at_limit"
WORKING_FROM, LIMIT_FROM, LIMIT_HOLD = 0.60, 0.85, 0.5
LIMIT_RELEASE = 0.80
LIMIT_LANE_COLOR = rl.Color(255, 138, 77, 255)
LIMIT_BORDER_COLOR = rl.Color(224, 162, 58, 255)


class Headroom:
  """Debounce limit entry and release below 80%, so bumps and threshold noise don't repeat warnings."""

  def __init__(self) -> None:
    self._over_since: float | None = None
    self._at_limit = False

  def stage(self, usage: float, now: float, active: bool = True) -> str:
    """Where steering use stands: comfortable, working, or at the limit.

    Args:
      usage: The share of the steering limit in use; its sign is ignored.
      now: The time in seconds.
      active: Steering is engaged; when it isn't, the stage resets to comfortable.

    Returns:
      COMFORTABLE, WORKING (from WORKING_FROM) or AT_LIMIT. At the limit is entered after LIMIT_HOLD seconds over
      LIMIT_FROM and held until use drops below LIMIT_RELEASE.
    """
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
  """What the headroom arc shows: how much steering is in use, a preview of where it's heading, and the stage."""
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
STAGE_STYLE = {COMFORTABLE: (T.TEXT, None), WORKING: (T.WARNING, 13), AT_LIMIT: (rl.Color(255, 112, 67, 255), 18)}   # mock px
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

  ABOVE_CARD = 23   # mock px: the gap the mock leaves between the arc's ends and the bar, kept above the Help steer card

  def __init__(self, state: Callable[[], ArcState], shape: Callable[[], ArcShape] = lambda: ARC,
               help_steer: Callable[[], bool] = lambda: False):
    """Makes the headroom arc.

    Args:
      state: The arc's state each frame.
      shape: The curve to draw (each mock's ARC).
      help_steer: Whether the Help steer card is up, in the bar's place; the arc then sits above the card.
    """
    super().__init__()
    self._state = state
    self._shape = shape
    self._help_steer = help_steer

  def _render(self, rect: rl.Rectangle) -> None:
    s, shape = self._state(), self._shape()
    half = rect.width * shape.chord / 2
    cx, end_y = rect.x + rect.width / 2, rect.y + rect.height - Z.px(shape.lift)   # rect is the whole road view
    if self._help_steer():
      end_y = min(end_y, help_steer_box(rect).y - Z.px(self.ABOVE_CARD))
    rise = rect.width * shape.rise

    def at(t: float) -> rl.Vector2:
      u = 1 - t
      return rl.Vector2(cx - half * u * u + half * t * t, end_y - 2 * u * t * rise)

    color, thickness = STAGE_STYLE[s.stage]
    thickness = Z.px(thickness) if thickness else Z.px(shape.stroke)
    alpha = 1.0 if s.active else 0.35

    def arc(t0: float, t1: float, width: float, ink: rl.Color) -> None:
      if abs(t1 - t0) < 0.002:
        return
      lo, hi = min(t0, t1), max(t0, t1)
      steps = max(2, int(ARC_STEPS * (hi - lo)))
      draw_stroke([at(lo + (hi - lo) * i / steps) for i in range(steps + 1)], width, ink)

    arc(0.0, 1.0, Z.px(shape.stroke), draw.alpha(T.TEXT, 0.18 * alpha))
    reach = lambda share: 0.5 + 0.5 * max(-1.0, min(1.0, share))  # noqa: E731
    if s.active and abs(s.preview) > abs(s.usage) + 0.05:
      arc(0.5, reach(s.preview), thickness, draw.alpha(color, 0.3))
    arc(0.5, reach(s.usage), thickness, draw.alpha(color, 0.95 * alpha))
    if abs(s.usage) < 0.03:
      rl.draw_circle_v(at(0.5), Z.px(5), draw.alpha(T.TEXT, 0.8 * alpha))


HELP_STEER = (N_("Help steer"), N_("Steering is at its limit for this curve"))


def help_steer_box(rect: rl.Rectangle) -> rl.Rectangle:
  return alerts.box(rect, alerts.WARNING, *HELP_STEER)


class HelpSteer(Component):
  """The at-limit warning, drawn as every other Warning alert is: the amber card along the bottom, in the bar's place (the
  view hides the bar and chips while it shows, as for other alerts). The view requests its one-shot sound through soundd."""
  grow_touch_target = False

  def _render(self, rect: rl.Rectangle) -> None:
    alerts.draw_alert(help_steer_box(rect), alerts.WARNING, *HELP_STEER, 1.0)


# ── New speed limit ──

@dataclass
class LimitOffer:
  """A new-limit card's offer: the limit, the set speed it would mean, its source, and how long it stays up."""
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
               top: Callable[[], float] = lambda: Z.px(16)):
    """top: how far down the card sits, below the turn card while navigating."""
    super().__init__()
    self._offer = offer
    self._top = top
    self._match = self._child(Button(N_("Match"), on_match, ButtonStyle.PRIMARY, height=self.button_height(), font_size=Z.font_px(18),
                                     radius=Z.px(16), weight=T.FONT_EXTRABOLD))
    self._ignore = self._child(Button(N_("Ignore"), on_ignore, ButtonStyle.SECONDARY, height=self.button_height(), font_size=Z.font_px(18),
                                      radius=Z.px(16), weight=T.FONT_BOLD))
    self._zoom = Z.zoom()

  def box(self, rect: rl.Rectangle) -> rl.Rectangle:
    height = self.pad() * 2 + sign_size()[1] + Z.px(14) + self.button_height() + Z.px(14) + Z.px(4)
    return rl.Rectangle(rect.x + Z.px(16), rect.y + self._top(), self.width(), height)

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
    verb = N_("Slow down") if offer.lower else N_("Speed up")
    draw.text(question, t_("{} to {} {}?", verb, f"{offer.target:.0f}", offer.unit), Z.font_px(16), T.TEXT_SECONDARY)
    draw.text(source, t_("From {} · ignored in {} s", offer.source.lower() or 'map', max(0, math.ceil(offer.seconds_left))), Z.font_px(13),
              T.TEXT_MUTED)
    ignore, match = row(buttons, [FILL, FILL], Z.px(10))
    self._ignore.render(ignore)
    self._match.render(match)
    draw.fill(bar, T.TRACK, Z.px(2))
    left = max(0.0, min(1.0, offer.seconds_left / offer.total)) if offer.total > 0 else 0.0
    if left > 0:
      draw.fill(rl.Rectangle(bar.x, bar.y, max(bar.height, bar.width * left), bar.height), T.ACCENT, Z.px(2))


# ── Speed, speed limit sign and turn card, as in the onroad mocks ──

HUD_PILL = rl.Color(0x0B, 0x0D, 0x10, 230)
SPEED_UNIT = rl.Color(0xC9, 0xD0, 0xDA, 255)
TURN_LINE = rl.Color(0xC9, 0xD8, 0xEA, 255)
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


def draw_speed(rect: rl.Rectangle, speed: float, unit: str, offset_y: float = 0.0, left: bool = False, right: bool = False,
               now: float = 0.0) -> None:
  """The current speed, top center on a dark pill. A blinker adds our turn signal on its side; the number stays centered."""
  number, size = f"{round(speed)}", Z.font_px(62)
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


def draw_speed_limit(tile: rl.Rectangle, limit: str, vienna: bool, note: str = "") -> None:
  """The posted limit on a dark tile.

  Args:
    tile: The tile.
    limit: The limit, formatted.
    vienna: Draw a round Vienna Convention sign instead of a U.S. one.
    note: Developer View's source and offset ("MAP · +3").
  """
  draw.fill(tile, rl.Color(0x0B, 0x0D, 0x10, 255), Z.px(14))
  draw_sign(place(tile, *sign_size()), limit, vienna, note)


def draw_sign(area: rl.Rectangle, limit: str, vienna: bool, note: str = "") -> None:
  """A US sign filling area, or Vienna's red ring centered on it (a little wider than the US sign, as in the mock). A note
  sits small under the US sign's number, or under Vienna's ring."""
  if vienna:
    sign = place(area, Z.px(72), Z.px(72))
    draw.fill(sign, VIENNA_RED, sign.width / 2)
    draw.fill(inset(sign, Z.px(8)), rl.WHITE, sign.width / 2)
    draw.text(sign, limit, Z.font_px(28), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
    if note:
      draw.text(rl.Rectangle(area.x - Z.px(10), sign.y + sign.height, area.width + Z.px(20), Z.px(14)), note, Z.font_px(9), T.TEXT_TERTIARY,
                T.FONT_EXTRABOLD, Align.CENTER)
    return
  sign = area
  draw.fill(sign, rl.WHITE, Z.px(8))
  draw.stroke(inset(sign, Z.px(2)), T.BG, Z.px(7), Z.px(3))
  body = inset(sign, x=Z.px(5), y=Z.px(9))
  top, middle, number, small = column(body, [Z.px(12), Z.px(12), FILL, Z.px(11) if note else 0])
  draw.text(top, "SPEED", Z.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)   # the US sign's own words: never translated
  draw.text(middle, "LIMIT", Z.font_px(10), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  draw.text(number, limit, Z.font_px(28 if note else 32), T.BG, T.FONT_EXTRABOLD, Align.CENTER)
  if note:
    draw.text(small, note, Z.font_px(9), T._hex("3A4552"), T.FONT_EXTRABOLD, Align.CENTER)


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
  draw.fill(tile, draw.alpha(rl.Color(0x0B, 0x0D, 0x10, 255), opacity), Z.px(14))
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


def turn_card_width() -> int:
  return Z.px(330)


def turn_card_top() -> int:
  return Z.px(16)


def turn_below_sign() -> int:
  """The card's top while the sign holds the corner."""
  return sign_margin() + sign_tile_size()[1] + Z.px(12)


TURN_SCROLL = Scroller()   # the instruction line scrolls when it doesn't fit, as the street name does


def draw_turn_card(rect: rl.Rectangle, distance: str, text: str, maneuver: str, modifier: str,
                   top: float | None = None) -> rl.Rectangle:
  """The next turn, top left (below the sign when there is one): its arrow, the distance and the instruction.

  Args:
    rect: The road view; an instruction that doesn't fit scrolls, clipped inside it.
    distance: The distance to the turn, formatted.
    text: The instruction.
    maneuver: The turn's maneuver, for its arrow.
    modifier: The maneuver's direction.
    top: Where the card's top goes; below the sign by default.

  Returns:
    The card's box.
  """
  top = turn_card_top() if top is None else top
  lines = [draw.line_height(Z.font_px(30)), draw.line_height(Z.font_px(17))]
  box = rl.Rectangle(rect.x + sign_margin(), rect.y + top, turn_card_width(), max(Z.px(54), sum(lines)) + Z.px(28))
  draw.fill(box, T.ACCENT_SURFACE, Z.px(20))
  body = inset(box, x=Z.px(18), y=Z.px(14))
  icon, words = row(body, [Z.px(54), FILL], Z.px(16))
  draw.icon(icon, turn_icon(maneuver, modifier), T.TEXT, Z.px(54))
  dist, line = column(place(words, words.width, sum(lines) + Z.px(2)), lines, Z.px(2))
  draw.text(dist, distance, Z.font_px(30), T.TEXT, T.FONT_EXTRABOLD)
  TURN_SCROLL.draw(line, text, Z.font_px(17), TURN_LINE, T.FONT, rect, fade=T.ACCENT_SURFACE)
  return box

