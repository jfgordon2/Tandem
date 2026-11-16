"""Render the release-matched Device widgets with sample device data."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from openpilot.common.qrcode import make_texture
from openpilot.selfdrive.ui.tandem.settings.device import Calibration, device_page
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.starpilot.ui.raylib import rl


class ExampleDevice:
  """An inert source for the nine release references."""

  def __init__(self) -> None:
    self.paired = False
    self.offroad = True
    self.engaged = False
    self.saved_calibration = Calibration.CALIBRATED
    self.code: rl.Texture | None = None

  def is_paired(self) -> bool:
    return self.paired

  def pairing_supported(self) -> bool:
    return True

  def provider_name(self) -> str:
    return "comma connect"

  def provider_web(self) -> str:
    return "https://connect.comma.ai"

  def is_offroad(self) -> bool:
    return self.offroad

  def can_recalibrate(self) -> bool:
    return not self.engaged

  def calibration(self) -> str:
    return self.saved_calibration

  def remote_access_label(self) -> str:
    return "Set Up"

  def ids(self) -> str:
    return "abc123 · serial"

  def imei(self) -> str:
    return "351234567890123"

  def pairing_qr(self) -> rl.Texture | None:
    return self.code

  def remote_access_link(self) -> str:
    return ""

  def remote_access_qr(self) -> rl.Texture | None:
    return None

  def show_regulatory(self) -> bool:
    return False

  def __getattr__(self, name: str) -> Callable[[], None]:
    return lambda: None


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Render the implemented Device presentation using the release fixture."""
  data = ExampleDevice()
  sections = [Section(label, lambda: None) for label in ("General", "Backups", "Storage & Data", "Report a Problem")]
  window = SettingsWindow({Tab.DEVICE: lambda: device_page(window, data, sections)}, lambda: None, initial=Tab.DEVICE)
  window.show_event()
  rect = rl.Rectangle(0, 0, 2160, 1080)

  def shot(name: str) -> None:
    for _ in range(10):
      frame(lambda: window.render(rect))
    save(f"{out}/{name}.png")

  shot("device-parked")
  panel = window.top.current
  for name, button in (("device-restart", panel._footer._buttons[0]), ("device-power-off", panel._footer._buttons[1]),
                       ("device-recalibrate", panel.items[2]._control)):
    button._click_callback()
    shot(name)
    window.dismiss()

  panel._scroll.set_offset(-220)
  shot("device-scrolled")
  panel._scroll.set_offset(0)
  data.saved_calibration = Calibration.CALIBRATING
  shot("device-calibrating")
  data.saved_calibration = Calibration.CALIBRATED
  data.paired = True
  shot("device-paired")
  data.offroad, data.engaged = False, True
  shot("device-engaged")
  data.paired, data.offroad, data.engaged = False, True, False
  sample_qr = Path(out) / "_sample-code.png"
  data.code = rl.load_texture(str(sample_qr)) if sample_qr.exists() else make_texture("https://connect.comma.ai/?pair=example-token")
  try:
    panel.items[0]._control._click_callback()
    shot("device-pairing")
    window.back()
    panel.items[1]._control._click_callback()
    shot("device-remote-access")
  finally:
    rl.unload_texture(data.code)
