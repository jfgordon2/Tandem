"""The drive screen's bar: Where to? beside MAX without a route (design/onroadwhereto.html), none while navigating."""
import pyray as rl

from openpilot.selfdrive.ui.tandem.onroad.layers import BarState, OnroadBar

RECT = rl.Rectangle(0, 0, 2160, 1080)


def _bar(state, where_to=lambda: None):
  return OnroadBar(lambda: state, lambda: None, lambda d: None, lambda: None, lambda: None, where_to)


def test_where_to_sits_beside_max_without_a_route():
  r = _bar(BarState(street="N Main St")).rects(RECT)
  assert list(r) == ["menu", "speed", "where", "center", "engage"]
  assert r["where"].x > r["speed"].x and r["center"].x > r["where"].x
  hits = [(h.x, h.y, h.width, h.height) for h in _bar(BarState()).hit_rects(RECT)]
  assert (r["where"].x, r["where"].y, r["where"].width, r["where"].height) in hits   # taps there are the bar's, not the road's


def test_no_where_to_while_navigating_or_without_a_way_to_open_it():
  assert "where" not in _bar(BarState(navigating=True)).rects(RECT)
  assert "where" not in _bar(BarState(), where_to=None).rects(RECT)
  wide, narrow = _bar(BarState(navigating=True)).rects(RECT)["center"], _bar(BarState()).rects(RECT)["center"]
  assert wide.width > narrow.width                       # navigating keeps the street pill's full width


def test_the_button_opens_where_to():
  opened = []
  bar = _bar(BarState(), lambda: opened.append(True))
  bar._where._click_callback()
  assert opened == [True]
