"""Selection changes free legacy tiles without touching retained/shared data."""
import json
import time

import pytest

from openpilot.starpilot.common.maps_download_progress import MapsStorageCache, load_maps_storage_cache
from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, downloads, maps as jobs, road
from openpilot.starpilot.tandem.tests.test_routing_paired import Params
from openpilot.starpilot.tandem.tests import test_routing_states

pytest_plugins = (test_routing_states.__name__,)


@pytest.fixture
def maps(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  for name in C.SCREENS:
    monkeypatch.setenv(name, "1")
  monkeypatch.setattr(C, "require_parked", lambda: None)
  road.root().mkdir()
  return Params(), Params()


def tile(lat, lon, content=b"legacy tile"):
  path = road.root() / str(lat) / str(lon) / f"{lat:.6f}_{lon:.6f}_{lat + .25:.6f}_{lon + .25:.6f}"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_bytes(content)
  return path


def cache(params, *selections):
  value = MapsStorageCache()
  for selection in selections:
    value.reconcile(1000, selection_key=selection, total_files=20, updated_at="2026-11-05")
  params.put(road.CACHE, value.to_json())


def test_installed_binary_menu_and_override_use_the_downloaders_footprints(tmp_path):
  data = road.menu()
  footprints = road.footprint("us_state.IA,us_state.IL", data)
  ia, il = footprints["us_state.IA"], footprints["us_state.IL"]
  assert len(ia) == 8 and len(il) == 12 and ia & il == {(40, -92), (42, -92)}
  assert road.regions("nation.US") == {"us_state." + code for code in road.US_STATE_CODES}
  for code in road.US_STATE_CODES:
    assert road.footprint("us_state." + code, data)["us_state." + code]
  custom = tmp_path / "mapd_download_menu.json"
  custom.write_text(json.dumps({"nation": {}, "us_state": {"IA": {
    "bounding_box": {"min_lat": 40, "min_lon": -96, "max_lat": 44, "max_lon": -90},
    "download_rows": [[40, -94, -92]]}}}))
  native = road.menu(override=custom)
  assert len(road.footprint("us_state.IA", native)["us_state.IA"]) == (1 if native["_download_rows_supported"] else 6)
  binary = tmp_path / "mapd"
  binary.write_bytes(b'binary supporting json:"download_rows,omitempty"')
  assert road.footprint("us_state.IA", road.menu(binary, custom))["us_state.IA"] == {(40, -94)}
  custom.write_text("invalid")
  with pytest.raises(ValueError):
    road.menu(override=custom)  # never silently substitute the embedded menu


def test_unrecognized_binary_cannot_authorize_deletion(tmp_path):
  binary = tmp_path / "mapd"
  binary.write_bytes(b"new binary format without a readable region menu")
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    road.menu(binary, tmp_path / "absent")


@pytest.mark.parametrize("selection", ["us_state.GU", "us_state.IA,us_state.GU", "nation.US"])
@pytest.mark.parametrize("null_entry", [False, True])
def test_missing_guam_menu_entry_uses_local_coverage_and_cleans_other_regions(maps, monkeypatch, selection, null_entry):
  params, memory = maps
  native_menu = road.menu()
  native_menu["us_state"].pop("GU", None)
  if null_entry:
    native_menu["us_state"]["GU"] = None
  monkeypatch.setattr(road, "menu", lambda: native_menu)
  monkeypatch.setattr(catalog.urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("cleanup used the network"))
  guam, iowa, foreign = tile(12, 144), tile(40, -96), tile(0, 20)
  cache(params, "us_state.GU", "us_state.IA", "nation.US")
  road.apply(selection, lambda: None, memory, params=params)
  assert guam.read_bytes() == b"legacy tile" and not foreign.exists()
  assert iowa.exists() == (selection != "us_state.GU")
  value = load_maps_storage_cache(params.get(road.CACHE))
  assert not value.selection_updated_at("us_state.GU")  # retention is not proof of a legacy download
  assert not value.selection_updated_at("nation.US")
  if "us_state.IA" in road.regions(selection):
    assert value.selection_updated_at("us_state.IA")


def test_guam_fallback_uses_bundled_metadata_when_cached_catalog_lacks_it(monkeypatch):
  monkeypatch.setattr(catalog, "load", lambda: {"schema": 1, "packages": []})
  assert road.footprint("us_state.GU", {"us_state": {}, "nation": {}})["us_state.GU"] == {(12, 142), (12, 144)}


def test_actual_mapd_definition_takes_precedence_over_the_routing_fallback(monkeypatch):
  def forbidden(*_):
    pytest.fail("existing mapd region consulted the fallback")
  monkeypatch.setattr(road, "_fallback_location", forbidden)
  data = {"nation": {}, "us_state": {"GU": {"bounding_box": {
    "min_lat": 12, "min_lon": 144, "max_lat": 16, "max_lon": 148}}}}
  assert road.footprint("us_state.GU", data)["us_state.GU"] == {(12, 144), (12, 146), (14, 144), (14, 146)}


@pytest.mark.parametrize("rows", [None, [], [[41, -94, -92]], [[40, -94, -92], [40, -94, -92]], [[40, -94]], [[40, -94, -98]]])
def test_invalid_optional_download_rows_match_mapds_bounding_box_fallback(rows):
  location = {"bounding_box": {"min_lat": 40.1, "min_lon": -95.1, "max_lat": 43.1, "max_lon": -90.1}, "download_rows": rows}
  assert road.groups(location) == {(lat, lon) for lat in (40, 42) for lon in (-96, -94, -92)}


def test_deselecting_illinois_keeps_iowa_and_shared_tiles_and_retires_old_ready_receipts(maps):
  params, memory = maps
  iowa, shared, illinois = tile(40, -96), tile(40, -92), tile(40, -88)
  cache(params, "us_state.IA,us_state.IL")  # includes installs predating per-state receipts
  road.apply("us_state.IA", lambda: None, memory, params=params)
  assert iowa.read_bytes() == shared.read_bytes() == b"legacy tile"
  assert not illinois.exists() and not illinois.parent.exists()
  value = load_maps_storage_cache(params.get(road.CACHE))
  assert set(value._selections) == {"us_state.IA"}
  assert value.selection_total_files("us_state.IA") == 8
  assert value.storage_bytes == len(b"legacy tile") * 2


def test_retained_country_tiles_and_other_selected_states_survive(maps):
  params, memory = maps
  data = road.menu()
  can_group = next(iter(road.footprint("nation.CA", data)["nation.CA"]))
  canada = tile(*can_group)
  iowa, illinois, texas = tile(40, -96), tile(40, -88), tile(30, -100)
  cache(params, "nation.CA", "us_state.IA", "us_state.IL")
  road.apply("us_state.IA,nation.CA", lambda: None, memory, params=params)
  # Canada's rounded archive bounds also need this northern Illinois group.
  assert canada.exists() and iowa.exists() and illinois.exists() and not texas.exists()
  assert set(load_maps_storage_cache(params.get(road.CACHE))._selections) == {"nation.CA", "us_state.IA"}


def test_empty_selection_clears_both_complete_and_partial_legacy_tiles_and_ready_receipts(maps):
  params, memory = maps
  paths = [tile(40, -96), tile(40, -88)]
  partial = paths[0].with_name(paths[0].name + ".part")
  partial.write_bytes(b"partial")
  cache(params, "us_state.IA", "us_state.IL")
  road.apply("", lambda: None, memory, params=params)
  assert not any(road.root().iterdir())
  value = load_maps_storage_cache(params.get(road.CACHE))
  assert value.storage_bytes == 0 and value._selections == {}


@pytest.mark.parametrize("selection", ["", "us_state.IA"])
def test_deselected_legacy_archive_downloads_are_also_removed(maps, selection):
  params, memory = maps
  archives = road.root().parent / "tmp/offline/40"
  archives.mkdir(parents=True)
  retained = archives / "-96.tar.gz.part"
  removed = archives / "-88.tar.gz"
  retained.write_bytes(b"resume if selected")
  removed.write_bytes(b"unused")
  road.apply(selection, lambda: None, memory, params=params)
  assert retained.exists() == bool(selection) and not removed.exists()


@pytest.mark.parametrize("selection", ["us_state.UNKNOWN", "invalid", "us_state.IA,nation.UNKNOWN"])
def test_unresolved_selection_fails_before_touching_any_tiles_or_receipts(maps, selection):
  params, memory = maps
  installed = tile(40, -88)
  cache(params, "us_state.IL")
  before = params.get(road.CACHE)
  with pytest.raises(C.RoutingError):
    road.apply(selection, lambda: None, memory, params=params)
  assert installed.exists() and params.get(road.CACHE) == before


@pytest.mark.parametrize("blocked", ["park", "disabled", "downloading", "active", "cancelled"])
def test_park_cancel_rollback_and_downloader_gates_preserve_tiles(maps, monkeypatch, blocked):
  params, memory = maps
  installed = tile(40, -88)
  cache(params, "us_state.IL")
  def stop():
    raise C.RoutingError("interrupted")
  if blocked == "park":
    monkeypatch.setattr(C, "require_parked", stop)
  elif blocked == "disabled":
    monkeypatch.setenv("TANDEM_ROUTING", "0")
  elif blocked == "downloading":
    memory.put_bool("DownloadMaps", True)
  elif blocked == "active":
    memory.put("MapsDownloadProgress", json.dumps({"active": True}))
  with pytest.raises(C.RoutingError):
    road.apply("", stop if blocked == "cancelled" else lambda: None, memory, params=params)
  assert installed.exists()


def test_paired_job_may_prune_after_both_downloads_while_coordinator_holds_flag(maps):
  params, memory = maps
  installed = tile(40, -88)
  memory.put_bool("DownloadMaps", True)
  memory.put("MapsDownloadProgress", json.dumps({"active": False, "completed": True}))
  road.apply("us_state.IA", lambda: None, memory, params=params, paired=True)
  assert not installed.exists() and memory.get_bool("DownloadMaps")


def test_unknown_files_and_symlinks_are_never_followed_or_removed(maps, tmp_path):
  params, memory = maps
  installed = tile(40, -88)
  external = tmp_path / "external"
  external.write_bytes(b"unrelated")
  link = installed.parent / "41.000000_-87.000000_41.250000_-86.750000"
  link.symlink_to(external)
  note = installed.parent / "notes.txt"
  note.write_bytes(b"keep")
  (road.root() / "42").symlink_to(installed.parent, target_is_directory=True)
  road.apply("", lambda: None, memory, params=params)
  assert not installed.exists() and external.read_bytes() == b"unrelated" and note.exists() and link.is_symlink()
  assert (road.root() / "42").is_symlink()


def test_interrupted_prune_retries_without_redownload_or_touching_retained_tiles(maps):
  params, memory = maps
  retained = tile(40, -96)
  removed = [tile(40, -88), tile(42, -88)]
  def gate():
    if sum(p.exists() for p in removed) == 1:
      raise C.RoutingError("interrupted")
  with pytest.raises(C.RoutingError):
    road.apply("us_state.IA", gate, memory, params=params)
  assert retained.exists()
  road.apply("us_state.IA", lambda: None, memory, params=params)
  assert retained.exists() and not any(p.exists() for p in removed)


def test_selection_update_activates_routes_before_pruning_roads_and_empty_clears_both(shared, maps, monkeypatch):
  params, memory = maps
  monkeypatch.setattr(catalog, "load", lambda **_: shared.data)
  downloads.install(catalog.plan("us_state.IA,us_state.IL")[0][0])
  retained, border, removed = tile(40, -98), tile(40, -92), tile(40, -88)
  cache(params, "us_state.IA,us_state.IL")
  actual, observed = road.apply, []
  def apply(selection, *args, **kwargs):
    if selection:
      assert bundles.active().manifest["regions"] == ["us_state.IA"]
    else:
      assert bundles.installed() == []
    observed.append(selection)
    actual(selection, *args, params=params, **kwargs)
  monkeypatch.setattr(road, "apply", apply)
  shared.requested.clear()
  manager = jobs.Manager(memory, prepare=lambda **_: None)
  jobs.request("us_state.IA")
  manager.run(jobs.read("map-request.json"))
  assert jobs.read()["phase"] == "ready"
  assert retained.exists() and border.exists() and not removed.exists()
  assert shared.requested == [] and observed == ["us_state.IA"]
  jobs.request("")
  manager.run(jobs.read("map-request.json"))
  assert jobs.read()["phase"] == "ready" and observed == ["us_state.IA", ""]
  assert bundles.installed() == [] and not any(road.root().iterdir())
  assert load_maps_storage_cache(params.get(road.CACHE))._selections == {}


def test_failed_route_rebuild_preserves_previous_road_tiles_and_receipts(shared, maps, monkeypatch):
  params, memory = maps
  monkeypatch.setattr(catalog, "load", lambda **_: shared.data)
  previous = downloads.install(catalog.plan("us_state.IA,us_state.IL")[0][0])
  retained, removed = tile(40, -96), tile(40, -88)
  cache(params, "us_state.IA,us_state.IL")
  before = params.get(road.CACHE)
  def fail(*_, **__):
    raise C.RoutingError("no_space")
  manager = jobs.Manager(memory, prepare=lambda **_: None, installer=fail)
  jobs.request("us_state.IA")
  manager.run(jobs.read("map-request.json"))
  assert jobs.read()["phase"] == "failed" and bundles.active().id == previous.id
  assert retained.exists() and removed.exists() and params.get(road.CACHE) == before


def test_completed_legacy_only_country_update_prunes_even_when_routing_is_unavailable(shared, maps, monkeypatch):
  params, memory = maps
  monkeypatch.setattr(catalog, "load", lambda **_: shared.data)
  canada = tile(60, -110)
  texas = tile(30, -100)
  cache(params, "nation.CA", "us_state.TX")
  actual = road.apply
  monkeypatch.setattr(road, "apply", lambda *a, **k: actual(*a, params=params, **k))
  jobs.request("nation.CA", wait_for_road=True)
  memory.put("MapsDownloadProgress", json.dumps({"selectedKey": "nation.CA", "active": False,
    "completed": True, "updatedAt": time.time()}))  # noqa: TID251
  manager = jobs.Manager(memory, prepare=lambda **_: pytest.fail("country without routing started runtime installation"))
  manager.run(jobs.read("map-request.json"))
  assert jobs.read()["error"] == "coverage_unavailable"
  assert canada.exists() and not texas.exists()
  assert set(load_maps_storage_cache(params.get(road.CACHE))._selections) == {"nation.CA"}
