"""Render the release Device › Storage & Data preview using release sample data."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.storage import StoragePanel
from openpilot.selfdrive.ui.tandem.settings.storage_owner import StorageOwner, StorageSample
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tools.render.scene_device import ExampleDevice
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Capture the list, its scrolled rows, and the release deletion dialogs."""
  owner = Mock(spec=StorageOwner)
  owner.poll.return_value = None
  owner.record.side_effect = lambda key: key == "RecordFront"
  owner.record_allowed.return_value = True
  owner.allowed.return_value = True
  owner.busy = False
  owner.uploads = 1
  owner.uploads_allowed.return_value = True
  owner.sample = StorageSample({"Total": 64e9, "Free": 30e9, "Drives": 21e9, "Maps": 4.2e9, "Models": 1.1e9}, ("old-model",), map_generation="a" * 64)
  sections = [Section("General", lambda: None), Section("Backups", lambda: None),
              Section("Storage & Data", lambda: StoragePanel(owner, window)), Section("RAM", lambda: None, dot=lambda: True),
              Section("Report a Problem", lambda: None)]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, ExampleDevice(), sections)}, initial=Tab.DEVICE)
  window.show_event()
  window.top.select(3)
  panel = window.top.current

  def draw() -> None:
    """Draw a complete frame of Settings."""
    window.render(rl.Rectangle(0, 0, 2160, 1080))

  for _ in range(3):
    frame(draw)
  save(f"{out}/stage4-storage.png")
  for index, name in ((1, "delete-drives"), (2, "delete-maps"), (3, "remove-models")):
    panel.items[index]._control._click_callback()
    window._overlay._shown_at = rl.get_time() - 1
    frame(draw)
    save(f"{out}/stage4-storage-{name}.png")
    window.dismiss()
  panel._scroll.set_offset(-T.px(340))
  for _ in range(3):
    frame(draw)
  save(f"{out}/stage4-storage-scrolled.png")
