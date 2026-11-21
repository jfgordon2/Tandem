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
    ("nav", False, replace(base, bar=replace(base.bar, navigating=True, arrive="4:52 PM", left="12 min · 8.4 mi", street="SE Hawthorne Blvd"),
                           chips=(), turn=("0.4 mi", "Turn right onto SE 39th Ave", "turn", "right"))),
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
    if name == "nav":
      save(f"{out}/onroad_nav.png")   # design/onroadnav.html
  Z.set_text(False)
  routing_shots(frame, save, out)
  signal_shots(frame, save, out, base)


def signal_shots(frame: Callable, save: Callable, out: str, base: DriveDisplay) -> None:
  """Each Whimsy Turn Signal partway across the road above the bar, signalling left (design/signalpicker.html,
  signalunicorn.html), saved as signal_<pack>.png."""
  import time
  from types import SimpleNamespace
  from openpilot.selfdrive.ui.tandem.onroad.layers import bar_height, bar_margin
  from openpilot.selfdrive.ui.tandem.onroad.turn_signals import GAP, TurnSignalRenderer
  noop = lambda *args: None  # noqa: E731
  car = SimpleNamespace(leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False)
  sample = replace(base, bar=replace(base.bar, set_speed=48, street="Market Street"), speed=44, chips=())
  rect = rl.Rectangle(0, 0, 2160, 1080)
  for slug, t in (("frog", 0.3), ("pouncing_cat", 0.5), ("bouncing_ball", 1.4), ("unicorn_rider", 0.42)):
    renderer = TurnSignalRenderer()
    overlay = OnroadOverlay(lambda: sample, noop, noop, noop, noop, clock=lambda: .5)

    def render(renderer: TurnSignalRenderer = renderer, overlay: OnroadOverlay = overlay, slug: str = slug) -> None:
      mock_road(rect)
      inner = road_rect(rect)
      renderer.render(inner, slug, car, 1, bottom_margin=bar_height() + bar_margin() + GAP)
      overlay.render(rect)

    frame(render)
    renderer._started_at = time.monotonic() - t   # a frame partway across
    frame(render)
    save(f"{out}/signal_{slug}.png")


def routing_shots(frame: Callable, save: Callable, out: str) -> None:
  """The routing chip in each approved state (design/valhalla2-chip-*.html): a route to Market Street, at 44 under a 45 sign."""
  from openpilot.selfdrive.ui.tandem.onroad.status import routing_chip, routing_state
  now = 100.0

  def routing(navigation: str, tandem: dict | None = None, recalculating: bool = False, offline_only: bool = False) -> Chip:
    chip = routing_chip(routing_state(navigation, tandem, tandem, recalculating, now), now, offline_only)
    assert chip is not None
    return chip
  trip = BarState(engaged=True, set_speed=48, street="Market Street", navigating=True, arrive="5:18 PM", left="12 min · 8.4 mi")
  waiting = replace(trip, arrive="", left="")
  base = DriveDisplay(trip, 44, posted="45", monitor=1.0, arc=ArcState(0.18, 0.0, True))
  paused = Chip("pause_signal", "Steering paused for signal", ChipTone.PAUSED, "signal")
  offline = {"status": "ready", "provider": "offline", "fallback": True}
  online = {"status": "ready", "provider": "online", "fallback": True}
  cases = (
    ("valhalla2-chip-recalculate", base, (routing("routing", recalculating=True),)),
    ("valhalla2-chip-offline-fallback", base, (routing("guiding", offline),)),
    ("valhalla2-chip-online-fallback", base, (routing("guiding", online),)),
    ("valhalla2-chip-strict-unavailable", replace(base, bar=waiting), (routing("routeUnavailable", {"status": "no_route"}, offline_only=True),)),
    ("valhalla2-chip-gps", base, (routing("waitingForLocation"),)),
    ("valhalla2-chip-stack", base, (routing("routing", recalculating=True), paused)),   # newest nearest the bar (ChipStack)
    ("valhalla2-chip-first-route", replace(base, bar=waiting), (routing("routing"),)),
  )
  noop = lambda *args: None  # noqa: E731
  for name, sample, chips in cases:
    shown = replace(sample, chips=tuple((chip, 1.0) for chip in chips))
    rect = rl.Rectangle(0, 0, 2160, 1080)
    overlay = OnroadOverlay(lambda shown=shown: shown, noop, noop, noop, noop, clock=lambda: .5)

    def render(rect: rl.Rectangle = rect, overlay: OnroadOverlay = overlay) -> None:
      mock_road(rect)
      overlay.render(rect)
    for _ in range(2):
      frame(render)
    save(f"{out}/{name}.png")
