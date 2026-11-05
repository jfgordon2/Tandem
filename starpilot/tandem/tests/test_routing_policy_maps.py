"""Provider fallback, catalog integrity, shared jobs, scheduling and deletion."""
import ast
import builtins
import datetime
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, downloads, maps
from openpilot.starpilot.tandem.routing.route_engine import PolicyRouteEngine
from openpilot.starpilot.tandem.tests.test_routing import make_bundle


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  for name in C.SCREENS:
    monkeypatch.setenv(name, "1")


@pytest.mark.parametrize("only,first,success,expected", [
  (False, "online", "online", ["online"]), (False, "offline", "offline", ["offline"]),
  (False, "online", "offline", ["online", "offline"]), (False, "offline", "online", ["offline", "online"]),
  (True, "online", "online", ["offline"]), (True, "offline", "offline", ["offline"]),
  (False, "online", "neither", ["online", "offline"]), (False, "offline", "neither", ["offline", "online"]),
])
def test_provider_policy_attempts_each_once(only, first, success, expected):
  C.set_policy(offline_only=only, preferred=first)
  calls, route = [], object()
  def provider(name):
    def fetch(*_):
      calls.append(name)
      return route if name == success else None
    return SimpleNamespace(fetch_route=fetch, status="no_route")
  engine = PolicyRouteEngine(online=provider("online"), offline=provider("offline"))
  result = engine.fetch_route("key", None, {})
  assert calls == expected
  assert (result is route) == (success in expected)
  assert C.policy() == (only, first)


def test_strict_change_during_local_failure_prevents_online_fallback():
  C.set_policy(preferred="offline")
  calls = []
  def offline(*_):
    C.set_policy(offline_only=True)
    return None
  engine = PolicyRouteEngine(online=SimpleNamespace(fetch_route=lambda *_: calls.append("network")),
    offline=SimpleNamespace(fetch_route=offline, status="no_route"))
  assert engine.fetch_route("key", None, {}) is None
  assert calls == [] and engine.status == "superseded"
  C.set_policy(offline_only=False)
  assert C.policy() == (False, "offline")


def test_corrupt_saved_policy_fails_closed():
  C.set_policy(offline_only=True)
  C.policy_path().write_text("truncated {")
  assert C.provider_order() == ("offline",)
  C.policy_path().write_text('{"offline_only": "false", "preferred": "online"}')
  assert C.provider_order() == ("offline",)


def test_maintainer_rollback_is_separate_from_driver_policy(monkeypatch):
  monkeypatch.delenv("TANDEM_ROUTING")
  C.set_policy(offline_only=True, preferred="offline")
  C.set_enabled(False)
  assert not C.enabled() and C.policy() == (True, "offline")
  C.set_enabled(True)
  assert C.enabled() and C.policy() == (True, "offline")


def test_online_exception_and_missing_key_fall_back_offline():
  result = object()
  def broken(*_):
    raise ValueError("invalid online payload")
  engine = PolicyRouteEngine(online=SimpleNamespace(fetch_route=broken),
    offline=SimpleNamespace(fetch_route=lambda *_: result, status="ready"))
  assert engine.fetch_route("key", None, {}) is result and engine.provider == "offline"
  assert engine.fallback_at > 0
  assert engine.fetch_route("", None, {}) is result


def legacy_catalog():
  return catalog.validate(json.loads((Path(__file__).parent / "fixtures/routing-catalog-v1.json").read_text()))


def test_bundled_country_catalog_covers_selector_and_arbitrary_state_unions():
  from openpilot.starpilot.common.maps_catalog import VALID_MAP_TOKENS
  data = catalog.validate(json.loads(Path(catalog.__file__).with_suffix(".json").read_text()))
  assert data["schema"] == 2
  dataset = data["dataset"]
  assert set(dataset["regions"]) == {token for token in VALID_MAP_TOKENS if token.startswith("us_state.")}
  parts = {part["id"]: part for part in dataset["parts"]}
  for selection in ("us_state.IA,us_state.IL", "us_state.CA,us_state.NY,us_state.PR", "nation.US", ""):
    planned, missing = catalog.plan(selection, data)
    assert not missing and len(planned) == 1
    expected = {part for region in catalog.tokens(selection) for part in dataset["regions"][region]["parts"]}
    assert set(planned[0]["parts"]) == expected
    assert planned[0]["bytes"] == sum(parts[part]["bytes"] for part in expected)
  national, _ = catalog.plan("nation.US", data)
  assert set(national[0]["parts"]) == set(parts)
  iowa = set(dataset["regions"]["us_state.IA"]["parts"])
  illinois = set(dataset["regions"]["us_state.IL"]["parts"])
  assert iowa & illinois  # Border/hierarchy packs are shared once, not duplicated.
  _, missing = catalog.plan("nation.CA", data)
  assert missing == {"nation.CA"}


