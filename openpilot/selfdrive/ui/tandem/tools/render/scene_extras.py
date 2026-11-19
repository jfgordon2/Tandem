"""Render the pedal tiles, border highlights and model chip over the stand-in road (design/onroadextras.html)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.onroad import extras
from openpilot.selfdrive.ui.tandem.onroad.layers import ArcState, BarState
from openpilot.selfdrive.ui.tandem.onroad.overlay import OnroadOverlay
from openpilot.selfdrive.ui.tandem.onroad.state import DriveDisplay
from openpilot.selfdrive.ui.tandem.tools.render.scene_onroad_port import mock_road
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Braking with the left signal on and a car in the right blind spot."""
  sample = DriveDisplay(BarState(engaged=True, set_speed=63, street="County Road F31"), 58, posted="60", left=True, monitor=1.0,
                        arc=ArcState(0.2, 0.0, True), pedals=(0.9, extras.IDLE), border=(extras.SIGNAL_BORDER, extras.BLIND_SPOT_BORDER),
                        model=("active", 1.0))
  rect = rl.Rectangle(0, 0, 2160, 1080)
  overlay = OnroadOverlay(lambda: sample, lambda: None, lambda _: None, lambda: None, lambda *_: None)

  def render() -> None:
    rl.clear_background(rl.BLACK)
    mock_road(rect)
    overlay.render(rect)
  frame(render)
  frame(render)
  save(f"{out}/onroadextras.png")
