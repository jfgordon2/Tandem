"""Pair state transfers without replacing mapd's downloader or scheduler."""
import ast
import datetime
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, downloads, handoff, maps
from openpilot.starpilot.tandem.tests import test_routing_states

pytest_plugins = (test_routing_states.__name__,)


class Params:
  def __init__(self, **values):
    self.values = values

  def get(self, key, **_):
    return self.values.get(key)

  def get_bool(self, key):
    return bool(self.get(key))

  def put(self, key, value):
    self.values[key] = value

  def put_bool(self, key, value):
    self.put(key, value)

  def remove(self, key):
    self.values.pop(key, None)


@pytest.fixture
def pairing(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "store"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  for name in C.SCREENS:
    monkeypatch.setenv(name, "1")
  monkeypatch.setattr(handoff, "available", lambda: True)
  monkeypatch.setattr(handoff, "wait_for_road_idle", lambda *_: True)
  data = catalog.load()
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  return Params(MapsSelected="us_state.IA,us_state.IL"), Params()


def road_progress(memory, region, *, complete=False):
  memory.put("MapsDownloadProgress", json.dumps({"selectedKey": region, "updatedAt": time.time(),  # noqa: TID251
    "downloadedFiles": 10 if complete else 5, "totalFiles": 10, "active": not complete, "completed": complete}))


def drive_manager(manager, errors):
  end = time.monotonic() + 10
  while not maps.read("map-request.json") and time.monotonic() < end:
    time.sleep(.01)
  try:
    manager.run(maps.read("map-request.json"))
  except Exception as error:
    errors.append(error)


def test_pairing_overlaps_both_routing_workers_with_road_and_installs_once(shared, pairing, monkeypatch):
  params, memory = pairing
  dataset = shared.data["dataset"]
  C.atomic_json(C.root() / "catalog.json", shared.data)
  road_started, illinois_started, overlap = threading.Event(), threading.Event(), threading.Barrier(2)
  native_transfer, transfers, roads, errors, reports = downloads._transfer, [], [], [], []
  lock = threading.Lock()
  first_parts = set(dataset["regions"]["us_state.IA"]["parts"])
  def transfer(part, *args, **kwargs):
    with lock:
      transfers.append(part["id"])
      first_two = len(transfers) <= 2
    if first_two:
      assert road_started.wait(5)
      overlap.wait(5)  # two actual transfer threads coexist with the road worker
    if part["id"] not in first_parts:
      assert handoff.road_receipt(maps.read("map-request.json")["id"])["completed"] == ["us_state.IA"]
      assert illinois_started.wait(5)
      assert roads == ["us_state.IA", "us_state.IL"]
    return native_transfer(part, *args, **kwargs)
  monkeypatch.setattr(downloads, "_transfer", transfer)
  manager = maps.Manager(memory, prepare=lambda **_: None)
  publish = manager.publish
  def report(**values):
    publish(**values)
    reports.append(dict(manager.state))
  monkeypatch.setattr(manager, "publish", report)
  thread = threading.Thread(target=drive_manager, args=(manager, errors), daemon=True)
  thread.start()
  def updater(now, selected, scoped_memory, manual_update=False):
    region = selected.get("MapsSelected")
    roads.append(region)
    assert manual_update and params.get("MapsSelected") == "us_state.IA,us_state.IL"
    assert handoff.in_progress()
    previous_id = maps.read("map-request.json")["id"]
    maps.on_map_download_started(region)
    assert maps.read("map-request.json")["id"] == previous_id  # no recursive companion job
    road_progress(scoped_memory, region)
    road_started.set()
    if region == "us_state.IL":
      illinois_started.set()
    if region == "us_state.IA":
      end = time.monotonic() + 5
      while not overlap.broken and overlap.n_waiting and time.monotonic() < end:
        time.sleep(.01)
    time.sleep(.05)
    road_progress(scoped_memory, region, complete=True)
    selected.put("LastMapsUpdate", "one state")
    scoped_memory.remove("DownloadMaps")
    assert memory.get_bool("DownloadMaps")
  assert handoff.coordinate(updater, datetime.datetime(2026, 11, 4), params, memory, params.get("MapsSelected"), "today")
  thread.join(10)
  assert not thread.is_alive() and not errors
  assert maps.read()["phase"] == "ready", maps.read()
  assert roads == ["us_state.IA", "us_state.IL"]
  assert len(transfers) == len(set(transfers)) == len(dataset["parts"])
  assert set(bundles.active().manifest["regions"]) == {"us_state.IA", "us_state.IL"}
  assert params.get("LastMapsUpdate") == "today" and not memory.get_bool("DownloadMaps")
  assert any(r.get("region_progress", {}).get("us_state.IA", {}).get("done") == 500 for r in reports)
  assert not any(r.get("region_progress", {}).get("us_state.IL", {}).get("done", 0) for r in reports
                 if r.get("road_region") == "us_state.IA")
  assert all(r.get("road_ready") for r in reports if r["phase"] == "install")


def test_current_routing_selection_still_updates_roads_then_reports_measured_checks(shared, pairing, monkeypatch):
  params, memory = pairing
  package = catalog.plan(params.get("MapsSelected"))[0][0]
  downloads.install(package)
  C.atomic_json(C.root() / "catalog.json", shared.data)
  shared.requested.clear()
  manager = maps.Manager(memory, prepare=lambda **_: None)
  roads, errors, reports = [], [], []
  publish = manager.publish
  def report(**values):
    publish(**values)
    reports.append(dict(manager.state))
  monkeypatch.setattr(manager, "publish", report)
  thread = threading.Thread(target=drive_manager, args=(manager, errors), daemon=True)
  thread.start()
  def updater(now, selected, scoped_memory, **_):
    roads.append(selected.get("MapsSelected"))
    road_progress(scoped_memory, roads[-1], complete=True)
  handoff.coordinate(updater, datetime.datetime(2026, 11, 4), params, memory, params.get("MapsSelected"), "today")
  thread.join(10)
  assert not thread.is_alive() and not errors and maps.read()["phase"] == "ready"
  assert roads == ["us_state.IA", "us_state.IL"] and shared.requested == []
  checks = [r for r in reports if r["phase"] == "install"]
  assert checks and all(r["stage"] == "check" and r["road_ready"] for r in checks)
  assert checks[-1]["done"] == checks[-1]["total"] > 0


@pytest.mark.parametrize("failure", ["runtime_missing", "no_space", "download_failed"])
def test_routing_failure_still_finishes_all_roads(pairing, monkeypatch, failure):
  params, memory = pairing
  def fail(**_):
    raise C.RoutingError(failure)
  manager, roads, errors = maps.Manager(memory, prepare=fail), [], []
  thread = threading.Thread(target=drive_manager, args=(manager, errors), daemon=True)
  thread.start()
  def updater(now, selected, scoped_memory, **_):
    roads.append(selected.get("MapsSelected"))
    road_progress(scoped_memory, roads[-1], complete=True)
  handoff.coordinate(updater, None, params, memory, params.get("MapsSelected"), "today")
  thread.join(5)
  assert not errors and not thread.is_alive()
  assert roads == ["us_state.IA", "us_state.IL"]
  assert maps.read()["phase"] == "failed" and maps.read()["road_ready"]
  assert params.get("LastMapsUpdate") == "today"


def test_routing_transfer_failure_keeps_the_active_state_and_finishes_remaining_roads(shared, pairing, monkeypatch):
  params, memory = pairing
  C.atomic_json(C.root() / "catalog.json", shared.data)
  road_started = threading.Event()
  def failed(*_, **__):
    assert road_started.wait(5)
    raise C.RoutingError("download_failed")
  monkeypatch.setattr(downloads, "_transfer", failed)
  manager, roads, errors = maps.Manager(memory, prepare=lambda **_: None), [], []
  thread = threading.Thread(target=drive_manager, args=(manager, errors), daemon=True)
  thread.start()
  def updater(now, selected, scoped_memory, **_):
    region = selected.get("MapsSelected")
    roads.append(region)
    road_started.set()
    road_progress(scoped_memory, region, complete=True)
  handoff.coordinate(updater, None, params, memory, params.get("MapsSelected"), "today")
  thread.join(5)
  assert not thread.is_alive() and not errors
  assert roads == ["us_state.IA", "us_state.IL"]
  assert maps.read()["phase"] == "failed" and maps.read()["error"] == "download_failed" and maps.read()["road_ready"]
  assert bundles.installed() == []


@pytest.mark.parametrize("disabled", [True, False])
def test_unavailable_pairing_leaves_original_downloader_in_charge(pairing, monkeypatch, disabled):
  params, memory = pairing
  monkeypatch.setattr(handoff, "available", lambda: False)
  monkeypatch.setenv("TANDEM_ROUTING", "0" if disabled else "1")
  assert not handoff.coordinate(None, None, params, memory, params.get("MapsSelected"), "today")
  assert not maps.read("map-request.json") and not memory.get_bool("DownloadMaps")
  assert handoff.regions_for("nation.CA") == []


def test_resume_uses_only_same_job_road_receipts_and_cancellation_never_starts_next_state(pairing, monkeypatch):
  params, memory = pairing
  pending = handoff.enqueue(params.get("MapsSelected"), paired=True, road_regions=["us_state.IA", "us_state.IL"])
  C.atomic_json(C.root() / "map-road.json", {"id": pending["id"], "completed": ["us_state.IA"]})
  C.atomic_json(C.root() / "map-job.json", {**pending, "phase": "download", "road_region": "us_state.IL"})
  roads = []
  def updater(now, selected, scoped_memory, **_):
    roads.append(selected.get("MapsSelected"))
    memory.put_bool("CancelDownloadMaps", True)
    assert scoped_memory.get_bool("CancelDownloadMaps")
    scoped_memory.remove("CancelDownloadMaps")
  assert handoff.coordinate(updater, None, params, memory, params.get("MapsSelected"), "today")
  assert roads == ["us_state.IL"] and maps.read("map-cancel.json")["id"] == pending["id"]
  assert handoff.road_receipt("another-job")["completed"] == []
  assert not memory.get_bool("DownloadMaps") and not memory.get_bool("CancelDownloadMaps")


def test_terminal_cancellation_does_not_fall_back_to_downloading_remaining_states(pairing):
  params, memory = pairing
  pending = handoff.enqueue(params.get("MapsSelected"), paired=True, road_regions=["us_state.IA", "us_state.IL"])
  # A restart may find a pending request before the broker records cancellation.
  C.atomic_json(C.root() / "map-job.json", {**pending, "phase": "download"})
  def finish_cancel():
    time.sleep(.05)
    C.atomic_json(C.root() / "map-job.json", {**pending, "phase": "cancelled"})
  thread = threading.Thread(target=finish_cancel)
  thread.start()
  def updater(*_, **__):
    pytest.fail("cancelled job started road maps")
  handoff.coordinate(updater, None, params, memory, params.get("MapsSelected"), "today")
  thread.join()


def test_next_road_command_waits_for_mapd_to_finish_its_previous_cancel(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path))
  monkeypatch.setattr(handoff, "cancelled", lambda *_: False)
  class Subscriber:
    count = 0
    updated = {"mapdExtendedOut": True}
    def update(self, *_):
      self.count += 1
    def __getitem__(self, _):
      return SimpleNamespace(downloadProgress=SimpleNamespace(active=self.count < 3))
  subscriber = Subscriber()
  assert handoff.wait_for_road_idle("test", Params(), subscriber)
  assert subscriber.count == 3