def test_legacy_catalog_resolves_connected_coverage_and_reports_missing():
  data = legacy_catalog()
  packages, missing = catalog.plan("us_state.IA,us_state.IL", data)
  assert len(packages) == 1 and set(packages[0]["regions"]) == {"us_state.IA", "us_state.IL"} and not missing
  packages, missing = catalog.plan("us_state.IA,us_state.WI", data)
  assert len(packages) == 1 and packages[0]["regions"] == ["us_state.IA"] and missing == {"us_state.WI"}
  assert "us_state.IA" in catalog.tokens("nation.US")
  for change in ({"schema": 0}, {"packages": [{}]}):
    with pytest.raises(C.RoutingError, match="catalog_unavailable"):
      catalog.validate({**data, **change})


def test_catalog_snapshot_reuses_parsed_metadata_and_detects_atomic_replacement(monkeypatch):
  path = C.root() / "catalog.json"
  data = legacy_catalog()
  C.atomic_json(path, data)
  checks, validate = [], catalog.validate
  def checked(value):
    checks.append(value)
    return validate(value)
  monkeypatch.setattr(catalog, "validate", checked)
  assert catalog.load() is catalog.load() and len(checks) == 1
  data["packages"][0]["title"] = "A newer catalog snapshot"
  C.atomic_json(path, data)
  assert catalog.load()["packages"][0]["title"] == "A newer catalog snapshot" and len(checks) == 2


def test_iowa_then_illinois_installs_connected_package_once(monkeypatch):
  data, calls = legacy_catalog(), []
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  def install(package, **kwargs):
    calls.append(package["id"])
    bundle = make_bundle(C.root() / "bundles" / package["id"], package["id"])
    manifest = {**bundle.manifest, "regions": package["regions"], "built_at": str(len(calls))}
    if "us_state.IL" in package["regions"]:
      manifest["bounds"] = [-97, 36, -87, 44]
    C.atomic_json(bundle.folder / "manifest.json", manifest)
    return bundles.verify(bundle.folder)
  manager = maps.Manager(SimpleNamespace(), installer=install, prepare=lambda **_: None)
  maps.request("us_state.IA")
  manager.run(maps.read("map-request.json"))
  initial = calls[0]
  start, destination = [41.5868, -93.6250, None], {"latitude": 41.8781, "longitude": -87.6298}
  with pytest.raises(C.RoutingError, match="outside_coverage"):
    bundles.for_trip(start, destination)
  maps.request("us_state.IL")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "ready" and len(calls) == 2
  assert bundles.for_trip(start, destination).id == calls[1]
  assert {b.id for b in bundles.installed()} == {initial, calls[1]}
  assert catalog.ready_regions() == {"us_state.IA", "us_state.IL"}
  maps.request("us_state.IA,us_state.IL")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "ready" and len(calls) == 2


def test_download_resumes_range_and_verifies_hash(monkeypatch, tmp_path):
  target, content, requests = tmp_path / "partial", b"verified graph bytes", []
  target.write_bytes(content[:5])
  class Response(io.BytesIO):
    status = 206
    headers = {"Content-Range": f"bytes 5-{len(content)-1}/{len(content)}"}
  def open_(request, **_):
    requests.append(request)
    return Response(content[5:])
  monkeypatch.setattr(downloads.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=open_))
  progress = []
  downloads.fetch("https://example.test/graph", target, len(content), hashlib.sha256(content).hexdigest(),
                  progress=lambda done, total: progress.append((done, total)))
  assert requests[0].get_header("Range") == "bytes=5-"
  assert target.read_bytes() == content and progress[-1] == (len(content), len(content))
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    downloads.fetch("https://example.test/graph", target, len(content), "0" * 64)
  assert not target.exists()


