"""StarPilot's optional onroad visuals in Essentials (design/onroadextras.html).

Each keeps StarPilot's own switch and rule for when it shows; only the drawing is ours:
- Pedals (Lead Insights, PedalsOnUI): brake and gas tiles under the driver monitor tile.
- Model source (external GPU): a chip under them, using StarPilot's widget for its state and fade.
- Compass: the heading as a tag in the bar (layers.OnroadBar), from StarPilot's compass text.
- Stopping point: a white line across the end of the path with a distance tag, not a red STOP octagon.
- Adjacent lanes and blind spot: a faint blue wash, amber for a car in the blind spot; path edges in light blue.
- Radar points: white dots ringed in black. The curve glow keeps StarPilot's timing in our blue (see view.py).
- Border: the signalling side blinks blue, a blind-spot side holds red.

The functions take what they need as arguments, so they render and test without a car.
"""
from __future__ import annotations

import math

import numpy as np
import pyray as rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.layout import FILL, inset, place, row
from openpilot.selfdrive.ui.tandem.i18n import N_, t_

BRAKE_FILL, BRAKE_INK = T._hex("3A1F24"), T._hex("FF8A8A")
GAS_FILL, GAS_INK = T._hex("173A2A"), T.SUCCESS_TEXT
TILE_FILL = rl.Color(0x0B, 0x0D, 0x10, 0xCC)
TAG_FILL = rl.Color(0x0B, 0x0D, 0x10, 0xE6)
LANE_WASH = T.ACCENT
BLIND_SPOT_WASH = T.WARNING
EDGE_INK = T._hex("A9D3FB")
SIGNAL_BORDER = T.ACCENT
BLIND_SPOT_BORDER = T._hex("E5646F")
RADAR_RING = rl.Color(0x0B, 0x0D, 0x10, 0xDC)
RADAR_DOT = T.TEXT
RADAR_TEXTURE_CENTER = 11.0   # StarPilot's marker texture is 22 px square


# ── Turn signal ──

# StarPilot's signal animations Essentials offers as Whimsy, by SignalAnimation slug. Its renderer draws them (view.py).
WHIMSY_SIGNALS = {"frog": N_("Jumping frog"), "pouncing_cat": N_("Pouncing cat"), "bouncing_ball": N_("Bouncing ball")}
SIGNAL_GAP = T.px(12)   # between an animation and the bar


# ── Path and lead marker (design/leadmarker.html) ──

PATH_COLOR = "#5AAAF880"   # StarPilot's PathColor for the Standard and Thin path styles: our blue at 50%
LEAD_INK = T.TEXT
LEAD_BRAKING_INK = T.WARNING
LEAD_OUTLINE = rl.Color(0x0B, 0x0D, 0x10, 0xB3)
LEAD_UNSURE = 0.45          # opacity when the model isn't sure the car ahead is there
LEAD_FAINT = 0.35           # a second car ahead, and cars in the next lanes
LEAD_SETTLE = 0.25          # s for a new car's bar to grow in
LEAD_JUMP = 8.0             # m: a lead this much nearer than the last one is a new car (a cut-in)


def lead_bar_rect(chevron) -> rl.Rectangle | None:
  """The bar under a lead car, from upstream's chevron for it: the chevron's tip is the car's ground point and its height
  (sz) scales with distance, so the bar keeps the chevron's place and size."""
  if not chevron or len(chevron) < 3:
    return None
  (_, base_y), (x, y), _ = chevron
  sz = base_y - y
  if sz <= 0:
    return None
  w, h = sz * 2.5, max(T.px(7), sz * 0.16)   # the chevron's width, about the car's at that distance
  return rl.Rectangle(x - w / 2, y + sz * 0.08, w, h)


