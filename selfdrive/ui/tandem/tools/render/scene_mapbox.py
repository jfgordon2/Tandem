import pyray as rl
from openpilot.selfdrive.ui.tandem import draw as D, tokens as T
from openpilot.selfdrive.ui.tandem.mapbox_help import mapbox_key_sheet


def main(frame, save, out, tap, gui_app):
  rect = rl.Rectangle(0, 0, 2160, 1080)
  sheet = mapbox_key_sheet(lambda: None)
  sheet.show_event()
  for _ in range(30):
    frame(lambda: (D.fill(rect, T.BG), D.fill(rl.Rectangle(38, 34, 2084, 220), T.SURFACE_2, T.RADIUS_PANEL), sheet.render(rect)))
  save(f"{out}/mapboxkey.png")
