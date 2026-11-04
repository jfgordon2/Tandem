import pyray as rl
from openpilot.selfdrive.ui.tandem import draw, tokens as T
from openpilot.selfdrive.ui.tandem.onroad.layers import (ArcState, BarState, HeadroomArc, HelpSteer, LimitCard, LimitOffer, OnroadBar,
                                                         StatusChip, WORKING, AT_LIMIT, draw_speed, draw_speed_limit, draw_turn_card,
                                                         sign_tile, dm_tile, draw_driver_monitor, TURN_BELOW_SIGN, TURN_CARD_TOP)
from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for

W, H = 2160, 1080


def road(rect):
  draw.fill(rect, rl.Color(18, 26, 36, 255))
  draw.fill(rl.Rectangle(rect.x, rect.y, rect.width, rect.height * 0.42), rl.Color(14, 20, 28, 255))
  cx = rect.x + rect.width / 2
  rl.draw_triangle(rl.Vector2(cx - 30, rect.y + rect.height * 0.42), rl.Vector2(cx - 340, rect.y + rect.height),
                   rl.Vector2(cx + 340, rect.y + rect.height), rl.Color(40, 80, 130, 200))
  rl.draw_triangle(rl.Vector2(cx - 30, rect.y + rect.height * 0.42), rl.Vector2(cx + 340, rect.y + rect.height),
                   rl.Vector2(cx + 30, rect.y + rect.height * 0.42), rl.Color(40, 80, 130, 200))
  for sx in (-1, 1):
    rl.draw_line_ex(rl.Vector2(cx + sx * 60, rect.y + rect.height * 0.42), rl.Vector2(cx + sx * 900, rect.y + rect.height), 6, rl.Color(200, 210, 220, 140))
  draw.stroke(rect, T.SUCCESS, T.px(18), T.px(6))


def scene(state, arc, chip, offer=None, help_=False, speed=62, limit="60", turn=None, signal=None, attentive=1.0):
  rect = rl.Rectangle(15, 15, W - 30, H - 30)
  bar = OnroadBar(lambda: state, lambda: None, lambda d: None, lambda: None, lambda: None, lambda: None)
  def render():
    road(rect)
    HeadroomArc(lambda: arc, help_steer=lambda: help_).render(rect)
    draw_speed(rect, speed, state.unit, left=signal == 'left', right=signal == 'right', now=0.5)
    sign = bool(limit) and offer is None
    card = LimitCard(lambda: offer, lambda: None, lambda: None)
    top = (card.box(rect).y + card.box(rect).height - rect.y + T.px(12)) if offer else TURN_BELOW_SIGN if sign else TURN_CARD_TOP
    if turn:
      draw_turn_card(rect, *turn, top)
    if sign:
      draw_speed_limit(sign_tile(rect), limit, False)
    draw_driver_monitor(dm_tile(rect), 1.0, attentive, True)
    if help_:   # a Warning alert: it takes the bar's place, as the view hides the bar, chips and card under alerts
      HelpSteer().render(rect)
      return
    StatusChip(lambda: chip if isinstance(chip, list) else ([(chip, 1.0)] if chip else [])).render(rect)
    card.render(rect)
    bar.render(rect)
  return render


def main(frame, save, out, tap, gui_app):
  shots = {
    "onroad_stack": scene(BarState(True, True, 63, "mph", "Market Street"), ArcState(0.3, 0.4, True),
                          [(c, a) for c, a in __import__("scene_stack").stacked()]),
    "memorychip": scene(BarState(True, True, 63, "mph", "Market Street"), ArcState(0.18, 0.2, True), __import__("scene_stack").low_memory()),
    "onroad_pauses": scene(BarState(True, True, 17, "mph", "Market Street"), ArcState(0.3, 0.4, True),
                           [(chip_for(x), 1.0) for x in (
                             Snapshot(lateral_paused=True, speed=8.0),
                             Snapshot(steering_held=True, speed=5.0, pause_lateral_ms=8.94, pause_lateral_speed=20),
                             Snapshot(steering_held=True, speed=5.0, pause_lateral_ms=8.94, pause_lateral_speed=20, signal_on=True,
                                      signal_direction="left", pause_on_signal=True),
                             Snapshot(steering_held=True, speed=12.0, pause_lateral_ms=8.94, pause_lateral_speed=20, pause_on_signal=True))], speed=17),
    "onroad_modes": scene(BarState(True, True, 58, "mph", "Market Street"), ArcState(0.2, 0.3, True),
                          [(chip_for(x), 1.0) for x in (
                            Snapshot(engaged=True, pulse_glide=True, gliding=True),
                            Snapshot(engaged=True, events={"laneChangeBlocked"}),
                            Snapshot(engaged=True, coasting=True),
                            Snapshot(engaged=True, speed_paused=True))], speed=58),
    "onroad_default": scene(BarState(True, True, 63, "mph", "Market Street"), ArcState(0.18, 0.2, True), chip_for(Snapshot(curve_control=True)),
                            signal="left"),
    "onroad_working": scene(BarState(True, True, 63, "mph", "Market Street"), ArcState(0.7, 0.92, True, WORKING),
                            chip_for(Snapshot(steering_held=True, speed=5.0, pause_lateral_ms=8.94, pause_lateral_speed=20)), attentive=0.0),
    "onroad_limit": scene(BarState(True, True, 48, "mph", "Hwy 101"), ArcState(0.2, 0.2, True), None,
                          LimitOffer(55, 58, "mph", "Map Data", 8), speed=45),
    "onroad_helpsteer": scene(BarState(True, True, 48, "mph", "Hwy 101"), ArcState(-0.95, -0.95, True, AT_LIMIT), None,
                              help_=True, speed=45),
    "onroad_nav": scene(BarState(False, True, 48, "mph", "SE Hawthorne Blvd", True, "4:52 PM", "12 min · 8.4 mi"), ArcState(0, 0, False),
                        chip_for(Snapshot(engaged=True, standstill=True)), speed=44, limit="45",
                        turn=("0.4 mi", "Turn right onto Market St", "turn", "right")),
    "onroad_nav_limit": scene(BarState(True, True, 48, "mph", "SE Hawthorne Blvd", True, "4:52 PM", "12 min · 8.4 mi"), ArcState(0.15, 0.2, True),
                              None, LimitOffer(55, 58, "mph", "Map Data", 18), speed=44, limit="45",
                              turn=("0.4 mi", "Turn right onto Market St", "turn", "right")),
    # The README's first image: a new-limit offer, a lane change and a weather heads-up, the compass and the weather now.
    "onroad_hero": scene(BarState(True, True, 48, "mph", "N Main St", heading="NE", weather=("rain", "52°")), ArcState(0.25, 0.3, True),
                         [(chip_for(Snapshot(engaged=True, lane_change="starting", lane_change_direction="left")), 1.0),
                          (chip_for(Snapshot(forecast=("Light rain in 12 min", "rain"))), 1.0)],
                         LimitOffer(55, 58, "mph", "Map Data", 18), speed=46, limit="45", signal="left"),
    "onroad_green": scene(BarState(True, True, 44, "mph", "SE Hawthorne Blvd"), ArcState(0, 0, False),
                          chip_for(Snapshot(engaged=True, standstill=True, events={"greenLight"})), speed=0, limit="45"),
  }
  for name, render in shots.items():
    for _ in range(3):
      frame(render)
    save(f"{out}/{name}.png")
