"""Display › Driving Screen › Text Size and Reduce Motion: the driving screen's sizes, and text that scrolls to fit."""
import pytest

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.onroad import scroll, size as Z


@pytest.fixture(autouse=True)
def standard(monkeypatch):
  """Standard text, and text measured as half its size per character: the tests run without fonts loaded."""
  from openpilot.selfdrive.ui.tandem import draw
  monkeypatch.setattr(draw, "text_width", lambda text, size, weight=None, tracking=0: len(text) * size * 0.5)
  Z.set_text(False, False)
  yield
  Z.set_text(False, False)


def test_larger_is_about_30_percent_on_everything_but_the_few_picked_sizes():
  assert Z.px(74) == T.px(74) and not Z.larger()
  Z.set_text(True)
  assert Z.larger() and Z.px(74) == round(74 * T.SCALE * 1.3) and Z.font_px(17) == round(17 * T.SCALE * 1.3)
  assert Z.pick(360, 405) == T.px(405)                       # the larger mock's own size, not 360 scaled
  Z.set_text(False)
  assert Z.pick(360, 405) == T.px(360)


def test_the_drive_screen_follows_both_settings(tandem_prefs):
  from openpilot.selfdrive.ui.tandem.settings.display import Display
  model = Display.__new__(Display)
  model.set_text_size(1)
  model.set_reduce_motion(True)
  Z.refresh(now=1e9)
  assert Z.larger() and Z.reduce_motion() and model.text_size == 1 and model.reduce_motion
  model.set_text_size(0)
  model.set_reduce_motion(False)
  Z.refresh(now=1e9 + 0.5)                                   # read at most once a second
  assert Z.larger()
  Z.refresh(now=1e9 + 1.0)
  assert not Z.larger() and not Z.reduce_motion()


def test_both_settings_are_off_by_default(tandem_prefs):
  from openpilot.selfdrive.ui.tandem.prefs import LARGER_TEXT, REDUCE_MOTION
  assert not LARGER_TEXT.get() and not REDUCE_MOTION.get()


def test_a_scrolling_line_rests_slides_rests_and_fades_back():
  shift, speed = 200.0, 40.0                                 # 5 s of sliding
  slide, loop = scroll.timing(shift, speed)
  assert slide == 5.0 and loop == scroll.REST_S + 5.0 + scroll.REST_S + scroll.FADE_S
  assert scroll.at(1.0, shift, speed) == scroll.Pass(0.0, 1.0)                       # resting at the start
  assert 0 < scroll.at(scroll.REST_S + 2.5, shift, speed).offset < shift              # sliding
  assert scroll.at(scroll.REST_S + 5.0 + 1.0, shift, speed) == scroll.Pass(shift, 1.0)   # resting at the end
  assert scroll.at(loop - 0.1, shift, speed).alpha < 0.5                             # fading out
  assert scroll.at(loop + 0.1, shift, speed) == scroll.Pass(0.0, 1.0)                # and back to the start


def test_only_text_that_doesnt_fit_scrolls_and_not_with_reduce_motion():
  scroller = scroll.Scroller(clock=lambda: 0.0)
  long_name = "Southeast Martin Luther King Jr Parkway"
  assert scroller.pass_seconds("Elm St", T.px(400), T.font_px(28), T.FONT_BOLD) == 0
  assert scroller.pass_seconds(long_name, T.px(200), T.font_px(28), T.FONT_BOLD) > 2 * scroll.REST_S
  Z.set_text(False, True)
  assert scroller.pass_seconds(long_name, T.px(200), T.font_px(28), T.FONT_BOLD) == 0


def _bar(now, street="Southeast Martin Luther King Jr Parkway"):
  from openpilot.selfdrive.ui.tandem.onroad.layers import BarState, OnroadBar
  state = BarState(engaged=True, street=street, navigating=True, arrive="4:52 PM", left="12 min · 8.4 mi")
  return OnroadBar(lambda: state, lambda: None, lambda d: None, lambda: None, lambda: None, clock=lambda: now[0]), state


def test_the_larger_navigating_bar_takes_turns_between_arrival_and_the_street():
  import pyray as rl
  from openpilot.selfdrive.ui.tandem.onroad import layers as L
  Z.set_text(True)
  now = [0.0]
  bar, state = _bar(now)
  body = rl.Rectangle(0, 0, T.px(470), T.px(92))
  assert bar._turns(body, state) == (1.0, 0.0)              # arrival first
  now[0] = L.ARRIVAL_S + 0.01
  arrival, street = bar._turns(body, state)
  assert street < 0.1 and arrival > 0.9                     # the street's turn begins, fading in
  now[0] += L.CROSSFADE_S
  assert bar._turns(body, state) == pytest.approx((0.0, 1.0))
  now[0] += L.STREET_S                                      # a long name keeps its turn until it has scrolled through
  assert bar._turns(body, state)[1] == 1.0
  now[0] += 60
  bar._turns(body, state)                                   # then back to arrival, fading in
  now[0] += L.CROSSFADE_S
  assert bar._turns(body, state) == pytest.approx((1.0, 0.0))


def test_reduce_motion_switches_turns_without_fading():
  import pyray as rl
  from openpilot.selfdrive.ui.tandem.onroad import layers as L
  Z.set_text(True, True)
  now = [0.0]
  bar, state = _bar(now, street="Elm St")
  body = rl.Rectangle(0, 0, T.px(470), T.px(92))
  bar._turns(body, state)
  now[0] = L.ARRIVAL_S + 0.01
  assert bar._turns(body, state) == (0.0, 1.0)


def test_sizes_grow_and_the_offer_card_ends_before_the_speed():
  from openpilot.selfdrive.ui.tandem.onroad import layers as L
  standard = (L.bar_height(), L.sign_tile_size(), L.street_size(), L.LimitCard.width())
  assert standard == (T.px(74), (T.px(82), T.px(98)), T.font_px(28), T.px(360))
  Z.set_text(True)
  assert L.bar_height() == Z.px(74) > standard[0] and L.street_size() > standard[2]
  assert L.LimitCard.width() == T.px(405)


def test_the_menu_sidebar_grows_only_while_driving():
  from openpilot.selfdrive.ui.tandem.sidebar import SidebarState, zoom
  Z.set_text(True)
  assert zoom(SidebarState(onroad=True)) == Z.LARGER and zoom(SidebarState(onroad=False)) == 1.0
