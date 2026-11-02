import pytest

from openpilot.selfdrive.ui.tandem import keyboard as K
from openpilot.selfdrive.ui.tandem import destinations as D
from openpilot.selfdrive.ui.tandem.routemap import NOT_SET_UP
from openpilot.selfdrive.ui.tandem.tests.fakes import FakePlaces


@pytest.fixture(autouse=True)
def no_window(monkeypatch):
  monkeypatch.setattr(K.upstream, "Label", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream, "Button", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream.gui_app, "texture", lambda *a, **k: None)


def _screen(**kw):
  places, closed = FakePlaces(**kw), []
  return D.DestinationsScreen(places, lambda: closed.append(True)), places, closed


def _type(screen, text):
  for ch in text:
    screen._keys._all_keys[ch]._click_callback()


def test_typing_searches_after_a_pause_and_search_lists_everything(monkeypatch):
  screen, places, _ = _screen()
  screen._search_pill._click_callback()
  assert screen._view == D.SEARCH
  clock = [100.0]
  monkeypatch.setattr(D.time, "monotonic", lambda: clock[0])
  _type(screen, "har")
  screen._update_state()
  assert places.queries == []                       # still typing
  clock[0] += D.SEARCH_PAUSE + 0.1
  screen._update_state()
  assert places.queries == ["har"]
  screen._keys._all_keys[K.ENTER]._click_callback()
  assert screen._view == D.RESULTS and places.queries == ["har"]   # already searched, so no repeat


def test_picking_a_result_previews_and_start_closes():
  screen, places, closed = _screen()
  screen._go(D.SEARCH)
  places.search("hardware")
  screen._pick_result(0)
  screen._update_state()
  assert screen._view == D.PREVIEW and D.place_name(places.draft()) == "Hardware Store"
  screen._start()
  assert closed and D.place_name(places.active()) == "Hardware Store"


def test_start_waits_for_routing():
  screen, places, closed = _screen(routing=False)
  screen._pick(places.recents()[0])
  screen._start()
  assert not closed and places.active() is None


def test_home_tile_opens_home_or_sets_it():
  screen, places, _ = _screen()
  screen._tiles[0]._click_callback()
  assert screen._view == D.PREVIEW and D.place_name(places.draft()) == "Home"
  screen._back()
  places.favs = [f for f in places.favs if not f.get("is_home")]
  screen._tiles[0]._click_callback()
  assert screen._view == D.SEARCH and screen._intent == "home"
  places.search("elm")
  screen._pick_result(0)
  screen._update_state()
  assert places.saved_as()[1]                       # the picked place became Home


def test_back_walks_out_and_closes():
  screen, places, closed = _screen()
  screen._pick(places.recents()[0])
  screen._back()
  assert screen._view == D.LIST and places.draft() is None
  screen._back()
  assert closed


def test_preview_star_saves_and_start_follows_routing():
  screen, places, closed = _screen()
  screen._pick(places.recents()[0])
  assert places.route()[0] is not None
  screen._star._click_callback()
  assert places.saved_as()[0]
  screen._start_button._click_callback()
  assert closed and places.active() is not None
  screen, places, _ = _screen(routing=False)
  screen._pick(places.recents()[0])
  assert not screen._start_button.enabled and places.route() == (None, NOT_SET_UP)


def test_mapbox_keys_each_do_their_part_and_the_steps_point_to_app_keys():
  from openpilot.selfdrive.ui.tandem.mapbox_help import STEPS, keys, status

  def saved(**values):
    return lambda key: values.get(key, "")
  assert keys(saved()) == (False, False) and keys(saved(MapboxPublicKey=b"  ")) == (False, False)
  assert status(saved(MapboxPublicKey="pk.a", MapboxSecretKey="sk.b")) == ("Added", True)
  assert status(saved(MapboxPublicKey="pk.a"))[0].startswith("Public key only")
  assert status(saved(MapboxSecretKey="sk.b"))[0].startswith("Secret key only")
  assert status(saved()) == ("Not added · needed for place search and routes", False)
  text = " ".join(line for _, line in STEPS)
  assert "Navigation & Maps › App Keys" in text and "DOWNLOADS:READ" in text and "pk." in text
