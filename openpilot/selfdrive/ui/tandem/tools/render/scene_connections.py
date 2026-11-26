"""Render each Connections section over the test stand-ins, each under its mock's name."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openpilot.selfdrive.ui.tandem.settings import connections
from openpilot.selfdrive.ui.tandem.tests.fakes import connections_window
from openpilot.starpilot.ui.raylib import rl


def main(frame: Callable, save: Callable, out: str, tap: Callable, gui_app: Any) -> None:
  """Each section, with sample networks and a finished test."""
  window: Any = connections_window()
  window.show_event()
  bounds = rl.Rectangle(0, 0, 2160, 1080)
  for index, mock in ((connections.WIFI, "connections"), (connections.CELLULAR, "connectionscellular"),
                      (connections.REMOTE, "connectionsremote"), (connections.DEVICES, "connectionsaudio"),
                      (connections.ANDROID_AUTO, "connections-androidauto"), (connections.TEST, "connectionstest")):
    window.top.select(index)
    frame(lambda: window.render(bounds))
    frame(lambda: window.render(bounds))
    save(f"{out}/{mock}.png")
  # Set up on your phone (design/androidauto-qr.html), fully open
  from openpilot.selfdrive.ui.tandem.settings.android_auto import AndroidAuto, StarPortStatus, setup_sheet
  model = AndroidAuto(lambda: StarPortStatus(supported=True), lambda: "https://galaxy.firestar.link/example/#/starport")
  model.link = "https://galaxy.firestar.link/example/#/starport"
  window.top.select(connections.ANDROID_AUTO)
  sheet = setup_sheet(model, window)
  window.present(sheet)
  sheet._shown_at = None
  frame(lambda: window.render(bounds))
  frame(lambda: window.render(bounds))
  save(f"{out}/androidauto-qr.png")
