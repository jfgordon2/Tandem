"""Render the driver camera preview's overlay (design/drivercamera.html) over a stand-in camera picture."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.drivercamera import draw_overlay, face_box
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """A face found, driver monitoring watching and attentive."""
  rect = rl.Rectangle(0, 0, 2160, 1080)

  def render() -> None:
    rl.clear_background(rl.Color(0x2A, 0x2E, 0x33, 255))
    draw_overlay(rect, False, face_box(0.05, 0.1, rect), 1.0, True, 1.0)
  frame(render)
  frame(render)
  save(f"{out}/drivercamera.png")