def draw_lead_bar(rect: rl.Rectangle, color: rl.Color, opacity: float = 1.0, scale: float = 1.0, outline: bool = True) -> None:
  """The bar, grown from its center by scale (the settle-in), with a thin dark outline that keeps white readable on a bright
  road."""
  if opacity <= 0.01 or scale <= 0.01:
    return
  w = rect.width * scale
  bar = rl.Rectangle(rect.x + (rect.width - w) / 2, rect.y, w, rect.height)
  if outline:
    edge = T.px(2)
    out = rl.Rectangle(bar.x - edge, bar.y - edge, bar.width + edge * 2, bar.height + edge * 2)
    draw.fill(out, draw.alpha(LEAD_OUTLINE, opacity), out.height / 2)
  draw.fill(bar, draw.alpha(color, opacity), bar.height / 2)


class LeadSettle:
  """How far a lead's bar has grown in (0 to 1): a car that appears, or one much nearer than the last (a cut-in), starts
  again from small and grows over LEAD_SETTLE."""

  def __init__(self):
    self._since: float | None = None
    self._distance: float | None = None

  def update(self, present: bool, distance: float, now: float) -> float:
    if not present:
      self._since = self._distance = None
      return 0.0
    if self._since is None or (self._distance is not None and self._distance - distance > LEAD_JUMP):
      self._since = now
    self._distance = distance
    t = min(1.0, (now - self._since) / LEAD_SETTLE)
    return 1.0 - (1.0 - t) ** 3   # ease out


# ── Pedals ──

def pedal_levels(params, car_state, starpilot_car_state=None) -> tuple[float, float] | None:
  """(brake, gas) from 0.25 (idle) to 1, as StarPilot's pedal icons reckon them; None when they're off."""
  if not params.get_bool("PedalsOnUI") or car_state is None:
    return None
  standstill = bool(getattr(car_state, "standstill", False))
  brake_lights = bool(getattr(car_state, "brakeLights", False) or getattr(car_state, "brakeLightsDEPRECATED", False)
                      or getattr(car_state, "regenBraking", False) or getattr(starpilot_car_state, "brakeLights", False))
  accel = float(getattr(car_state, "aEgo", 0.0))
  if params.get_bool("DynamicPedalsOnUI"):
    brake = 1.0 if standstill else (min(1.0, max(0.25, abs(accel))) if accel < -0.25 else 0.25)
    gas = min(1.0, max(0.25, accel)) if accel > 0.0 else 0.25
    return brake, gas
  if params.get_bool("StaticPedalsOnUI"):
    return (1.0 if (standstill or brake_lights or accel < -0.25) else 0.25), (1.0 if accel > 0.25 else 0.25)
  return 1.0, 1.0


def draw_pedal(tile: rl.Rectangle, kind: str, level: float) -> None:
  """A brake or gas tile: lit red or green as the pedal works, a dim dark tile when idle."""
  lit = max(0.0, min(1.0, (level - 0.25) / 0.75))
  fill, ink = (BRAKE_FILL, BRAKE_INK) if kind == "brake" else (GAS_FILL, GAS_INK)
  draw.fill(tile, TILE_FILL, T.px(16))
  if lit > 0:
    draw.fill(tile, draw.alpha(fill, lit), T.px(16))
  color = draw.alpha(ink if lit > 0 else T.TEXT_SECONDARY, 0.35 + 0.65 * lit)
  w, h = (T.px(16), T.px(8)) if kind == "brake" else (T.px(9), T.px(18))
  shape = place(tile, w, h)
  rl.draw_rectangle_rounded_lines_ex(shape, 0.35, 6, T.px(2.4), color)


def draw_pedals(top: rl.Rectangle, levels: tuple[float, float]) -> float:
  """Brake then gas, stacked below top (the driver monitor tile). Returns the bottom of the stack."""
  y = top.y + top.height + T.px(10)
  for kind, level in zip(("brake", "gas"), levels, strict=True):
    draw_pedal(rl.Rectangle(top.x, y, top.width, top.width), kind, level)
    y += top.width + T.px(10)
  return y


# ── Model source ──

