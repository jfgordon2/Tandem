from openpilot.starpilot.ui.raylib import rl
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
  """Every non-docstring string in this package."""
  import ast
  from pathlib import Path
  root = Path(__file__).resolve().parents[2]
  found = []
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
  assert "controls.py" in scanned, "string scan found nothing; check the paths"
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
  from openpilot.starpilot.ui.raylib import rl
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
  from openpilot.starpilot.ui.raylib import rl
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
