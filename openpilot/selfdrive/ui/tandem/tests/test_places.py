"""Where to?'s places (places.py) over StarPilot 7's real navigation owner in a temporary folder."""
from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from openpilot.starpilot.navigation.owner import NavigationOwner
from openpilot.selfdrive.ui.tandem.places import StarPilotPlaces
from openpilot.selfdrive.ui.tandem.routemap import NO_FIX, NOT_SET_UP, RoutePlan

PARK = {"name": "Laurelhurst Park", "address": "SE Cesar E Chavez Blvd, Portland", "latitude": 45.52, "longitude": -122.62}
OFFICE = {"name": "Office", "address": "200 Market St, Portland", "latitude": 45.51, "longitude": -122.68}


class Now:
  """Runs each search at once, as the worker thread would."""

  def submit(self, work: Any, *args: Any) -> Future:
    future: Future = Future()
    try:
      future.set_result(work(*args))
    except Exception as error:
      future.set_exception(error)
    return future


class Runtime:
  """StarPilot's navigation status, with nothing routing."""

  def snapshot(self) -> dict:
    return {}


def make_owner(tmp_path: Path) -> NavigationOwner:
  """StarPilot's owner in tmp_path, in imperial units (its IsMetric param needs the device's Params)."""
  real = NavigationOwner(tmp_path / "navigation", runtime_source=Runtime(), transient_root=tmp_path / "transient")
  real._is_metric = lambda: False   # type: ignore[method-assign]
  return real


@pytest.fixture
def owner(tmp_path: Path) -> NavigationOwner:
  real = make_owner(tmp_path)
  real.configure({"token": "pk.test"}, real.snapshot()["revision"], True)
  return real


def places(owner: NavigationOwner, allowed: bool = True) -> StarPilotPlaces:
  clock = [0.0]

  def tick() -> float:
    clock[0] += 2.0   # every read is fresh
    return clock[0]
  return StarPilotPlaces(lambda: owner, allowed=lambda: allowed, clock=tick, executor=Now)


def test_start_turns_navigation_on_and_sets_the_destination(owner: NavigationOwner) -> None:
  source = places(owner)
  assert not owner.snapshot()["enabled"] and source.can_search()
  source.pick(PARK)
  assert source.can_start() and source.start()
  snap = owner.snapshot()
  assert snap["enabled"] and snap["destination"]["name"] == "Laurelhurst Park" and source.draft() is None
  assert source.active()["name"] == "Laurelhurst Park" and [r["name"] for r in source.recents()] == ["Laurelhurst Park"]
  source.end_route()
  assert owner.snapshot()["destination"] is None


def test_home_and_work_are_labels_on_favorites(owner: NavigationOwner) -> None:
  source = places(owner)
  source.pick(OFFICE)
  source.toggle("work")
  assert source.saved_as() == (True, False, True)
  assert [(f["name"], f["is_home"], f["is_work"]) for f in source.favorites()] == [("Office", False, True)]
  source.toggle("home")
  assert source.saved_as() == (True, True, False)
  source.toggle("home")
  assert source.saved_as() == (True, False, False)   # still a favorite, no longer Home
  source.toggle("favorite")
  assert source.saved_as() == (False, False, False) and source.favorites() == []


def test_a_recents_star_saves_and_forgets_it(owner: NavigationOwner) -> None:
  source = places(owner)
  source.toggle_saved(PARK)
  assert source.is_favorite(PARK)
  source.toggle_saved(PARK)
  assert not source.is_favorite(PARK)


def test_nothing_changes_when_not_allowed(owner: NavigationOwner) -> None:
  source = places(owner, allowed=False)
  source.pick(PARK)
  assert not source.start() and owner.snapshot()["destination"] is None and source.draft() is not None