MODEL_LABELS = {   # StarPilot's ModelSourceStatus value: label and chip tone
  "loading": (N_("Loading model"), "accent"),
  "active": (N_("Big model"), "success"),
  "failed": (N_("Big model failed"), "warning"),
  "fallback_engaged": (N_("Small model in use"), "warning"),
}
_TONES = {"accent": (T.ACCENT_SURFACE, T.ACCENT_CHIP_TEXT, T.ACCENT_TEXT), "success": (T.SUCCESS_SURFACE, T.SUCCESS_CHIP_TEXT, T.SUCCESS_TEXT),
          "warning": (T.WARNING_SURFACE, T.WARNING_CHIP_TEXT, T.WARNING)}


def draw_model_chip(right: float, y: float, status: str, alpha: float) -> None:
  """The external-GPU model state as a status chip, right-aligned at right."""
  label, tone = MODEL_LABELS[status]
  fill, ink, icon = _TONES[tone]
  size, h = T.font_px(17), T.px(52)
  w = T.px(14) + T.px(24) + T.px(10) + draw.text_width(label, size, T.FONT_SEMIBOLD) + T.px(16)
  chip = rl.Rectangle(right - w, y, w, h)
  draw.fill(chip, draw.alpha(fill, alpha), T.px(14))
  glyph, words = row(inset(chip, left=T.px(14), right=T.px(16)), [T.px(24), FILL], T.px(10))
  draw.icon(glyph, "model", draw.alpha(icon, alpha), T.px(24))
  draw.text(words, label, size, draw.alpha(ink, alpha), T.FONT_SEMIBOLD)


class ModelChip:
  """StarPilot's model-source widget keeps deciding the state and when it fades; this draws it as our chip."""

  def __init__(self, widget):
    self._widget = widget

  def render(self, right: float, y: float) -> None:
    widget = self._widget
    if not widget.is_visible:
      return
    widget._update_state()
    status = widget._status
    if status is None:
      return
    now = rl.get_time()
    if status is not widget._shown_status:   # as StarPilot's _render: show a change for PERSISTENCE_SECONDS, loading always
      widget._fade_time = now
      widget._shown_status = status
    alpha = widget._alpha_filter.update(status.value == "loading" or 0 < now - widget._fade_time < widget.PERSISTENCE_SECONDS)
    if alpha < 1e-2:
      return
    if status.value == "loading":
      alpha *= 0.35 + 0.65 * (0.5 - 0.5 * math.cos(now * 6.0))
    draw_model_chip(right, y, status.value, alpha)


# ── Compass ──

def heading(compass_text: str | None) -> str:
  """StarPilot's compass text ("- NE -") as the bar's tag ("NE")."""
  return (compass_text or "").strip(" -")


# ── On the road ──

def path_end(projected: np.ndarray) -> tuple[rl.Vector2, rl.Vector2] | None:
  """The far end of the path polygon ([L0..Lk-1, Rk-1..R0]): its left and right corners, where StarPilot puts the stop."""
  if projected is None or len(projected) < 4:
    return None
  mid = len(projected) // 2
  left, right = projected[mid - 1], projected[mid]
  return rl.Vector2(float(left[0]), float(left[1])), rl.Vector2(float(right[0]), float(right[1]))


def stop_text(distance_m: float, metric: bool) -> str:
  return t_("{} m", round(distance_m)) if metric else t_("{} ft", round(distance_m * 3.28084))


