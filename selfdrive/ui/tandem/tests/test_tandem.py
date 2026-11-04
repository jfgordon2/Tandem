import pyray as rl
import pytest

from openpilot.system.ui.lib.application import MousePos
from openpilot.system.ui.widgets import DialogResult
from openpilot.selfdrive.ui.tandem import (BottomNav, Component, Dialog, Segmented, Sidebar, SidebarItem, Slider, Stepper, Switch, resolve,
                                               tokens as T)
from openpilot.selfdrive.ui.tandem.layout import FILL, Align, Fill, column, grid, grow, inset, place, row


def _r(rect: rl.Rectangle) -> tuple[float, float, float, float]:
  return round(rect.x, 3), round(rect.y, 3), round(rect.width, 3), round(rect.height, 3)


# ── layout ──

def test_row_gives_fixed_sizes_first_and_splits_the_rest_by_weight():
  parts = row(rl.Rectangle(0, 0, 1000, 50), [100, FILL, Fill(3), 200], gap=10)
  assert [_r(p) for p in parts] == [(0, 0, 100, 50), (110, 0, 167.5, 50), (287.5, 0, 502.5, 50), (800, 0, 200, 50)]


def test_column_never_goes_negative_when_fixed_sizes_overflow():
  top, rest = column(rl.Rectangle(0, 0, 100, 50), [80, FILL], gap=10)
  assert _r(top) == (0, 0, 100, 80)
  assert rest.height == 0


def test_grid_fills_left_to_right_then_down():
  cells = grid(rl.Rectangle(0, 0, 290, 210), columns=3, rows=2, gap=10)
  assert [_r(c)[:2] for c in cells] == [(0, 0), (100, 0), (200, 0), (0, 110), (100, 110), (200, 110)]
  assert all(_r(c)[2:] == (90, 100) for c in cells)


def test_inset_place_and_grow():
  assert _r(inset(rl.Rectangle(0, 0, 100, 100), 10, left=20)) == (20, 10, 70, 80)
  assert _r(place(rl.Rectangle(0, 0, 100, 100), 20, 10, Align.END, Align.CENTER)) == (80, 45, 20, 10)
  assert _r(grow(rl.Rectangle(50, 50, 40, 40), 112, 20)) == (14, 50, 112, 40)


def test_tokens_convert_mock_pixels_to_device_pixels():
  assert T.px(1125) == 2160
  assert T.ROW_HEIGHT == T.px(70)   # the Theme & Startup mock's rows
  # Font sizes convert like layout: the text patch's FONT_SCALE already maps draw size to CSS em size.
  assert T.font_px(30) == T.px(30)
  assert T.MIN_TOUCH >= 112


# ── values ──

def test_resolve_calls_getters_but_not_raylib_structs():
  color = rl.Color(1, 2, 3, 4)
  assert resolve(color) is color
  assert resolve(lambda: 5) == 5
  assert resolve("x") == "x"


# ── controls ──

def test_stepper_steps_and_clamps():
  value = {"v": 9.0}
  stepper = Stepper(lambda: value["v"], lambda v: value.__setitem__("v", v), minimum=-10, maximum=10, step=1)
  assert stepper.stepped(1) == 10
  value["v"] = 10
  assert stepper.stepped(1) == 10
  assert stepper.stepped(-1) == 9
  value["v"] = -10
  assert stepper.stepped(-1) == -10


def test_slider_snaps_to_step_and_respects_floor():
  slider = Slider(50, lambda v: None, minimum=0, maximum=100, step=5, floor=25)
  slider.set_rect(rl.Rectangle(0, 0, 1028, 66))
  assert slider.value_at(slider.x_for(62)) == 60
  assert slider.value_at(slider.x_for(10)) == 25
  assert slider.value_at(-100) == 25
  assert slider.value_at(5000) == 100


def test_switch_reports_the_flipped_value():
  changes = []
  switch = Switch(True, changes.append)
  switch._handle_mouse_release(MousePos(0, 0))
  assert changes == [False]


