"""Render widgets headlessly (under xvfb-run) and save PNGs. Usage: BIG=1 xvfb-run -a python3 snap.py <scene.py> <out_dir>"""
import os
import sys
import runpy

sys.path.insert(0, os.path.dirname(__file__))
import stubs
stubs.install()

import pyray as rl
from openpilot.system.ui.lib.application import gui_app, MouseEvent, MousePos

W, H = 2160, 1080


def open_window():
  rl.set_trace_log_level(rl.TraceLogLevel.LOG_ERROR)
  rl.set_config_flags(rl.ConfigFlags.FLAG_MSAA_4X_HINT)
  rl.init_window(W, H, "snap")
  gui_app._load_fonts()
  gui_app._patch_text_functions()
  from openpilot.selfdrive.ui.tandem.fonts import prepare_fallback
  prepare_fallback()


def frame(draw, events=()):
  gui_app._mouse_events = list(events)
  rl.begin_drawing()
  rl.clear_background(rl.BLACK)
  draw()
  rl.end_drawing()


def save(path):
  img = rl.load_image_from_screen()
  rl.export_image(img, path)
  rl.unload_image(img)


def tap(x, y, slot=0):
  pos = MousePos(x, y)
  t = rl.get_time()
  return [MouseEvent(pos, slot, True, False, True, t)], [MouseEvent(pos, slot, False, True, False, t)]


if __name__ == "__main__":
  open_window()
  scene = runpy.run_path(sys.argv[1])
  scene["main"](frame=frame, save=save, out=sys.argv[2], tap=tap, gui_app=gui_app)
