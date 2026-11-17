"""Render release's Device Report and Developer panels with sample native owners."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from openpilot.selfdrive.ui.tandem.settings.developer import DeveloperPanel
from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.report import Report, report_section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tools.render.scene_device import ExampleDevice
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Capture the two release sections by opening them in order."""
  model = Report(Mock(), lambda: True, Mock(), Mock())
  native, params = Mock(), Mock()
  params.get_bool.return_value = False
  params.get.return_value = None
  native._joystick_toggle.is_visible = native._alpha_long_toggle.is_visible = True

  def developer() -> DeveloperPanel:
    """Use parked native capabilities and no SSH keys, as in the release sample."""
    return DeveloperPanel(native, params, Mock(), lambda: True, lambda: True, Mock())

  sections = [
    Section("General", lambda: None), Section("Backups", lambda: None), Section("Storage & Data", lambda: None),
    Section("RAM", lambda: None), Section("Report a Problem", lambda: report_section(model, window)),
    Section("Developer", developer),
  ]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, ExampleDevice(), sections)}, initial=Tab.DEVICE)
  window.show_event()

  def draw() -> None:
    """Draw the Device window at its device resolution."""
    window.render(rl.Rectangle(0, 0, 2160, 1080))

  for index, name in ((5, "report"), (6, "developer")):
    window.top.select(index)
    for _ in range(3):
      frame(draw)
    save(f"{out}/stage4-device-{name}.png")
