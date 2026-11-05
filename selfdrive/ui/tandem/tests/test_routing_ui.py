import sys
import threading
from types import SimpleNamespace

from openpilot.selfdrive.ui.tandem import destinations as D, routemap as M
from openpilot.starpilot.tandem.routing import bundles, config as C


def settle(fetcher):
  for _ in range(200):
    if not fetcher._busy:
      return
    threading.Event().wait(.005)
  raise AssertionError("route worker did not complete")


def test_preview_rejects_late_a_after_a_b_a_and_expires():
  gate = threading.Event()
  asked = []
  clock = [100.0]
  plan = M.RoutePlan(((41.5, -93.6), (41.6, -93.6)), 1000, 60)
  def fetch(place):
    asked.append(place["name"])
    if len(asked) == 1:
      gate.wait(2)
      return M.NO_ROUTE
    return plan
  context = ["first-graph"]
  fetcher = M.RouteFetcher(fetch, clock=lambda: clock[0], identity=lambda place: (place["name"], context[0]), max_age=30)
  fetcher.route({"name": "A"})
  fetcher.route({"name": "B"})
  fetcher.route({"name": "A"})
  settle(fetcher)
  gate.set()
  threading.Event().wait(.03)
  assert fetcher.route({"name": "A"}) == (plan, "")
  context[0] = "new-graph"
  assert fetcher.route({"name": "A"}) == (None, M.FINDING)
  settle(fetcher)
  clock[0] += 31
  assert fetcher.route({"name": "A"}) == (None, M.FINDING)
  settle(fetcher)


def test_local_controller_accepts_keyless_saved_place_but_start_waits_for_preview(monkeypatch):
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  class Client:
    @classmethod
    def _normalize_result(cls, payload):
      return None
  class Controller:
    def __init__(self):
      self._draft_destination = self._selected_favorite = self._active_destination = None
      self._favorites = []
    def _favorite_for_destination(self, place):
      return None
    def _select_destination(self, place, favorite=None):
      self._draft_destination = dict(place)
    def _public_mapbox_key(self):
      return ""
    def _start_navigation(self):
      assert self._routing_available()
      self._active_destination, self._draft_destination = self._draft_destination, None
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.layouts.settings.starpilot.navigation",
                      SimpleNamespace(MapboxSearchClient=Client, StarPilotNavigationLayout=Controller))
  monkeypatch.setattr(bundles, "capability", lambda: {"status": "ready", "generation": "graph"})
  places = D.UpstreamPlaces()
  places.pick({"name": "Home", "latitude": 41.5, "longitude": -93.6})
  assert not places.can_search()
  places._routes = SimpleNamespace(route=lambda _: (None, M.FINDING))
  assert not places.can_start() and not places.start()
  plan = M.RoutePlan(((41.5, -93.6), (41.6, -93.6)), 1000, 60)
  places._routes = SimpleNamespace(route=lambda _: (plan, ""))
  assert places.can_start() and places.start()
  assert places.active()["name"] == "Home"
  places.pick({"place_name": "Old name-only recent"})
  assert places.draft() is None
  assert "no coordinates" in places._nav._search_error


def test_routing_preference_uses_existing_backup_marker_convention(monkeypatch, tmp_path):
  from openpilot.selfdrive.ui.tandem.prefs import save_prefs, restore_prefs
  monkeypatch.delenv("TANDEM_ROUTING", raising=False)
  C.set_policy(offline_only=True, preferred="offline")
  assert C.policy() == (True, "offline")
  backup = tmp_path / "backup"
  save_prefs(backup)
  C.set_policy(offline_only=False, preferred="online")
  assert C.enabled() and C.policy() == (False, "online")
  restore_prefs(backup)
  assert C.policy() == (True, "offline")


def test_mutations_recheck_parked_state_and_fail_closed(monkeypatch):
  import pytest
  from openpilot.starpilot.tandem.routing.maps import remove_all
  def blocked():
    raise C.RoutingError("park_to_change")
  monkeypatch.setattr(C, "require_parked", blocked)
  with pytest.raises(C.RoutingError, match="park_to_change"):
    remove_all()


