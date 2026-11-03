"""The passive recorder in ready, recording and saved states, plus translated/pseudo layouts."""
import os
import sys
from dataclasses import replace

import pyray as rl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
from test_settings import _search_window
from test_can_recorder import FakeRecorder
from openpilot.selfdrive.ui.tandem import i18n
from openpilot.selfdrive.ui.tandem.settings.can_recorder import CanRecorderPage
from openpilot.selfdrive.ui.tandem.settings.window import Tab


def main(frame, save, out, tap, gui_app):
  win = _search_window()
  win.show_event()
  win.select_tab(Tab.DEVICE)
  win.top.select(5)
  recorder = FakeRecorder()
  page = CanRecorderPage(recorder, allowed=lambda: True, clock_ns=lambda: 13_034_000_000)
  win.push(page)
  rect = rl.Rectangle(0, 0, 2160, 1080)

  def shot(name):
    for _ in range(5):
      frame(lambda: win.render(rect))
    save(f"{out}/{name}.png")

  shot("canrecorder_ready")
  page.set_input(1)
  shot("canrecorder_obd_ready")
  recorder.state = replace(recorder.state, phase="recording", session="20261102T213000Z-a1b2c3", started_ns=1_000_000_000,
                           frames=21504, obd_frames=12150, input="obd", lock_markers=1, unlock_markers=1,
                           last_kind="unlock", last_marker_ns=11_418_000_000)
  shot("canrecorder")
  recorder.state = replace(recorder.state, phase="aborting")
  shot("canrecorder_aborting")
  recorder.state = replace(recorder.state, phase="saved", ended_ns=13_034_000_000)
  shot("canrecorder_saved")
  saved = recorder.state
  recorder.abort()
  shot("canrecorder_discarded")
  recorder.state = saved
  original = i18n._language
  try:
    codes = ("pseudo",) if os.environ.get("TANDEM_PSEUDO") == "1" else ("de", "es", "ja", "pseudo")
    for code in codes:
      i18n._language = lambda c=code: c
      shot(f"canrecorder_{code}")
  finally:
    i18n._language = original
  win.hide_event()