def test_connection_loss_reopens_at_saved_offset(monkeypatch, tmp_path):
  content, requests = b"verified graph bytes", []
  class Response(io.BytesIO):
    def __init__(self, data, initial):
      super().__init__(data)
      self.status, self.initial, self.reads = (200 if initial else 206), initial, 0
      self.headers = {"Content-Range": f"bytes 5-{len(content)-1}/{len(content)}"}
    def read(self, size):
      self.reads += 1
      if self.initial and self.reads > 1:
        raise OSError("connection lost")
      return super().read(size)
  def open_(request, **_):
    requests.append(request)
    return Response(content[:5] if len(requests) == 1 else content[5:], len(requests) == 1)
  monkeypatch.setattr(downloads.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=open_))
  monkeypatch.setattr(downloads.time, "sleep", lambda _: None)
  target = tmp_path / "partial"
  downloads.fetch("https://example.test/graph", target, len(content), hashlib.sha256(content).hexdigest())
  assert len(requests) == 2 and requests[1].get_header("Range") == "bytes=5-"
  assert target.read_bytes() == content


def test_paused_job_resumes_and_cancellation_is_scoped(monkeypatch):
  allowed = threading.Event()
  identity = maps.request("us_state.IA")
  manager = maps.Manager(SimpleNamespace(), allowed.is_set, prepare=lambda **_: None)
  manager.state = {"id": identity, "phase": "download"}
  entered = threading.Event()
  thread = threading.Thread(target=lambda: (manager.gate(), entered.set()))
  thread.start()
  for _ in range(100):
    if maps.read().get("paused"):
      break
    time.sleep(.005)
  assert maps.read()["paused"] and not entered.is_set()
  allowed.set()
  thread.join(1)
  assert entered.is_set() and not maps.read()["paused"]
  maps.cancel()
  with pytest.raises(C.RoutingError, match="cancelled"):
    manager.gate()
  next_id = maps.request("us_state.IA")
  manager.state["id"] = next_id
  manager.gate()  # an older cancel cannot cancel a later job


def test_shared_job_keeps_road_success_and_retries_only_routes(monkeypatch):
  data = catalog.load()
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  calls = []
  def install(package, **kwargs):
    calls.append(package["id"])
    kwargs["progress"](50, 100)
    kwargs["installing"]()
    if len(calls) == 1:
      raise C.RoutingError("download_failed")
  manager = maps.Manager(SimpleNamespace(), installer=install, prepare=lambda **_: None)
  maps.request("us_state.IA")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "failed" and maps.read()["road_ready"]
  maps.request("us_state.IA")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "ready" and maps.read()["regions_ready"] == ["us_state.IA"]
  assert len(calls) == 2


def test_manager_shutdown_retains_active_job_for_restart(monkeypatch):
  data = catalog.load()
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  maps.request("us_state.IA")
  manager = maps.Manager(SimpleNamespace(), installer=lambda *a, **k: None, prepare=lambda **_: None)
  manager.stop.set()
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] in maps.ACTIVE and maps.read()["paused"]
  restarted = maps.Manager(SimpleNamespace(), installer=lambda *a, **k: None, prepare=lambda **_: None)
  restarted.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "ready"


def test_deletion_leases_all_graphs_before_deleting_anything(tmp_path):
  import fcntl
  first = bundles.install(make_bundle(tmp_path / "a", "a").folder)
  second = bundles.install(make_bundle(tmp_path / "b", "b").folder)
  bundles.activate(first.id)
  with (second.folder / ".lease").open("a") as stream:
    fcntl.flock(stream, fcntl.LOCK_SH)
    with pytest.raises(C.RoutingError, match="busy"):
      maps.remove_all()
    assert first.folder.exists() and second.folder.exists()
  maps.remove_all()
  assert bundles.installed() == [] and not (C.root() / "active.json").exists()


