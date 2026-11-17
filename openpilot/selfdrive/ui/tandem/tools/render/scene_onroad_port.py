"""Render the seven approved driving states with fake telemetry, through release's layers (onroad/layers.py)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.onroad import alerts, size as Z
from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState, LimitOffer
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay, road_rect
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay, DrivingAlert, LimitDecision, Proposal
from openpilot.selfdrive.ui.tandem.onroad.status import Chip, ChipTone
from openpilot.starpilot.ui.raylib import rl


def mock_road(rect: rl.Rectangle) -> None:
  """Stand in for the native camera and model layer in the design mocks."""
  inner = road_rect(rect)

  def point(x: float, y: float) -> rl.Vector2:
    return rl.Vector2(inner.x + x * inner.width / 1093, inner.y + y * inner.height / 531)

  top, horizon = point(0, 0), point(0, 230)
  draw.fill(inner, rl.Color(0x13, 0x22, 0x31, 255))
  draw.fill(rl.Rectangle(top.x, top.y, inner.width, horizon.y - top.y), rl.Color(0x0F, 0x1A, 0x24, 255))
  edge = rl.Color(0x5C, 0x6B, 0x7A, 255)
  rl.draw_line_ex(point(520, 226), point(116, 531), T.px(5), edge)
  rl.draw_line_ex(point(576, 226), point(984, 531), T.px(5), edge)
  rl.draw_triangle_strip([point(377, 531), point(729, 531), point(534, 228), point(560, 228)], 4, rl.Color(0x24, 0x47, 0x6C, 255))


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  curve = (Chip("curve", "Slowing for curve", ChipTone.INFO, "curve"), 1.0)
  base = DriveDisplay(BarState(engaged=True, set_speed=63, street="County Road F31"), 62, posted="60", left=True, monitor=1.0,
                      arc=ArcState(0.29, 0.0, True), chips=(curve,))
  proposal = Proposal(LimitDecision("fixture", 1, 1, 55 / 2.236936), LimitOffer(55, 58, "mph", "map", 18, 30))
  ram = (Chip("low_memory", "Low on RAM · 91% used", ChipTone.ALERT, "memory"), 1.0)
  cases = (
    ("engaged", False, base),
    ("factory-cruise", False, replace(base, bar=replace(base.bar, can_adjust=False), chips=())),
    ("inactive", False, replace(base, bar=BarState(street=base.bar.street), left=False, arc=ArcState(), chips=())),
    ("new-limit", True, replace(base, bar=replace(base.bar, set_speed=48), speed=45, left=False, proposal=proposal, chips=())),
    ("warning", True, replace(base, attention_warning=True, alert=DrivingAlert(alerts.WARNING, "Pay attention", "Look at the road ahead"))),
    ("critical", False, DriveDisplay(alert=DrivingAlert(alerts.CRITICAL, "TAKE CONTROL IMMEDIATELY", "System Unresponsive"))),
    ("low-ram", True, replace(base, chips=(ram, curve))),
  )
  noop = lambda *args: None  # noqa: E731
  for name, larger, sample in cases:
    Z.set_text(larger)
    rect = rl.Rectangle(0, 0, 2160, 1080)
    overlay = OnroadOverlay(lambda sample=sample: sample, noop, noop, noop, noop, clock=lambda: .5)

    def render(sample: DriveDisplay = sample, rect: rl.Rectangle = rect, overlay: OnroadOverlay = overlay) -> None:
      if sample.alert is None or sample.alert.level != alerts.CRITICAL:
        mock_road(rect)
      overlay.render(rect)

    for _ in range(2):
      frame(render)
    save(f"{out}/stage4-onroad-{name}.png")
  Z.set_text(False)
