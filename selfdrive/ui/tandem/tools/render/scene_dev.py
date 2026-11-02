import pyray as rl
import scene_onroad as O
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.onroad.developer import STRIP_H, WIDTH, DevData, Lead, draw_lead_tag, draw_panel, draw_strip
from openpilot.selfdrive.ui.tandem.onroad.lead import lead_anchor
from scene_lead import car, chevron
from openpilot.selfdrive.ui.tandem.onroad.layers import (DEV_ARC, ArcState, BarState, BAR_HEIGHT, BAR_MARGIN, HeadroomArc, OnroadBar,
                                                         dm_tile, draw_driver_monitor, draw_speed, draw_speed_limit, sign_tile)


def main(frame, save, out, tap, gui_app):
  rect = rl.Rectangle(15, 15, 2160 - WIDTH - 30, 1050)
  state = BarState(True, True, 63, "mph", "SE Hawthorne Blvd")
  bar = OnroadBar(lambda: state, lambda: None, lambda d: None, lambda: None, lambda: None, lambda: None)
  lead = Lead("38 m", "1.4 s", "−2 mph", True, "radar")
  data = DevData(lead, 0.38, "61°C", 0.22, 0.52, "3.1 GB", "20", "idle", "map", "3.6 / 3.5 m", "+0.42", "+0.38", "0.6", "0.9 m/s²", "0.18 s")

  def render():
    draw.fill(rl.Rectangle(0, 0, 2160, 1080), T.BG)
    O.road(rect)
    HeadroomArc(lambda: ArcState(0.2, 0.2, True), lambda: DEV_ARC).render(rect)
    draw_speed(rect, 62, "mph")
    draw_speed_limit(sign_tile(rect), "60", False, "MAP · +3")
    draw_driver_monitor(dm_tile(rect), 1.0, 1.0, True)
    cx = rect.x + rect.width / 2
    car(cx, 560, 120)
    anchor = lead_anchor(chevron(cx, 560, 38))
    draw_lead_tag(anchor.x, anchor.y, lead, anchored=True, bounds=rect)
    lift = STRIP_H + T.px(6)
    draw_strip(rl.Rectangle(rect.x, rect.y + rect.height - BAR_MARGIN - BAR_HEIGHT - lift, rect.width, STRIP_H), data)
    bar.render(rect)
    draw_panel(rl.Rectangle(2160 - WIDTH, 0, WIDTH, 1080), data)
  for _ in range(4):
    frame(render)
  save(f"{out}/onroaddev.png")
  import dataclasses
  data = dataclasses.replace(data, strip=("accel", "want", "steer", "delay"), steer="−4°", show_gpu=False, show_lanes=False)
  for _ in range(4):
    frame(render)
  save(f"{out}/onroaddev_four.png")