def test_recalculation_uses_chip_without_replacing_estimates_or_street():
  from openpilot.selfdrive.ui.tandem.onroad.status import Snapshot, chips_for, routing_chip
  from openpilot.selfdrive.ui.tandem.routing_status import display_estimate
  from openpilot.selfdrive.ui.tandem.settings.maps import Progress
  route = routing_chip({"status": "rerouting", "active": True}, 100)
  chips = chips_for(Snapshot(lateral_paused=True, routing=route))
  assert [c.key for c in chips] == ["pause_button", "routing"]
  assert chips[-1].label == "Recalculating route"
  assert routing_chip({"status": "ready", "provider": "online", "fallback_at": 100}, 101, True) is None
  assert routing_chip({"status": "ready", "provider": "offline", "fallback_at": 100}, 104) is None
  estimate = {"estimate": {"at": 100, "seconds": 720, "meters": 13500}}
  assert display_estimate(estimate, 105) == (715, 13500)
  for now in (99, 121):
    assert display_estimate(estimate, now) is None
  assert display_estimate({"estimate": {"at": "bad"}}, 101) is None
  assert Progress(False, 0, 0, "", phase="ready").fraction == 1


def test_routing_keeps_ram_at_lowest_priority():
  from openpilot.selfdrive.ui.tandem.onroad.status import ChipStack, Snapshot, chips_for, routing_chip
  route = routing_chip({"status": "rerouting", "active": True}, 100)
  state = Snapshot(lateral_paused=True, routing=route, low_ram=True, memory_percent=91)
  assert [c.key for c in chips_for(state)] == ["pause_button", "routing", "low_memory"]
  stack = ChipStack()
  stack.MAX = 2
  assert {c.key for c, _ in stack.update(state, 100, False)} == {"pause_button", "routing"}


def test_local_rebuild_measures_installation_and_never_marks_it_ready_early():
  from openpilot.selfdrive.ui.tandem.settings.maps import Progress, RegionProgress
  region = RegionProgress("us_state.IA", 0, 0, False)
  progress = Progress(True, 0, 0, "Iowa", (region,), phase="install", unit="bytes", current_regions=(region.location,))
  assert progress.fraction == 0 and progress.step == 2 and progress.active
  assert progress.current is region and not region.finished
  from dataclasses import replace
  building = replace(progress, done=38, total=100, stage="build")
  assert building.fraction == .38 and not building.regions[0].finished
  assert [building.step_complete(i) for i in range(4)] == [True, True, False, False]
  checking = replace(building, done=94, stage="check")
  assert checking.fraction == .94
  assert replace(checking, done=100).fraction == .99  # activation remains
  ready = replace(checking, active=False, phase="ready", regions=(replace(region, ready=True),))
  assert ready.fraction == 1 and ready.regions[0].finished and all(ready.step_complete(i) for i in range(4))


def test_shared_maps_adds_missing_routes_without_redownloading_roads():
  from openpilot.selfdrive.ui.tandem.settings.map_source import CombinedMaps
  from openpilot.selfdrive.ui.tandem.settings.maps import Progress, RegionProgress
  from openpilot.starpilot.tandem.routing import maps
  calls = []
  road_progress = Progress(False, 10, 10, "Iowa", (RegionProgress("us_state.IA", 10, 10),))
  road = SimpleNamespace(_layout=SimpleNamespace(_params=SimpleNamespace(get=lambda *a, **k: "us_state.IA")),
                         progress=lambda: road_progress, download=lambda: calls.append("road"))
  source = CombinedMaps(road)
  source.road_ready, source.route_ready = {"us_state.IA"}, set()
  source.download()
  pending = maps.read("map-request.json")
  assert pending["selection"] == "us_state.IA" and not pending["wait_for_road"] and calls == []
  source.job = {"phase": "road", "regions_ready": []}
  progress = source.progress()
  assert progress.active and not progress.regions[0].finished  # no gap before routing preparation