def test_segmented_tap_picks_the_segment_under_the_finger():
  changes = []
  seg = Segmented(["A", "B", "C"], selected=0, on_change=changes.append, equal=True)
  seg.set_rect(rl.Rectangle(0, 0, 308, 40))
  rects = seg.segment_rects()
  seg._handle_mouse_release(MousePos(rects[2].x + 5, 20))
  seg._handle_mouse_release(MousePos(rects[0].x + 5, 20))   # already selected: no change
  assert changes == [2]


def test_small_controls_accept_touches_across_min_touch():
  switch = Switch(False)
  switch.set_rect(rl.Rectangle(500, 500, 60, 40))
  hit = switch._hit_rect
  assert hit.width >= T.MIN_TOUCH and hit.height >= T.MIN_TOUCH


def test_dialog_reports_its_result():
  results = []
  dialog = Dialog("Delete?", "Gone for good.", "Delete", results.append)
  dialog._confirm._click_callback()
  dialog._cancel._click_callback()
  assert results == [DialogResult.CONFIRM, DialogResult.CANCEL]
  assert dialog.result == DialogResult.CANCEL


# ── chrome ──

def test_sidebar_selects_only_a_different_visible_item():
  opened = []
  sidebar = Sidebar("Driving", [SidebarItem("A", lambda: opened.append("A")), SidebarItem("Hidden", visible=False),
                                SidebarItem("C", lambda: opened.append("C"))], selected=0)
  sidebar.set_rect(rl.Rectangle(0, 0, 300, 600))
  rects = dict(sidebar.item_rects())
  assert set(rects) == {0, 2}
  for index in (0, 2):
    pos = MousePos(rects[index].x + 10, rects[index].y + 10)
    sidebar._handle_mouse_press(pos)
    sidebar._handle_mouse_release(pos)
  assert opened == ["C"]


def test_bottom_nav_selects_the_tab_that_was_pressed_and_released():
  picked = []
  nav = BottomNav(["Driving", "Device", "Network"], selected=0, on_select=picked.append)
  nav.set_rect(rl.Rectangle(0, 0, 2160, T.NAV_HEIGHT))
  tabs = nav.tab_rects()
  inside = MousePos(tabs[2].x + 10, tabs[2].y + 10)
  nav._handle_mouse_press(inside)
  nav._handle_mouse_release(inside)
  nav._handle_mouse_press(MousePos(tabs[1].x + 10, tabs[1].y + 10))
  nav._handle_mouse_release(inside)                       # dragged to another tab: ignored
  assert picked == [2]


@pytest.mark.parametrize("cls", [BottomNav, Sidebar])
def test_containers_do_not_grow_their_touch_area(cls):
  assert issubclass(cls, Component) and cls.grow_touch_target is False


# ── fonts ──

def _figtree_codepoints() -> set[int]:
  import re
  from pathlib import Path
  fnt = Path(__file__).resolve().parents[3] / "assets/fonts/Figtree-Medium.fnt"
  return {int(code) for code in re.findall(r"^char id=(\d+)", fnt.read_text(), re.MULTILINE)}


