"""Approved Cellular/APN states and pseudo-language layout, without a real modem."""
from dataclasses import replace
import os
import sys

import pyray as rl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
from test_settings import _search_window
from openpilot.selfdrive.ui.tandem import draw, i18n
from openpilot.selfdrive.ui.tandem.settings.window import Tab
from openpilot.starpilot.tandem.cellular import Observation


def main(frame, save, out, tap, gui_app):
  old_language, old_drawn = i18n._language, draw.DRAWN
  try:
    for language in ("en", "pseudo"):
      i18n._language = lambda code=language: code
      draw.DRAWN = set()
      window = _search_window()
      window.store.write({"GsmApn": "carrier.apn", "GsmMetered": True})
      window.show_event()
      window.select_tab(Tab.CONNECTIONS)
      window.top.select(1)
      model = window.top.current.model
      source = model.cellular
      connected = source.value
      states = {
        "connected": connected,
        "no-signal": Observation(sim=True, modem=7, registration=2, quality=0),
        "connecting": replace(connected, connected=False, connecting=True),
        "not-connected": Observation(sim=True, modem=8, registration=1),
        "no-sim": Observation(sim=False),
        "wifi": Observation(sim=True, modem=8, registration=1, wifi=True),
        "checking": None,
      }
      rect = rl.Rectangle(0, 0, 2160, 1080)
      def shot(name, win=window, bounds=rect, code=language):
        for _ in range(4):
          frame(lambda: win.render(bounds))
        save(f"{out}/{name}{'_pseudo' if code == 'pseudo' else ''}.png")
      for state in ("connected", "no-signal"):
        source.value = states[state]
        shot("cellular-status-" + state)
      window.top.current._bottom._click_callback()
      for state, value in states.items():
        source.value = value
        shot("cellular-apn-" + state)
      window.hide_event()
      if language == "pseudo":
        from pathlib import Path
        missed = sorted(text for text in draw.DRAWN if any(c.isalpha() for c in text) and "[" not in text and
                        text not in ("Home Wi-Fi", "weedle-c488", "carrier.apn", "LTE"))
        Path(out, "cellular_missed.txt").write_text("\n".join(missed) + "\n")
  finally:
    if old_drawn is not None:
      old_drawn.update(draw.DRAWN or ())
    i18n._language, draw.DRAWN = old_language, old_drawn