def test_cancel_while_waiting_for_previous_road_operation_does_not_send_a_new_command(monkeypatch):
  monkeypatch.setattr(handoff, "cancelled", lambda *_: True)
  assert not handoff.wait_for_road_idle("test", Params(), SimpleNamespace())


@pytest.mark.parametrize("manual,schedule", [(True, 0), (False, 1), (False, 2)])
def test_actual_upstream_downloader_runs_each_state_once_and_keeps_original_schedule(pairing, manual, schedule):
  params, memory = pairing
  params.put("PreferredSchedule", schedule)
  path = Path(__file__).resolve().parents[2] / "common/starpilot_functions.py"
  node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "update_maps")
  sent, errors = [], []
  class Sub:
    updated = {"mapdExtendedOut": True}
    count = 0
    def update(self, *_):
      self.count += 1
    def __getitem__(self, _):
      return SimpleNamespace(downloadProgress=SimpleNamespace(active=self.count == 1, totalFiles=10,
                                                              downloadedFiles=5 if self.count == 1 else 10))
  def publish(target, selection, *_, progress=None, completed=False, **kwargs):
    target.put("MapsDownloadProgress", json.dumps({"selectedKey": selection, "updatedAt": time.time(),  # noqa: TID251
      "completed": completed, "totalFiles": progress.totalFiles if progress else 0,
      "downloadedFiles": progress.downloadedFiles if progress else 0}))
  env = {"_get_maps_storage_cache": lambda _: SimpleNamespace(storage_known=True, storage_bytes=100, maps_present=True,
          selection_estimate_bytes=lambda _: 100), "sanitize_selected_locations_csv": lambda s: s,
    "normalize_schedule_value": int, "selection_key": lambda s: s, "_publish_maps_progress": publish,
    "_reconcile_maps_storage": lambda *a, **k: 100, "time": SimpleNamespace(monotonic=time.monotonic, sleep=lambda _: None),
    "messaging": SimpleNamespace(PubMaster=lambda _: SimpleNamespace(send=lambda _, msg: sent.append((msg.mapdIn.type, msg.mapdIn.str))),
      SubMaster=lambda _: Sub(), new_message=lambda _: SimpleNamespace(mapdIn=SimpleNamespace()))}
  exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), env)
  manager = maps.Manager(memory, prepare=lambda **_: None)
  def installer(package, **kwargs):
    for region in package["regions"]:
      manager.publish(force=True, road_region=region)
      while region not in handoff.road_receipt(manager.state["id"])["completed"]:
        manager.gate()
        time.sleep(.01)
    manager.publish(phase="install", stage="check", road_ready=True)
  manager.installer = installer
  thread = threading.Thread(target=drive_manager, args=(manager, errors), daemon=True)
  thread.start()
  # November 1 is both Sunday and the first of the month.
  env["update_maps"](datetime.datetime(2026, 11, 1), params, memory, manual)
  thread.join(5)
  assert not thread.is_alive() and not errors
  assert maps.read()["phase"] == "ready", maps.read()
  assert sent == [(0, "us_state.IA"), (0, "us_state.IL")]
  assert params.get("MapsSelected") == "us_state.IA,us_state.IL"
  assert params.get("LastMapsUpdate") == "November 1st, 2026"
  assert not memory.get_bool("DownloadMaps")