def test_search_shows_results_or_starpilots_reason(owner: NavigationOwner, monkeypatch: pytest.MonkeyPatch) -> None:
  source = places(owner)
  monkeypatch.setattr(owner, "search", lambda query: [dict(PARK, id="p")])
  source.search("park")
  source.tick()
  assert source.results() == [("Laurelhurst Park", "SE Cesar E Chavez Blvd, Portland")] and source.status() is None
  source.pick_result(0)
  assert source.draft()["name"] == "Laurelhurst Park"

  def refuse(query: str) -> list:
    raise ValueError("Mapbox's monthly search budget is used up")
  monkeypatch.setattr(owner, "search", refuse)
  source.search("park")
  source.tick()
  assert source.results() == [] and source.status() == ("Search unavailable", "Mapbox's monthly search budget is used up")


def test_without_a_key_there_is_no_search_or_route(tmp_path: Path) -> None:
  source = places(make_owner(tmp_path))
  source.pick(PARK)
  assert not source.can_search() and not source.can_start() and source.route() == (None, NOT_SET_UP)


def test_the_preview_route_comes_from_starpilots_engine(owner: NavigationOwner, monkeypatch: pytest.MonkeyPatch) -> None:
  source = places(owner)
  assert source._fetch_route(PARK) == NO_FIX
  monkeypatch.setattr(owner.position_store, "read", lambda: {"latitude": 45.5, "longitude": -122.6, "bearing": 90.0})
  asked: list[tuple] = []

  def fetch(engine: Any, token: str, origin: tuple, place: dict, bearing: Any, exclusions: tuple) -> Any:
    asked.append((token, origin, bearing))
    return SimpleNamespace(points=((-122.6, 45.5), (-122.62, 45.52)), total_distance=3000.0, total_duration=420.0)
  from openpilot.starpilot.navigation import route_engine
  monkeypatch.setattr(route_engine.MapboxRouteEngine, "fetch", fetch)
  plan = source._fetch_route(PARK)
  assert asked == [("pk.test", (-122.6, 45.5), 90.0)]
  assert plan == RoutePlan(((45.5, -122.6), (45.52, -122.62)), 3000.0, 420.0)


def test_offline_maps_only_starts_and_previews_without_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  from openpilot.starpilot.tandem.routing import config as C, navigation as N
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path / "state"))
  C.set_policy(offline_only=True)
  monkeypatch.setattr(N, "capability", lambda: {"status": "ready", "generation": "g"})
  monkeypatch.setattr(N, "language", lambda: "en")
  route = SimpleNamespace(points=((-122.6, 45.5), (-122.62, 45.52)), total_distance=3000.0, total_duration=420.0)
  monkeypatch.setattr(N.LocalRouteEngine, "fetch", lambda self, *args: route)
  owner = make_owner(tmp_path)
  monkeypatch.setattr(owner.position_store, "read", lambda: {"latitude": 45.5, "longitude": -122.6})
  source = places(owner)
  source.pick(PARK)
  assert source.can_start() and source._fetch_route(PARK) == RoutePlan(((45.5, -122.6), (45.52, -122.62)), 3000.0, 420.0)
  assert source.start() and owner.snapshot()["destination"]["name"] == "Laurelhurst Park"


def test_offline_maps_only_without_coverage_holds_start_and_says_why(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  from openpilot.starpilot.tandem.routing import config as C, navigation as N
  from openpilot.starpilot.navigation.owner import ValidationError
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path / "state"))
  C.set_policy(offline_only=True)
  monkeypatch.setattr(N, "capability", lambda: {"status": "ready", "generation": "g"})
  monkeypatch.setattr(N, "language", lambda: "en")

  def outside(*_: object) -> None:
    raise ValidationError("data_missing")
  monkeypatch.setattr(N.LocalRouteEngine, "fetch", outside)
  owner = make_owner(tmp_path)
  monkeypatch.setattr(owner.position_store, "read", lambda: {"latitude": 45.5, "longitude": -122.6})
  source = places(owner)
  assert source.maps_ready() and source._fetch_route(PARK) == "Download maps for this region"
  source.pick(PARK)
  source._routes.route = lambda place: (None, "Download maps for this region")   # type: ignore[method-assign]
  assert source.route_missing() and not source.can_start()
  C.set_policy(offline_only=False)
  assert not source.route_missing()
