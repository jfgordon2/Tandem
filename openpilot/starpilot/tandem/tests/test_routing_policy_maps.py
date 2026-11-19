"""Provider fallback, catalog integrity, shared jobs, scheduling and deletion."""
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, downloads, maps
from openpilot.starpilot.tandem.tests.test_routing import make_bundle


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  for name in C.SCREENS:
    monkeypatch.setenv(name, "1")
  # StarPilot 7's map owner isn't on this machine; test_routing_road.py covers the road step
  from openpilot.starpilot.tandem.routing import road
  monkeypatch.setattr(road, "ensure", lambda *args, **kwargs: None)


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


def test_bundled_country_catalog_covers_selector_and_arbitrary_state_unions():
  from openpilot.starpilot.tandem.routing.regions import STATE_TOKENS
  data = catalog.validate(json.loads(Path(catalog.__file__).with_suffix(".json").read_text()))
  assert data["schema"] == 2
  dataset = data["dataset"]
  assert set(dataset["regions"]) == STATE_TOKENS
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


def legacy_catalog():
  return catalog.validate(json.loads((Path(__file__).parent / "fixtures/routing-catalog-v1.json").read_text()))




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
  manager = maps.Manager(installer=install, prepare=lambda **_: None)
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
  manager = maps.Manager(allowed.is_set, prepare=lambda **_: None)
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
  manager = maps.Manager(installer=install, prepare=lambda **_: None)
  maps.request("us_state.IA")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "failed"   # the road step's retry skips what StarPilot has (test_routing_road.py)
  maps.request("us_state.IA")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "ready" and maps.read()["regions_ready"] == ["us_state.IA"]
  assert len(calls) == 2


def test_manager_shutdown_retains_active_job_for_restart(monkeypatch):
  data = catalog.load()
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  maps.request("us_state.IA")
  manager = maps.Manager(installer=lambda *a, **k: None, prepare=lambda **_: None)
  manager.stop.set()
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] in maps.ACTIVE and maps.read()["paused"]
  restarted = maps.Manager(installer=lambda *a, **k: None, prepare=lambda **_: None)
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
