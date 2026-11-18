"""StarPilot's optional onroad visuals, drawn in Essentials (design/onroadextras.html).

Each keeps StarPilot 7's own setting and rule for when it shows; only the drawing is ours:
- Pedals: brake and gas tiles under the driver monitor tile, lit by StarPilot's wheel feedback (measured acceleration,
  full at ±2 m/s², with its fade), while its wheel brake and acceleration colors setting is on (Lead Insights).
- Border: the signalling side blinks blue and a blind-spot side holds red, while StarPilot's signal and blind-spot
  border settings are on (Display › Blind Spot Highlights).

Release's stopping point, adjacent lanes, radar points and signal animations were StarPilot 6 settings, gone in 7.
The functions take what they need as arguments, so they render and test without a car.
"""
from __future__ import annotations

from typing import Any

from openpilot.starpilot.ui.raylib import rl

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.layout import place

BRAKE_FILL, BRAKE_INK = T._hex("3A1F24"), T._hex("FF8A8A")
GAS_FILL, GAS_INK = T._hex("173A2A"), T.SUCCESS_TEXT
TILE_FILL = rl.Color(0x0B, 0x0D, 0x10, 0xCC)
SIGNAL_BORDER = T.ACCENT
BLIND_SPOT_BORDER = T._hex("E5646F")
IDLE = 0.25   # a pedal tile's level when nothing is happening


class Pedals:
  """The pedal tiles' levels from StarPilot's own wheel feedback fade (starpilot/ui/wheel_feedback.py)."""

  def __init__(self) -> None:
    from openpilot.starpilot.ui.wheel_feedback import WheelFeedbackFade
    self._fade = WheelFeedbackFade()

  def update(self, acceleration: float | None, enabled: bool, now_ns: int, drive_frame: int | None) -> tuple[float, float] | None:
    """(brake, gas), each from IDLE to 1, or None while StarPilot's setting is off.

    Args:
      acceleration: StarPilot's observed acceleration (OnroadState.wheel_acceleration), m/s².
      enabled: StarPilot's wheel brake and acceleration colors setting.
      now_ns: Monotonic nanoseconds.
      drive_frame: The drive, so a new one starts from rest.
    """
    self._fade.update(acceleration, enabled, now_ns, drive_frame)
    if not enabled:
      return None
    amount = float(self._fade._amount)   # StarPilot's faded tint, -1 (braking) to 1 (accelerating)
    return IDLE + (1 - IDLE) * max(0.0, -amount), IDLE + (1 - IDLE) * max(0.0, amount)


def draw_pedal(tile: rl.Rectangle, kind: str, level: float) -> None:
  """A brake or gas tile: lit red or green as the pedal works, a dim dark tile when idle."""
  lit = max(0.0, min(1.0, (level - IDLE) / (1 - IDLE)))
  fill, ink = (BRAKE_FILL, BRAKE_INK) if kind == "brake" else (GAS_FILL, GAS_INK)
  draw.fill(tile, TILE_FILL, T.px(16))
  if lit > 0:
    draw.fill(tile, draw.alpha(fill, lit), T.px(16))
  color = draw.alpha(ink if lit > 0 else T.TEXT_SECONDARY, 0.35 + 0.65 * lit)
  w, h = (T.px(16), T.px(8)) if kind == "brake" else (T.px(9), T.px(18))
  rl.draw_rectangle_rounded_lines_ex(place(tile, w, h), 0.35, 6, T.px(2.4), color)


def draw_pedals(top: rl.Rectangle, levels: tuple[float, float]) -> float:
  """Brake then gas, stacked below top (the driver monitor tile). Returns the bottom of the stack."""
  y = top.y + top.height + T.px(10)
  for kind, level in zip(("brake", "gas"), levels, strict=True):
    draw_pedal(rl.Rectangle(top.x, y, top.width, top.width), kind, level)
    y += top.width + T.px(10)
  return y


def border_halves(signal_on: bool, blind_spot_on: bool, left_signal: bool, right_signal: bool, left_blind: bool, right_blind: bool,
                  now: float) -> tuple[Any, Any]:
  """Each side's border color, or None: a blind spot holds red, a signal blinks blue every 0.5 s (StarPilot's rules)."""
  blink = (int(now * 1000) % 1000) < 500

  def half(blind: bool, signal: bool) -> Any:
    if blind and blind_spot_on:
      return BLIND_SPOT_BORDER
    if signal and signal_on and blink:
      return SIGNAL_BORDER
    return None
  return half(left_blind, left_signal), half(right_blind, right_signal)


def draw_border_halves(rect: rl.Rectangle, border: rl.Rectangle, radius: float, width: float, colors: tuple[Any, Any]) -> None:
  """Each colored side over the border's left or right half."""
  for i, color in enumerate(colors):
    if color is None:
      continue
    rl.begin_scissor_mode(int(rect.x + i * (rect.width // 2)), int(rect.y), int(rect.width // 2), int(rect.height))
    draw.stroke(border, color, radius, width)
    rl.end_scissor_mode()