def draw_stopping_point(ends: tuple[rl.Vector2, rl.Vector2], distance: str | None) -> None:
  """A white line across the path where the car plans to stop, and the distance in a tag above it."""
  left, right = ends
  cx, cy = (left.x + right.x) / 2, (left.y + right.y) / 2
  half = max(T.px(26), abs(right.x - left.x) / 2)
  rl.draw_line_ex(rl.Vector2(cx - half, cy), rl.Vector2(cx + half, cy), T.px(6), T.TEXT)
  for x in (cx - half, cx + half):
    rl.draw_circle_v(rl.Vector2(x, cy), T.px(3), T.TEXT)
  if not distance:
    return
  size = T.font_px(16)
  w = T.px(12) + T.px(16) + T.px(8) + draw.text_width(distance, size, T.FONT_MONO_BOLD) + T.px(12)
  tag = rl.Rectangle(cx - w / 2, cy - T.px(14) - T.px(36), w, T.px(36))
  draw.fill(tag, TAG_FILL, T.px(10))
  draw.stroke(tag, T.TRACK, T.px(10), T.px(1))
  glyph, words = row(inset(tag, x=T.px(12)), [T.px(16), FILL], T.px(8))
  draw.icon(glyph, "stop", T.TEXT, T.px(16))
  draw.text(words, distance, size, T.TEXT, T.FONT_MONO_BOLD)


def lane_gradient(color: rl.Color, strength: float):
  """A wash that fades out toward the horizon, as StarPilot's lane gradient does."""
  from openpilot.system.ui.lib.shader_polygon import Gradient
  return Gradient(start=(0.0, 1.0), end=(0.0, 0.0), stops=[0.0, 0.5, 1.0],
                  colors=[draw.alpha(color, strength), draw.alpha(color, strength * 0.8), draw.alpha(color, 0.0)])


def draw_lanes(rect: rl.Rectangle, sides: list[tuple[np.ndarray, str | None]]) -> None:
  """sides: (polygon, "blind_spot" | "lane" | None) for the left and right lanes."""
  from openpilot.system.ui.lib.shader_polygon import draw_polygon
  for vertices, kind in sides:
    if kind is None or vertices is None or len(vertices) < 4:
      continue
    color, strength = (BLIND_SPOT_WASH, 0.30) if kind == "blind_spot" else (LANE_WASH, 0.14)
    draw_polygon(rect, vertices, gradient=lane_gradient(color, strength))


def draw_path_edges(rect: rl.Rectangle, outer: np.ndarray, inner: np.ndarray) -> None:
  """The strip between the path and its edge, in light blue fading toward the horizon."""
  from openpilot.system.ui.lib.shader_polygon import draw_polygon
  if outer is None or inner is None or len(outer) < 4 or len(inner) < 4:
    return
  draw_polygon(rect, np.vstack([outer, inner[::-1]]), gradient=lane_gradient(EDGE_INK, 0.75))


def draw_radar_marker() -> None:
  """StarPilot's radar marker texture, redrawn: a white dot ringed in black (22 px texture)."""
  center = rl.Vector2(RADAR_TEXTURE_CENTER, RADAR_TEXTURE_CENTER)
  rl.draw_circle_v(center, 9.0, RADAR_RING)
  rl.draw_circle_v(center, 6.0, RADAR_DOT)


# ── Border ──

def border_halves(signal_on: bool, blind_spot_on: bool, left_signal: bool, right_signal: bool, left_blind: bool, right_blind: bool,
                  now: float) -> tuple[rl.Color | None, rl.Color | None]:
  """StarPilot's rules (SignalMetrics, BlindSpotMetrics): a blind spot holds red, a signal blinks blue every 0.5 s."""
  blink = (int(now * 1000) % 1000) < 500

  def half(blind: bool, signal: bool) -> rl.Color | None:
    if blind and blind_spot_on:
      return BLIND_SPOT_BORDER
    if signal and signal_on and blink:
      return SIGNAL_BORDER
    return None
  return half(left_blind, left_signal), half(right_blind, right_signal)


def draw_border_halves(rect: rl.Rectangle, border_rect: rl.Rectangle, roundness: float, width: float,
                       colors: tuple[rl.Color | None, rl.Color | None]) -> None:
  for i, color in enumerate(colors):
    if color is None:
      continue
    rl.begin_scissor_mode(int(rect.x + i * (rect.width // 2)), int(rect.y), int(rect.width // 2), int(rect.height))
    rl.draw_rectangle_rounded_lines_ex(border_rect, roundness, 10, width, color)
    rl.end_scissor_mode()