@pytest.mark.parametrize("schedule,date,manual,expected", [
  (1, (2026, 11, 8), False, 1), (1, (2026, 11, 7), False, 0),
  (2, (2026, 12, 1), False, 1), (2, (2026, 12, 2), False, 0),
  (0, (2026, 12, 1), False, 0), (0, (2026, 12, 2), True, 1),
])
@pytest.mark.parametrize("failure", ["none", "import", "call", "pair_import", "pair_call"])
def test_actual_upstream_schedule_starts_both_datasets(monkeypatch, schedule, date, manual, expected, failure):
  # Execute the real update_maps function with transport stand-ins. This tests
  # the actual Weekly/Monthly gates and the hook's position after those gates.
  path = Path(__file__).resolve().parents[2] / "common/starpilot_functions.py"
  node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "update_maps")
  class Params:
    values = {"MapsSelected": "us_state.IA", "PreferredSchedule": schedule}
    def get(self, key):
      return self.values.get(key)
    def get_bool(self, _):
      return False
    def put(self, key, value):
      self.values[key] = value
    def put_bool(self, *_):
      pass
    def remove(self, *_):
      pass
  class Sub:
    updated = {"mapdExtendedOut": True}
    count = 0
    def update(self, *_):
      self.count += 1
    def __getitem__(self, _):
      return SimpleNamespace(downloadProgress=SimpleNamespace(active=self.count == 1, totalFiles=10))
  events, sent = [], []
  def hook(selection):
    events.append(selection)
    if failure == "call":
      raise RuntimeError("routing hook failed")
  real_import = builtins.__import__
  def import_(name, *args, **kwargs):
    if failure == "import" and name == "openpilot.starpilot.tandem.routing.maps":
      raise ImportError("routing hook unavailable")
    if failure == "pair_import" and name == "openpilot.starpilot.tandem.routing.handoff":
      raise ImportError("paired coordinator unavailable")
    return real_import(name, *args, **kwargs)
  from openpilot.starpilot.tandem.routing import handoff
  monkeypatch.setattr(handoff, "available", lambda: False)
  if failure == "pair_call":
    def failed(*_, **__):
      raise RuntimeError("paired coordinator failed")
    monkeypatch.setattr(handoff, "coordinate", failed)
  monkeypatch.setattr(maps, "on_map_download_started", hook)
  monkeypatch.setattr(builtins, "__import__", import_)
  env = {"_get_maps_storage_cache": lambda _: SimpleNamespace(storage_known=True, storage_bytes=100, maps_present=True,
          selection_estimate_bytes=lambda _: 100), "sanitize_selected_locations_csv": lambda s: s,
    "normalize_schedule_value": int, "selection_key": lambda s: s, "_publish_maps_progress": lambda *a, **k: None,
    "_reconcile_maps_storage": lambda *a, **k: 100, "time": SimpleNamespace(monotonic=lambda: 1, sleep=lambda _: None),
    "messaging": SimpleNamespace(PubMaster=lambda _: SimpleNamespace(send=lambda _, msg: sent.append((msg.mapdIn.type, msg.mapdIn.str))),
      SubMaster=lambda _: Sub(), new_message=lambda _: SimpleNamespace(mapdIn=SimpleNamespace())),
    "__builtins__": {**vars(builtins), "__import__": import_}}
  exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), env)
  env["update_maps"](datetime.datetime(*date), Params(), Params(), manual)
  assert events == (["us_state.IA"] * expected if failure not in ("import", "pair_import") else [])
  assert sent == [(0, "us_state.IA")] * expected


@pytest.mark.parametrize("where", ["enabled", "request"])
def test_companion_hook_swallows_unexpected_failures(monkeypatch, where):
  def failed(*args, **kwargs):
    raise RuntimeError("unexpected routing failure")
  monkeypatch.setattr(C if where == "enabled" else maps, where, failed)
  maps.on_map_download_started("us_state.IA")


def test_companion_request_does_not_wait_for_graph_installation():
  with bundles.lock():
    thread = threading.Thread(target=maps.on_map_download_started, args=("us_state.IA",))
    thread.start()
    thread.join(1)
    returned_while_locked = not thread.is_alive()
  thread.join(2)  # release a regressed blocking implementation before failing
  assert returned_while_locked, "road-map hook waited on the graph install lock"
  pending = maps.read("map-request.json")
  assert pending["selection"] == "us_state.IA" and pending["wait_for_road"]
