"""Capture the approved radio controls using the actual Connections panels."""
import os
import sys

import pyray as rl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
from test_settings import _search_window
from openpilot.selfdrive.ui.tandem.settings import connections
from openpilot.selfdrive.ui.tandem.settings.window import Tab
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth, FakeWifi
from openpilot.starpilot.tandem.radios import Radio


def main(frame, save, out, tap, gui_app):
  wifi, bluetooth = FakeWifi(), FakeBluetooth()
  window = _search_window()
  window.wifi = lambda: wifi
  window.bluetooth = lambda: bluetooth
  window.show_event()
  window.select_tab(Tab.CONNECTIONS)
  rect = rl.Rectangle(0, 0, 2160, 1080)
  try:
    for section, name in ((connections.WIFI, "wifi"), (connections.CELLULAR, "cellular"),
                          (connections.REMOTE, "remote"), (connections.AUDIO, "audio")):
      window.top.select(section)
      for enabled in (True, False):
        wifi.radios.set_enabled(Radio.WIFI, enabled if section == connections.WIFI else True)
        wifi.radios.set_enabled(Radio.CELLULAR, enabled if section == connections.CELLULAR else True)
        bluetooth.set_power(enabled if section in (connections.REMOTE, connections.AUDIO) else True)
        for _ in range(4):
          frame(lambda: window.render(rect))
        save(f"{out}/radio-{name}-{'on' if enabled else 'off'}.png")
  finally:
    window.hide_event()
