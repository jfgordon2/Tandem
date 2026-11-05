"""Render widgets headlessly (under xvfb-run) and save PNGs. Usage: BIG=1 xvfb-run -a python3 snap.py <scene.py> <out_dir>"""
import os
import sys
import runpy

sys.path.insert(0, os.path.dirname(__file__))
import stubs
stubs.install()

import pyray as rl

W, H = 2160, 1080
capture = None


def open_window():
  global capture
  os.environ["SCALE"] = "1"   # captures always use device pixels; do not open an auto-scale query window
  rl.set_trace_log_level(rl.TraceLogLevel.LOG_ERROR)
  rl.set_config_flags(rl.ConfigFlags.FLAG_MSAA_4X_HINT)
  rl.init_window(W, H, "snap")
  if os.getenv("TANDEM_CAPTURE_TEXTURE") == "1":
    # The device's physical framebuffer is portrait and has display color transforms.
    # Capture the landscape drawing target before those panel transforms instead.
    capture = rl.load_render_texture(W, H)
  load_application()


def load_application():
  # On macOS, install the app's logging callback after Cocoa/GL have initialized.
  global gui_app, MouseEvent, MousePos
  from openpilot.system.ui.lib.application import gui_app, MouseEvent, MousePos
  gui_app._load_fonts()
  gui_app._patch_text_functions()
  from openpilot.selfdrive.ui.tandem.fonts import prepare_fallback
  prepare_fallback()


def frame(draw, events=()):
  gui_app._mouse_events = list(events)
  rl.begin_drawing()
  if capture is not None:
    rl.begin_texture_mode(capture)
  rl.clear_background(rl.BLACK)
  draw()
  if capture is not None:
    rl.end_texture_mode()
  rl.end_drawing()


def save(path):
  img = rl.load_image_from_screen() if capture is None else rl.load_image_from_texture(capture.texture)
  if capture is not None:
    rl.image_flip_vertical(img)
  if (img.width, img.height) != (W, H):
    rl.image_resize(img, W, H)
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
