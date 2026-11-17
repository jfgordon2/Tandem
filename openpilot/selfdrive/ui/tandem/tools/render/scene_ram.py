"""Render the release Device › RAM panel in the current Settings window."""
from __future__ import annotations

from collections.abc import Callable
import datetime
import json
from pathlib import Path
from typing import Any

from openpilot.selfdrive.ui.tandem.ram import RamLog
from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.ram import ram_section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tools.render.scene_device import ExampleDevice
from openpilot.starpilot.ui.raylib import rl


def sample_ram(out: str) -> RamLog:
  """Use the three sample drives and process values from release's RAM mock."""
  mb = 2**20
  today = datetime.datetime.now().replace(second=0, microsecond=0)
  top = [["starpilot_process", 352 * mb], ["modeld", 250 * mb], ["dmonitoringmodeld", 205 * mb], ["ui", 170 * mb],
         ["speed_limit_vision", 160 * mb]]
  grew = {"starpilot_process": 270 * mb, "modeld": 2 * mb, "dmonitoringmodeld": 1 * mb, "ui": 4 * mb, "speed_limit_vision": 40 * mb}
  drives = [(today.replace(hour=16, minute=46), 95), (today.replace(hour=16, minute=25), 93), (today.replace(hour=15, minute=31), 92)]
  path = Path(out) / "_ram.json"
  path.write_text(json.dumps({"unseen": True, "drives": [{"when": when.timestamp(), "percent": percent, "top": top,
                                                         "rest": 2300 * mb, "drive": i, "grew": grew}
                                                        for i, (when, percent) in enumerate(drives)]}))
  return RamLog(path)


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Draw an unread snapshot and then the panel after the driver opens it."""
  log = sample_ram(out)
  sections = [Section("More device settings", lambda: None), Section("Firehose", lambda: None),
              ram_section(log, lambda: 38), Section("Developer", lambda: None)]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, ExampleDevice(), sections)}, initial=Tab.DEVICE)
  window.show_event()
  def render() -> None:
    window.render(rl.Rectangle(0, 0, 2160, 1080))

  for _ in range(8):
    frame(render)
  save(f"{out}/stage4-ram-unread.png")
  window.top.select(3)
  for _ in range(8):
    frame(render)
  save(f"{out}/stage4-ram.png")

  window.top.current._content._scroll.set_offset(-70)
  for _ in range(8):
    frame(render)
  save(f"{out}/stage4-ram-scrolled.png")
