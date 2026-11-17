"""Render first-run setup's first question over the test stand-ins (design/setup.html)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.setup import Setup, SetupWindow
from openpilot.selfdrive.ui.tandem.tests.test_defaults import BatchStore
from openpilot.selfdrive.ui.tandem.tests.test_display_alerts_port import FakeRoad
from openpilot.selfdrive.ui.tandem.tools.render.scene_driving import example_owner
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """The driving style question, Standard preselected."""
  window = SetupWindow(Setup(BatchStore(), example_owner().rows, FakeRoad(), lambda: None))  # type: ignore[arg-type]
  frame(lambda: window.render(rl.Rectangle(0, 0, 2160, 1080)))
  frame(lambda: window.render(rl.Rectangle(0, 0, 2160, 1080)))
  save(f"{out}/setup.png")
