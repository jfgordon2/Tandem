"""The Cellular page and its real hotspot-name keyboard, including translated and longer pseudo text."""
import os
import sys

import pyray as rl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tests"))
from test_settings import _search_window
from openpilot.selfdrive.ui.tandem import draw, i18n
from openpilot.selfdrive.ui.tandem.settings.window import Tab


def main(frame, save, out, tap, gui_app):
  original_language = i18n._language
  original_push = gui_app.push_widget
  keyboards = []
  gui_app.push_widget = keyboards.append
  try:
    for code in ("en", "de", "es", "ja", "pseudo"):
      i18n._language = lambda c=code: c
      draw.DRAWN = set()
      win = _search_window()
      win.store.write({"GsmMetered": True})
      win.show_event()
      win.select_tab(Tab.CONNECTIONS)
      win.top.select(1)
      rect = rl.Rectangle(0, 0, 2160, 1080)
      for _ in range(4):
        frame(lambda w=win, r=rect: w.render(r))
      save(f"{out}/connectionscellular_{code}.png")
      if code == "en":
        save(f"{out}/connectionscellular.png")
      win.top.current.items[1]._control._click_callback()
      kb = keyboards.pop()
      for _ in range(4):
        frame(lambda k=kb, r=rect: k.render(r))
      save(f"{out}/hotspotname_{code}.png")
      if code == "pseudo":
        missed = sorted(t for t in draw.DRAWN if any(c.isalpha() for c in t) and "[" not in t and t != "weedle-c488")
        with open(f"{out}/hotspot_missed.txt", "w", encoding="utf-8") as f:
          f.write("\n".join(missed) + "\n")
      win.hide_event()
  finally:
    gui_app.push_widget = original_push
    i18n._language = original_language