def test_shared_state_selection_can_clear_and_update_without_road_downloads(monkeypatch, tmp_path):
  from openpilot.selfdrive.ui.tandem.settings.map_source import CombinedMaps
  from openpilot.selfdrive.ui.tandem.settings.maps import Maps, Progress
  from openpilot.starpilot.tandem.routing import catalog, maps
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path))
  monkeypatch.setattr(catalog, "load", lambda **_: {"schema": 2})
  monkeypatch.setattr(catalog, "plan", lambda *a, **k: ([{"bytes": 0}], set()))
  picked, calls = [""], []
  road = SimpleNamespace(_layout=SimpleNamespace(_params=SimpleNamespace(get=lambda *a, **k: picked[0])),
    has_selection=lambda: bool(picked[0]), checks=lambda: [("Parked", True)],
    progress=lambda: Progress(False, 0, 0, ""), downloaded=lambda: True, download=lambda: calls.append("road"),
    selection_summary=lambda: "None selected")
  source = CombinedMaps(road)
  source.road_ready = source.route_ready = {"us_state.IA"}
  monkeypatch.setattr(source, "checks", lambda: [("Parked", True), ("Wi-Fi", True)])
  model = Maps(SimpleNamespace(), source)
  assert model.ready() and not model.blocked_reason() and source.download_label() == "Update maps"
  assert source.summary()["routes"] == "Removed on update"
  source.download()
  assert maps.read("map-request.json")["selection"] == "" and not calls
  assert not model.ready()  # avoid duplicate clear requests while the operation runs
  source.job = {"selection": "", "phase": "ready"}
  source.route_ready = set()
  assert source.progress().phase == "" and not source.progress().active


def test_state_picker_does_not_replan_or_read_installed_graphs_on_each_draw(monkeypatch):
  from openpilot.selfdrive.ui.tandem.settings.map_source import CombinedMaps
  from openpilot.starpilot.tandem.routing import bundles, catalog
  data = {"schema": 2, "dataset": {"regions": {"us_state.IA": {}, "us_state.IL": {}}}, "packages": []}
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  monkeypatch.setattr(catalog, "ready_regions", lambda: set())
  calls, picked = [], ["us_state.IA"]
  disk_reads = []
  monkeypatch.setattr(bundles, "installed", lambda: disk_reads.append("snapshot") or [])
  monkeypatch.setattr(catalog, "plan", lambda selection, *_: (calls.append(selection) or [{"bytes": 1000}], set()))
  road = SimpleNamespace(_layout=SimpleNamespace(_params=SimpleNamespace(get=lambda key, **_: picked[0] if key == "MapsSelected" else "")),
    _m=SimpleNamespace(REGIONAL_PACKAGES={}), tick=lambda: None, downloaded=lambda: True)
  source = CombinedMaps(road)
  source.road_ready = {"us_state.IA", "us_state.IL"}
  for _ in range(10):
    assert source.region_status("us_state.IA")[1] == "Routes not downloaded"
    source.summary()
    source.download_label()
    source.routes_size()
  assert calls == ["us_state.IA"]
  assert not disk_reads
  picked[0] = "us_state.IL"
  source.summary()
  assert calls == ["us_state.IA", "us_state.IL"]
  source.tick()
  source.summary()
  assert calls == ["us_state.IA", "us_state.IL", "us_state.IL"]
  assert disk_reads == ["snapshot"]


def test_same_state_update_keeps_road_controller_and_deselection_reuses_roads(monkeypatch):
  from openpilot.selfdrive.ui.tandem.settings.map_source import CombinedMaps
  from openpilot.starpilot.tandem.routing import catalog, maps
  monkeypatch.setattr(catalog, "load", lambda **_: {"schema": 2})
  calls, picked = [], ["us_state.IA,us_state.IL"]
  road = SimpleNamespace(_layout=SimpleNamespace(_params=SimpleNamespace(get=lambda *a, **k: picked[0])),
                         download=lambda: calls.append("road"))
  source = CombinedMaps(road)
  source.road_ready = source.route_ready = {"us_state.IA", "us_state.IL"}
  source.download()
  assert calls == ["road"]  # an ordinary Update still checks upstream road data
  picked[0] = "us_state.IA"
  source.download()
  assert calls == ["road"] and maps.read("map-request.json")["selection"] == "us_state.IA"
