"""Render Device › General and its language picker against the release Device rail."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any

from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.general import GeneralPanel, open_language
from openpilot.selfdrive.ui.tandem.settings.general_owner import General
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.tools.render.scene_device import ExampleDevice
from openpilot.starpilot.galaxy.localization_settings import LocalizationSettingsOwner
from openpilot.starpilot.ui.display_owner import DisplayOwner
from openpilot.starpilot.ui.display_preferences import SCREEN_OFF
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Use isolated settings and release's sample of a Device rail with a RAM snapshot."""
  with tempfile.TemporaryDirectory() as root:
    path = Path(root)
    (path / SCREEN_OFF).write_bytes(b"1")
    params = SimpleNamespace(get_param_path=lambda key: str(path / key), get_bool=lambda _: False)

    def parked() -> bool:
      """Use a parked, local device without connecting to any hardware."""
      return True

    model = General(LocalizationSettingsOwner(params, parked, parked), DisplayOwner(params, parked, gpu_capable=False),
                    parked, lambda: None)
    sections = [Section("General", lambda: GeneralPanel(model, window)),
                Section("Backups", lambda: None), Section("Storage & Data", lambda: None),
                Section("RAM", lambda: None, dot=lambda: True), Section("Report a Problem", lambda: None)]
    window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, ExampleDevice(), sections)}, initial=Tab.DEVICE)
    window.show_event()
    window.top.select(1)
    bounds = rl.Rectangle(0, 0, 2160, 1080)

    def draw() -> None:
      """Draw a frame of the complete Settings window."""
      window.render(bounds)

    frame(draw)
    save(f"{out}/stage4-general.png")
    open_language(model, window)
    # Render after the release sheet's entry animation has finished in the headless scene.
    window._overlay._shown_at = None
    frame(draw)
    save(f"{out}/stage4-general-language.png")
