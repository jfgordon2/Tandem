"""Render the release Backups panel and its existing confirmation dialogs."""
from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any
from unittest.mock import Mock

from openpilot.selfdrive.ui.tandem.settings.backup_owner import Backup, BackupStore
from openpilot.selfdrive.ui.tandem.settings.backups import backups_panel
from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tools.render.scene_device import ExampleDevice
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Capture the release sample list, empty list and the two confirmations."""
  store = Mock(spec=BackupStore)
  store.allowed = Mock(return_value=True)
  store.backups.return_value = (Backup("first", "Backup 2026-10-24 0910", "Oct 24, 2026 9:10 AM"),
                                Backup("second", "Before update", "Oct 2, 2026 6:00 PM"))
  sections = [Section("General", lambda: None), Section("Backups", lambda: backups_panel(store, window)),
              Section("Storage & Data", lambda: None), Section("RAM", lambda: None, dot=lambda: True),
              Section("Report a Problem", lambda: None)]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, ExampleDevice(), sections)}, initial=Tab.DEVICE)
  window.show_event()
  window.top.select(2)
  page = window.top.current
  bounds = rl.Rectangle(0, 0, 2160, 1080)

  def draw() -> None:
    """Draw a complete frame of Settings."""
    window.render(bounds)

  def wait_for_list() -> None:
    """Wait for the fake store's worker to update the release list."""
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
      frame(draw)
      if page._content._header_control.enabled:
        frame(draw)
        return
      time.sleep(.01)
    raise TimeoutError("Backups list did not settle")

  wait_for_list()
  save(f"{out}/stage4-backups.png")
  delete, restore = page._content.items[1]._control._buttons
  for button, name in ((restore, "restore"), (delete, "delete")):
    button._click_callback()
    window._overlay._shown_at = rl.get_time() - 1
    frame(draw)
    save(f"{out}/stage4-backups-{name}.png")
    window.dismiss()
  window.top.select(0)
  store.backups.return_value = ()
  window.top.select(2)
  wait_for_list()
  save(f"{out}/stage4-backups-empty.png")
