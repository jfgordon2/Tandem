import numpy as np
import pyray as rl
import scene_onroad as O
from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.onroad import extras as X
from openpilot.selfdrive.ui.tandem.onroad.layers import BarState, OnroadBar, dm_tile, draw_driver_monitor, draw_speed


def ribbon(left_top, right_top, left_bottom, right_bottom, n=12):
  ys = np.linspace(0, 1, n)
  L = [(left_bottom[0] + (left_top[0] - left_bottom[0]) * t, left_bottom[1] + (left_top[1] - left_bottom[1]) * t) for t in ys]
  R = [(right_bottom[0] + (right_top[0] - right_bottom[0]) * t, right_bottom[1] + (right_top[1] - right_bottom[1]) * t) for t in ys]
  return np.array(L + R[::-1], dtype=np.float32)


def main(frame, save, out, tap, gui_app):
  rect = rl.Rectangle(15, 15, 2160 - 30, 1080 - 30)
  cx, horizon = rect.x + rect.width / 2, rect.y + rect.height * 0.42
  bottom = rect.y + rect.height
  path = ribbon((cx - 30, horizon + 160), (cx + 30, horizon + 160), (cx - 340, bottom), (cx + 340, bottom))
  outer = ribbon((cx - 40, horizon + 160), (cx + 40, horizon + 160), (cx - 380, bottom), (cx + 380, bottom))
  left_lane = ribbon((cx - 90, horizon), (cx - 30, horizon), (cx - 1400, bottom), (cx - 340, bottom))
  right_lane = ribbon((cx + 30, horizon), (cx + 90, horizon), (cx + 340, bottom), (cx + 1400, bottom))
  state = BarState(True, True, 63, "mph", "Market Street", heading="NE", weather=("cloud", "34°"))
  bar = OnroadBar(lambda: state, lambda: None, lambda d: None, lambda: None, lambda: None)
  marker = rl.load_render_texture(22, 22)
  rl.begin_texture_mode(marker)
  rl.clear_background(rl.Color(0, 0, 0, 0))
  X.draw_radar_marker()
  rl.end_texture_mode()

  def render():
    O.road(rect)
    X.draw_lanes(rect, [(left_lane, "lane"), (right_lane, "blind_spot")])
    X.draw_path_edges(rect, outer, path)
    X.draw_stopping_point(X.path_end(path), "148 ft")
    for x, y in ((cx - 120, horizon + 60), (cx + 160, horizon + 40), (cx + 380, horizon + 140)):
      rl.draw_texture_v(marker.texture, rl.Vector2(x - 11, y - 11), rl.WHITE)
    draw_speed(rect, 38, "mph")
    tile = dm_tile(rect)
    draw_driver_monitor(tile, 1.0, 1.0, True)
    y = X.draw_pedals(tile, (1.0, 0.25))
    X.draw_model_chip(tile.x + tile.width, y, "active", 1.0)
    bar.render(rect)
    border = rl.Rectangle(rect.x - 6, rect.y - 6, rect.width + 12, rect.height + 12)
    X.draw_border_halves(rl.Rectangle(0, 0, 2160, 1080), border, 0.06, 12, (T.ACCENT, X.BLIND_SPOT_BORDER))
  for _ in range(4):
    frame(render)
  save(f"{out}/onroad_extras.png")
