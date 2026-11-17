"""Release's Software tab (design/softwaretab.html) in release's settings window, over a stand-in for StarPilot's software owner."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from openpilot.selfdrive.ui.tandem.settings.software import Software, SoftwarePage
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.selfdrive.ui.tandem.software import HomeSoftware, InstallPreference, InstallTarget, SoftwareState, SoftwareWatch, Stage
from openpilot.starpilot.ui.raylib import rl

DESCRIPTION = "7.0.0 / development / 1abbbc6 / Nov 16"


class StillWatch(SoftwareWatch):
  """A watch that keeps the state it's given: nothing is read or sent while rendering."""

  def poll(self) -> SoftwareState:
    return self.state


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  watch = StillWatch(Mock, lambda key: None, lambda: True, Mock())
  installs = InstallPreference(True, "0 3 * * *", "America/Chicago", "a" * 32)
  base = SoftwareState(stage=Stage.CURRENT, home=HomeSoftware(installed="7.0.0", current=True), branch="development",
                       downloads=True, installs=installs, can_check=True, can_configure=True)
  target = InstallTarget("development", "a" * 40, "b" * 40)
  states = {
    "softwaretab": base,
    "softwaretab-available": SoftwareState(**{**base.__dict__, "stage": Stage.AVAILABLE, "can_download": True}),
    "softwaretab-downloading": SoftwareState(**{**base.__dict__, "stage": Stage.DOWNLOADING, "percent": 42, "can_check": False}),
    "softwaretab-ready": SoftwareState(**{**base.__dict__, "stage": Stage.READY,
                                          "home": HomeSoftware(installed="7.0.0", version="7.0.1", target=target)}),
    "softwaretab-park": SoftwareState(**{**base.__dict__, "stage": Stage.PARK, "can_check": False, "can_configure": False}),
  }
  window = SettingsWindow({Tab.SOFTWARE: lambda: SoftwarePage(Software(watch, lambda key: DESCRIPTION if key == "UpdaterCurrentDescription" else None,
                                                                       lambda: None), window)},
                          initial=Tab.SOFTWARE)
  window.show_event()
  rect = rl.Rectangle(0, 0, 2160, 1080)
  try:
    for name, state in states.items():
      watch.state = state
      for _ in range(4):
        frame(lambda: window.render(rect))
      save(f"{out}/{name}.png")
  finally:
    watch.close()
