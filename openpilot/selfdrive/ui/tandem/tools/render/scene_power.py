"""Device › Power (design/devicepower.html): custom parked limits, Aggressive Cooling off and the drive state on Auto."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.power import COOLING, CUSTOM, ENABLED, HOURS, VOLTS, Power, power_panel
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tests.test_power import Drive
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner
from openpilot.selfdrive.ui.tandem.tools.render.scene_device import ExampleDevice
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  owner = Owner({"parked_power": {ENABLED: CUSTOM, HOURS: "6 h", VOLTS: "12.2 V"}, "power": {COOLING: "Off"}})
  owner.pages["parked_power"][HOURS] = replace(owner.pages["parked_power"][HOURS], choices=("1 h", "6 h", "30 h"))
  model = Power(owner.rows, Drive(), lambda: True, lambda: False)
  holder: list[SettingsWindow] = []
  sections = [Section("General", lambda: None), Section("Power", lambda: power_panel(model, holder[0])),
              Section("Backups", lambda: None), Section("Storage & Data", lambda: None), Section("Firehose", lambda: None)]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(holder[0], ExampleDevice(), sections)}, initial=Tab.DEVICE)
  holder.append(window)
  window.show_event()
  window.top.select(2)
  for _ in range(3):
    frame(lambda: window.render(rl.Rectangle(0, 0, 2160, 1080)))
  save(f"{out}/devicepower.png")