def _ui_strings() -> list[tuple[str, str]]:
  """Translated strings in StarPilot's settings panels, and every non-docstring string in this package."""
  import ast
  from pathlib import Path
  root = Path(__file__).resolve().parents[2]
  found = []
  for path in (root / "layouts/settings/starpilot").glob("*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
      if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "tr_noop") and node.args \
         and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        found.append((path.name, node.args[0].value))
  for path in (root / "tandem").glob("*.py"):
    if path.name == "arabic.py":   # character tables for shaping, drawn with the Noto fallback, not UI text
      continue
    tree = ast.parse(path.read_text())
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    found += [(path.name, n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
  return found


def test_figtree_atlas_can_draw_every_ui_string():
  """The atlases are pre-baked; a missing glyph renders as '?' on the device."""
  glyphs = _figtree_codepoints()
  strings = _ui_strings()
  scanned = {name for name, _ in strings}
  assert {"controls.py", "lateral.py"} <= scanned, "string scan found nothing; check the paths"
  missing = {(name, ch) for name, value in strings for ch in value if ord(ch) > 127 and ch.isprintable() and ord(ch) not in glyphs}
  assert not missing, sorted(missing)


def test_slider_merges_marks_at_the_same_value():
  from openpilot.selfdrive.ui.tandem.controls import Slider
  slider = Slider(100, lambda v: None, 0, 100, marks=[(80, "Quiet"), (100, "Normal"), (100, "Loud")])
  assert slider.merged_marks() == [(80, "Quiet"), (100, "Normal · Loud")]


def test_scroll_glow_marks_the_edges_with_more_content(monkeypatch):
  from openpilot.selfdrive.ui.tandem import draw
  glows = []
  monkeypatch.setattr(draw, "gradient_v", lambda r, top, bottom: glows.append("top" if top.a > bottom.a else "bottom"))
  monkeypatch.setattr(draw, "fill", lambda *args, **kwargs: None)
  view = rl.Rectangle(0, 0, 400, 300)

  def edges(offset, content):
    glows.clear()
    draw.scroll_glow(view, offset, content)
    return glows[:]

  assert edges(0, 600) == ["bottom"]            # at the top, more below
  assert edges(-150, 600) == ["top", "bottom"]  # in the middle
  assert edges(-300, 600) == ["top"]            # at the end
  assert edges(0, 300) == []                    # everything fits


def test_scroll_glow_spans_the_pane_and_follows_rounded_corners():
  from openpilot.selfdrive.ui.tandem import draw
  assert draw._corner_inset(20, 25) == 0.0                      # past the curve: the full width
  assert draw._corner_inset(20, 0) == 20                        # at the very edge, the curve starts a radius in
  assert 0 < draw._corner_inset(20, 5) < draw._corner_inset(20, 1) < 20


def test_paragraph_max_lines_ends_the_last_line_in_an_ellipsis(monkeypatch):
  import pyray as rl
  from openpilot.selfdrive.ui.tandem import draw
  drawn = []
  monkeypatch.setattr(draw, "paragraph_lines", lambda value, size, weight, width: ["one two", "three four", "five six"])
  monkeypatch.setattr(draw, "_fit", lambda text, size, weight, width, tracking=0: text)   # paragraph fits the already-translated line
  monkeypatch.setattr(draw.rl, "draw_text_ex", lambda font, line, *a: drawn.append(line))
  monkeypatch.setattr(draw, "font", lambda weight: None)
  monkeypatch.setattr(draw, "_face", lambda value, weight: None)   # no fonts loaded in tests
  draw.paragraph(rl.Rectangle(0, 0, 100, 100), "x", 20, rl.WHITE, max_lines=2)
  assert drawn == ["one two", "three four five six" + draw.ELLIPSIS]


def _sheet_drag(points, on_dismiss):
  import pyray as rl
  from openpilot.system.ui.lib.application import MouseEvent, MousePos
  from openpilot.selfdrive.ui.tandem.overlays import Sheet
  from openpilot.selfdrive.ui.tandem.rows import Text
  sheet = Sheet("What's new", Text("notes"), on_dismiss=on_dismiss)
  sheet._sheet_rect = rl.Rectangle(0, 400, 2160, 680)
  sheet._grab_rects = [rl.Rectangle(0, 400, 2160, 60)]
  for i, (y, t) in enumerate(points):
    last = i == len(points) - 1
    sheet._handle_mouse_event(MouseEvent(MousePos(1000, y), 0, i == 0, last, not last, t))
  sheet._handle_mouse_release(MousePos(1000, points[-1][0]))
  return sheet


def test_sheet_closes_when_its_handle_is_dragged_far_enough_or_flicked():
  closed = []
  _sheet_drag([(420, 0.0), (500, 0.5), (650, 1.0), (650, 1.1)], lambda: closed.append("far"))         # 230 px > a quarter
  _sheet_drag([(420, 0.0), (440, 0.1), (520, 0.15), (520, 0.16)], lambda: closed.append("flick"))     # short but fast
  assert closed == ["far", "flick"]


def test_sheet_springs_back_from_a_short_slow_drag_and_ignores_drags_off_the_handle():
  closed = []
  sheet = _sheet_drag([(420, 0.0), (470, 1.0), (500, 2.0), (500, 2.1)], lambda: closed.append(True))
  assert not closed and sheet._snap is not None and sheet._drag == 0
  _sheet_drag([(700, 0.0), (900, 0.5), (1000, 1.0), (1000, 1.1)], lambda: closed.append(True))      # starts in the body
  assert not closed


def test_traffic_chip_only_while_braking_and_ready_only_when_the_car_waits():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
  braking = Snapshot(engaged=True, slowing_for_lead=True, speed=12.0, accel=-1.2)
  assert chip_for(braking).label == "Slowing for traffic"
  assert chip_for(Snapshot(engaged=True, slowing_for_lead=True, speed=12.0, accel=0.1)) is None      # just following
  stopped = Snapshot(engaged=True, slowing_for_lead=True, standstill=True, speed=0.0, accel=-0.4)
  assert chip_for(stopped) is None                                   # stopped behind a car that will resume on its own
  stopped.waiting_for_resume = True
  assert chip_for(stopped).label == "Ready · tap resume"


def test_stop_chips_say_stopped_once_the_car_is_stopped():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
  assert chip_for(Snapshot(red_light=True, speed=8.0)).label == "Stopping ahead"   # the model's stop: light or sign
  assert chip_for(Snapshot(red_light=True, standstill=True)).label == "Stopped"
  assert chip_for(Snapshot(stop_sign=True, standstill=True)).label == "Stopped for stop sign"


def test_steer_saturated_is_the_alert_help_steer_replaces():
  from openpilot.selfdrive.ui.tandem.onroad.alerts import replaced_by_headroom
  assert replaced_by_headroom("steerSaturated/warning")
  assert not replaced_by_headroom("promptDriverDistracted/warning") and not replaced_by_headroom("")


def test_light_is_green_outranks_stopped_at_a_stop():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
  s = Snapshot(red_light=True, standstill=True, events={"greenLight"})
  assert chip_for(s).label == "Light is green"
  s.events = set()
  assert chip_for(s).label == "Stopped"


def test_every_steering_limit_alert_is_replaced_by_help_steer():
  from types import SimpleNamespace
  from openpilot.selfdrive.ui.tandem.onroad.alerts import replaced_by_headroom, steer_limit_alert
  for name in ("steerSaturated/warning", "goatSteerSaturated/warning", "firefoxSteerSaturated/warning", "thisIsFineSteerSaturated/warning"):
    assert replaced_by_headroom(name)
  assert not replaced_by_headroom("promptDriverDistracted/warning")

  class SM(dict):
    valid = {"selfdriveState": True, "starpilotSelfdriveState": True}
  sm = SM(selfdriveState=SimpleNamespace(alertType=""), starpilotSelfdriveState=SimpleNamespace(alertType="goatSteerSaturated/warning"))
  assert steer_limit_alert(sm)
  sm["starpilotSelfdriveState"] = SimpleNamespace(alertType="greenLight/permanent")
  assert not steer_limit_alert(sm)


def test_chip_stack_newest_nearest_the_bar_each_with_its_own_hold():
  from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, Snapshot
  stack = ChipStack()
  keys = lambda shown: [c.key for c, _ in shown]  # noqa: E731
  assert keys(stack.update(Snapshot(curve_control=True), 0.0, False)) == ["curve"]
  shown = stack.update(Snapshot(curve_control=True, weather="Rain", weather_gap=True), 0.5, False)
  assert keys(shown) == ["weather", "curve"]                    # the newer one sits nearest the bar
  shown = stack.update(Snapshot(weather="Rain", weather_gap=True), 1.0, False)    # the curve ended at 0.5: still held
  assert keys(shown) == ["weather", "curve"] and shown[1][1] == 1.0
  shown = stack.update(Snapshot(weather="Rain", weather_gap=True), 2.6, False)    # past its hold: fading
  assert keys(shown) == ["weather", "curve"] and 0.0 < shown[1][1] < 1.0
  assert keys(stack.update(Snapshot(weather="Rain", weather_gap=True), 3.0, False)) == ["weather"]   # gone
  assert stack.update(Snapshot(weather="Rain", weather_gap=True), 3.1, True) == []                     # hidden under an alert


def test_chip_stack_keeps_the_four_highest_priority():
  from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, Snapshot
  stack = ChipStack()
  busy = Snapshot(lateral_paused=True, curve_control=True, limit_changed=True, speed_limit=45, weather="Rain", weather_gap=True,
                  always_on_lateral=True)
  shown = [c.key for c, _ in stack.update(busy, 0.0, False)]
  assert len(shown) == 4 and "pause_button" in shown and "steering_only" not in shown


def test_low_memory_chip_is_red_in_arrival_order_and_lowest_priority():
  from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, ChipTone, Snapshot, chips_for
  low = dict(events={"lowMemory"}, memory_percent=91)
  chip = chips_for(Snapshot(**low))[0]
  assert (chip.key, chip.label, chip.tone, chip.icon) == ("low_memory", "Low on RAM · 91% used", ChipTone.ALERT, "memory")
  assert chips_for(Snapshot(memory_percent=91)) == []                     # StarPilot decides when memory is low
  stack = ChipStack()
  keys = lambda shown: [c.key for c, _ in shown]  # noqa: E731
  assert keys(stack.update(Snapshot(**low), 0.0, False)) == ["low_memory"]
  assert keys(stack.update(Snapshot(curve_control=True, **low), 0.5, False)) == ["curve", "low_memory"]   # newest nearest the bar
  busy = Snapshot(lateral_paused=True, curve_control=True, limit_changed=True, speed_limit=45, weather="Rain", weather_gap=True, **low)
  assert chips_for(busy)[-1].key == "low_memory"
  assert "low_memory" not in keys(ChipStack().update(busy, 0.0, False))  # the first to give way


def test_steering_pause_chip_names_the_real_reason():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
  setting = dict(pause_lateral_ms=8.94, pause_lateral_speed=20)          # StarPilot's Pause steering below 20 mph
  assert chip_for(Snapshot(lateral_paused=True, speed=25.0, **setting)).label == "Steering paused"        # a button, not speed
  assert chip_for(Snapshot(steering_held=True, speed=5.0, **setting)).label == "Steering paused · under 20 mph"
  assert chip_for(Snapshot(steering_held=True, speed=5.0, signal_on=True, pause_on_signal=True, **setting)).label == \
    "Steering paused for signal"
  # With Pause on signal, speed alone doesn't pause: a hold with the signal off is StarPilot's after-turn delay, at any speed
  assert chip_for(Snapshot(steering_held=True, speed=5.0, pause_on_signal=True, **setting)).label == "Steering paused after turn"
  assert chip_for(Snapshot(steering_held=True, speed=12.0, pause_on_signal=True, **setting)).label == "Steering paused after turn"
  assert chip_for(Snapshot(steering_held=True, speed=12.0, **setting)).label == "Steering paused"
  assert chip_for(Snapshot(steering_held=True, standstill=True, **setting)) is None                   # stopped: nothing to say
  assert chip_for(Snapshot(speed=2.0, **setting)) is None              # the planner isn't holding steering: no chip


def test_matching_limit_follows_an_accepted_change_until_reached():
  from openpilot.selfdrive.ui.tandem.onroad.status import LimitWatch
  w = LimitWatch()
  assert not w.update(20.0, 20.0, True, False, 0.0, 20.0, 0.0)        # the first limit seen isn't a change
  assert not w.update(20.0, 20.0, True, True, 0.0, 20.0, 1.0)         # a new limit is still being asked about: the card says it
  assert not w.update(20.0, 20.0, True, False, 0.0, 20.0, 1.5)        # declined: the limit never changed
  assert w.update(15.0, 15.0, True, False, 0.0, 20.0, 2.0)            # accepted 15: slowing to it
  assert not w.update(15.0, 15.0, True, False, 3.0, 19.0, 2.5)        # the driver overrode the speed
  assert w.update(15.0, 15.0, True, False, 0.0, 18.0, 3.0)
  assert not w.update(15.0, 15.0, True, False, 0.0, 15.2, 4.0)        # reached
  assert not w.update(15.0, 15.0, True, False, 0.0, 18.0, 5.0)        # and stays done
  assert w.update(25.0, 25.0, True, False, 0.0, 15.0, 6.0)            # a raise under the set speed: speeding up to it
  assert not w.update(30.0, 30.0, False, False, 0.0, 15.0, 7.0)       # above the set speed: the limit isn't holding the car
  assert not w.update(30.0, 30.0, True, False, 0.0, 15.0, 30.0)       # too long ago


def test_wheel_button_mode_chips():
  from openpilot.selfdrive.ui.tandem.onroad.status import ChipTone, Snapshot, chip_for, chips_for
  assert chip_for(Snapshot(engaged=True, speed_paused=True)).label == "Speed control paused"
  assert chip_for(Snapshot(engaged=True, speed_paused=True)).tone == ChipTone.PAUSED
  assert chip_for(Snapshot(engaged=True, coasting=True)).label == "Coasting"
  assert chip_for(Snapshot(engaged=True, pulse_glide=True)).label == "Pulse & glide"
  assert chip_for(Snapshot(engaged=True, pulse_glide=True, gliding=True)).label == "Pulse & glide · gliding"
  assert chip_for(Snapshot(speed_paused=True, coasting=True, pulse_glide=True)) is None              # not engaged: nothing applies
  # Paused speed control outranks the modes it switches off, and sits with the other pauses
  both = Snapshot(engaged=True, speed_paused=True, coasting=True, pulse_glide=True, lateral_paused=True)
  assert [c.key for c in chips_for(both)] == ["pause_button", "speed_paused"]
  from openpilot.selfdrive.ui.tandem import draw
  for name in ("gauge_pause", "pulse_glide", "coast"):
    assert (draw.ICON_DIR / f"{name}.png").is_file()


def test_lane_change_blocked_follows_the_blindspot_banner_it_replaces():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chip_for
  assert chip_for(Snapshot(events={"laneChangeBlocked"})).label == "Lane change blocked"
  assert chip_for(Snapshot(events={"laneChangeBlockedLoud"})).label == "Lane change blocked"   # also without steering
  assert chip_for(Snapshot(lane_change="pre", blindspot=True)).label == "Lane change blocked"


def test_help_steer_is_a_bottom_warning_card_with_the_arc_above_it():
  import pyray as rl
  from openpilot.selfdrive.ui.tandem.onroad import alerts
  from openpilot.selfdrive.ui.tandem.onroad.layers import BAR_HEIGHT, BAR_MARGIN, HELP_STEER, HeadroomArc, help_steer_box
  road = rl.Rectangle(0, 0, 2130, 1050)
  card = help_steer_box(road)
  same = alerts.box(road, alerts.WARNING, *HELP_STEER)                               # the same box as StarPilot's warnings
  assert (card.x, card.y, card.width, card.height) == (same.x, same.y, same.width, same.height)
  assert abs(card.y + card.height - (road.y + road.height - alerts.MARGIN)) < 0.01      # along the bottom
  assert card.y <= road.y + road.height - BAR_MARGIN - BAR_HEIGHT                     # covering the bar's row
  assert HeadroomArc.ABOVE_CARD > 0                                                   # the arc's ends sit above it



def test_release_notes_lead_with_a_tandem_entry():
  """The updater shows RELEASES.md's first block (up to the first blank line) as What's new; it must be ours and whole."""
  from pathlib import Path
  from openpilot.common.markdown import parse_markdown
  from openpilot.selfdrive.ui.tandem.settings.software_tab import notes_text
  text = (Path(__file__).resolve().parents[4] / "RELEASES.md").read_text()
  first, rest = text.split("\n\n", 1)
  lines = first.splitlines()
  assert lines[0].startswith("Tandem ") and lines[1].startswith("===")      # not openpilot's or StarPilot's notes
  assert len(lines) > 3 and all(line.lstrip().startswith("* ") for line in lines[2:])   # a heading, then bullets
  assert not rest.lstrip().startswith("* ")                                  # no bullets cut off by a blank line
  shown = notes_text(parse_markdown(first))
  assert shown.splitlines()[0] == lines[0] and shown.count("• ") == len(lines) - 2


def test_home_software_card_opens_software_or_the_notes():
  from openpilot.selfdrive.ui.tandem.home import HomeContent, HomeState
  opened = []
  state = HomeState(version="0.11.2")
  home = HomeContent(lambda: state, lambda: None, lambda: None, lambda: opened.append("notes"), lambda: opened.append("software"))
  home._update._click_callback()
  state = HomeState(update_ready=True)
  home._update._click_callback()
  assert opened == ["software", "notes"]


def test_screens_moves_the_settings_window_to_a_tab(monkeypatch):
  from openpilot.selfdrive.ui.tandem import screens
  moved = []
  monkeypatch.setattr(screens, "_settings", [type("W", (), {"open_at": lambda self, tab: moved.append(tab)})()])
  screens.show_settings_tab(3)
  assert moved == [3]


def test_lead_bar_takes_the_chevrons_place_and_size():
  from openpilot.selfdrive.ui.tandem.onroad import extras
  sz = 50.0
  chevron = [(500 + sz * 1.25, 300 + sz), (500, 300), (500 - sz * 1.25, 300 + sz)]   # upstream's: tip at the car's ground point
  rect = extras.lead_bar_rect(chevron)
  assert abs(rect.x + rect.width / 2 - 500) < 1e-6 and rect.y > 300 and abs(rect.width - sz * 2.5) < 1e-6
  far = extras.lead_bar_rect([(500 + 20, 300 + 16), (500, 300), (500 - 20, 300 + 16)])
  assert far.width < rect.width                                                    # smaller with distance
  assert extras.lead_bar_rect([]) is None
  fills = []
  import openpilot.selfdrive.ui.tandem.draw as draw
  original = draw.fill
  draw.fill = lambda r, c, radius=0: fills.append((r.width, c.a))
  try:
    extras.draw_lead_bar(rect, extras.LEAD_INK)
    assert len(fills) == 2 and fills[0][0] > fills[1][0]                           # the dark outline, then the bar
    fills.clear()
    extras.draw_lead_bar(rect, extras.LEAD_INK, extras.LEAD_FAINT, outline=False)
    assert len(fills) == 1 and fills[0][1] < 255
  finally:
    draw.fill = original


def test_lead_bar_grows_in_for_a_new_or_cut_in_car():
  from openpilot.selfdrive.ui.tandem.onroad.extras import LEAD_SETTLE, LeadSettle
  s = LeadSettle()
  assert s.update(True, 40.0, 0.0) == 0.0
  assert 0.0 < s.update(True, 40.0, LEAD_SETTLE / 2) < 1.0
  assert s.update(True, 39.0, LEAD_SETTLE) == 1.0
  assert s.update(True, 20.0, LEAD_SETTLE + 1.0) == 0.0          # a car cut in, much nearer: grows in again
  assert s.update(False, 0.0, 5.0) == 0.0 and s.update(True, 30.0, 5.0) == 0.0


def test_standard_and_thin_paths_are_essentials_blue():
  from openpilot.selfdrive.ui.lib.starpilot_theme import get_param_color
  from openpilot.selfdrive.ui.tandem.onroad.extras import PATH_COLOR
  from openpilot.selfdrive.ui.tandem.settings.display import PATH_STYLES
  for name, _, values in PATH_STYLES:
    assert values["PathColor"] == PATH_COLOR, name
  color = get_param_color(type("P", (), {"get": lambda self, k, encoding=None: PATH_COLOR})(), "PathColor")
  assert (color.r, color.g, color.b, color.a) == (0x5A, 0xAA, 0xF8, 0x80)
