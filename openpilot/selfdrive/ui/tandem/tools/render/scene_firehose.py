"""Device › Firehose (design/firehose.html, firehose-inactive.html): active on Wi-Fi, and inactive scrolled to the questions."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.settings.device import device_page
from openpilot.selfdrive.ui.tandem.settings.firehose import firehose_panel
from openpilot.selfdrive.ui.tandem.settings.pages import Section
from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
from openpilot.starpilot.ui.raylib import rl
from scene_device import ExampleDevice


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  bounds = rl.Rectangle(0, 0, 2160, 1080)
  for name, on, scrolled in (("firehose", True, False), ("firehose-inactive", False, True)):
    panel = firehose_panel(lambda on=on: on)
    sections = [Section(label, lambda: None) for label in ("General", "Backups", "Storage & Data")]
    sections += [Section("Firehose", lambda panel=panel: panel), Section("Report a Problem", lambda: None)]
    holder: list[SettingsWindow] = []
    window = SettingsWindow({Tab.DEVICE: lambda sections=sections, holder=holder: device_page(holder[0], ExampleDevice(), sections)},
                            lambda: None, initial=Tab.DEVICE)
    holder.append(window)
    window.show_event()
    window.top.select(4)
    for _ in range(2):
      frame(lambda window=window: window.render(bounds))
    if scrolled:   # the inactive card first, then down to the questions, as the mock shows them together
      save(f"{out}/{name}-top.png")
      panel._scroll.set_offset(-T.px(260))   # down to the questions, as the mock shows
      for _ in range(2):
        frame(lambda window=window: window.render(bounds))
    save(f"{out}/{name}.png")
