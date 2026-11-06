import sys
from dataclasses import dataclass, replace
from types import SimpleNamespace

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


@pytest.mark.parametrize("fields, expected", [
  ({"full_address": "410 N Ankeny Blvd, Ankeny, IA 50023", "address": "410 N Ankeny Blvd",
    "place_formatted": "Ankeny, IA 50023"}, "410 N Ankeny Blvd, Ankeny, IA 50023"),
  ({"address": "2510 SW State St", "place_formatted": "Ankeny, IA 50023"}, "2510 SW State St, Ankeny, IA 50023"),
  ({"full_address": " 410 N Ankeny Blvd, Ankeny, IA 50023 "}, "410 N Ankeny Blvd, Ankeny, IA 50023"),
  ({"address": " 410 N Ankeny Blvd ", "place_formatted": " Ankeny, IA 50023 "}, "410 N Ankeny Blvd, Ankeny, IA 50023"),
  ({"address": "410 N Ankeny Blvd"}, "410 N Ankeny Blvd"),
  ({"place_formatted": "Ankeny, IA 50023"}, "Ankeny, IA 50023"),
  ({}, ""),
])
@pytest.mark.parametrize("retrieved", [False, True])
def test_search_address_includes_street_without_repeating_locality(fields, expected, retrieved):
  payload = {"properties": fields} if retrieved else fields
  assert D.search_address(payload) == expected


def test_tandem_search_client_preserves_results_and_distinguishes_branches(monkeypatch):
  monkeypatch.setenv("TANDEM_ROUTING", "0")  # this test isolates upstream search normalization
  @dataclass(frozen=True)
  class Result:
    name: str
    subtitle: str
    mapbox_id: str
    latitude: float = 41.7
    longitude: float = -93.6

  normalized = []

  class Client:
    @classmethod
    def _normalize_result(cls, payload):
      if not payload.get("name"):
        return None
      result = Result(payload["name"], payload.get("place_formatted", ""), payload["mapbox_id"])
      normalized.append(result)
      return result

  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.layouts.settings.starpilot.navigation", SimpleNamespace(
    MapboxSearchClient=Client, StarPilotNavigationLayout=lambda: SimpleNamespace(_search_client=Client())))
  places = D.UpstreamPlaces()
  client = places._nav._search_client
  assert isinstance(client, Client)
  payloads = [
    {"name": "Hy-Vee", "mapbox_id": "north", "place_formatted": "Ankeny, IA 50023",
     "full_address": "410 N Ankeny Blvd, Ankeny, IA 50023"},
    {"name": "Hy-Vee", "mapbox_id": "south", "place_formatted": "Ankeny, IA 50023", "address": "2510 SW State St"},
  ]
  places._nav._search_results = [client._normalize_result(p) for p in payloads]
  assert places.results() == [
    ("Hy-Vee", "410 N Ankeny Blvd, Ankeny, IA 50023"),
    ("Hy-Vee", "2510 SW State St, Ankeny, IA 50023"),
  ]
  for original, result in zip(normalized, places._nav._search_results, strict=True):
    assert replace(result, subtitle=original.subtitle) == original   # IDs and coordinates still come from upstream
  assert client._normalize_result({}) is None
  result = client._normalize_result({"name": "410 N Ankeny Blvd", "mapbox_id": "address",
                                     "full_address": "410 N Ankeny Blvd, Ankeny, IA 50023"})
  assert result.subtitle == "Ankeny, IA 50023"   # address searches already put the street on the first line


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


def test_typing_shows_two_rows_with_the_same_keyboard_height_as_settings(monkeypatch):
  from openpilot.selfdrive.ui.tandem.settings.search import SettingsSearch

  screen, places, _ = _screen()
  screen._go(D.SEARCH)
  places.found = [(f"Place {i}", f"{i} Main St") for i in range(6)]
  keys = []
  monkeypatch.setattr(screen, "_render_field", lambda _: None)
  monkeypatch.setattr(screen._keys, "render_keys", keys.append)
  monkeypatch.setattr(D.ResultCard, "_render", lambda *args: None)
  rect = K.rl.Rectangle(20, 30, 2160, 1080)
  screen._render_search(rect)
  cards = [card.rect for card in screen._cards]
  assert len(cards) == 4 and cards[0].y == cards[1].y and cards[2].y == cards[3].y
  assert cards[0].x == cards[2].x < cards[1].x == cards[3].x
  assert cards[2].y > cards[0].y + cards[0].height
  assert cards[2].y + cards[2].height < keys[0].y

  settings = SettingsSearch(lambda: True, lambda _: None, lambda: None)
  monkeypatch.setattr(settings, "_render_field", lambda _: None)
  monkeypatch.setattr(settings._keys, "render_keys", keys.append)
  monkeypatch.setattr(D.draw, "fill", lambda *args: None)
  monkeypatch.setattr(D.draw, "text", lambda *args: None)
  settings._render(rect)
  assert (keys[0].y, keys[0].height) == (keys[1].y, keys[1].height)

  screen._cards[3]._click_callback()
  screen._update_state()
  assert screen._view == D.PREVIEW and D.place_name(places.draft()) == "Place 3"


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4, 6])
def test_suggestions_hide_empty_cells_and_search_keeps_all_results(count):
  screen, places, _ = _screen()
  screen._go(D.SEARCH)
  places.found = [(f"Place {i}", f"{i} Main St") for i in range(count)]
  assert [card.is_visible for card in screen._cards] == [i < count for i in range(4)]
  screen._keys.set_text("place")
  screen._searched = "place"
  screen._keys._all_keys[K.ENTER]._click_callback()
  assert screen._view == D.RESULTS and len(places.results()) == count


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
