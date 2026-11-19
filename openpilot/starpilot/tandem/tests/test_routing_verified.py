"""Full checks stay off the route path; changed data loses its ready receipt."""
import io
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import bundles, config as C, maps, native_worker, verified
from openpilot.starpilot.tandem.tests.test_routing import make_bundle, response
from openpilot.starpilot.tandem.routing.normalize import normalize


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  monkeypatch.setattr(C, "runtime_ready", lambda: True)


def test_worker_start_and_repeated_requests_never_scan_graph(monkeypatch, tmp_path, capsys):
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  bundles.activate(bundle.id)
  original = bundles.digest
  def digest(path, *args):
    assert path.name != "tiles.tar", "route path scanned the installed graph"
    return original(path, *args)
  monkeypatch.setattr(bundles, "digest", digest)
  configs = []
  class Actor:
    def __init__(self, config):
      configs.append(config)
    def route(self, _):
      return response()
  monkeypatch.setitem(sys.modules, "valhalla", SimpleNamespace(Actor=Actor,
    get_config=lambda **_: {"mjolnir": {"data_processing": {}}, "thor": {}}))
  monkeypatch.setattr(native_worker, "isolate_network", lambda: "test")
  message = {"bundle": bundle.id, "generation": bundle.generation, "start": [41.58, -93.62, None],
             "destination": {"latitude": 41.59, "longitude": -93.60}}
  monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO((json.dumps(message) + "\n").encode() * 2)))
  assert bundles.capability()["status"] == "ready"
  native_worker.main()
  values = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
  assert [v["status"] for v in values] == ["ok", "ok"] and len(configs) == 1
  assert configs[0]["thor"]["clear_reserved_memory"]
  assert configs[0]["mjolnir"]["use_simple_mem_cache"]


def test_same_size_change_even_with_restored_mtime_invalidates_receipt(tmp_path):
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  path = bundle.folder / "tiles.tar"
  before = path.stat()
  path.write_bytes(b"x" * before.st_size)
  os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
  assert not verified.read(bundle)
  assert bundles.capability()["status"] == "data_incompatible"
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    bundles.verify(bundle.folder)
  assert not (bundle.folder / verified.RECEIPT).exists()


def test_missing_receipt_is_rebuilt_only_by_parked_audit(monkeypatch, tmp_path):
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  verified.invalidate(bundle)
  manager = maps.Manager(SimpleNamespace(), prepare=lambda **_: None, allowed=lambda: False)
  manager.audit()
  assert not verified.read(bundle)
  manager.allowed = lambda: True
  manager.audit()
  verified.require(bundle)
  assert bundles.capability()["status"] == "ready"


def test_audit_detects_corruption_without_file_metadata_change(monkeypatch, tmp_path):
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  # Model storage corruption: the cached stat identity still matches, but bytes
  # supplied by the full scanner no longer match the expected digest.
  old = verified.read(bundle)
  old["checked_at"] -= verified.INTERVAL + 1
  C.atomic_json(bundle.folder / verified.RECEIPT, old)
  original = bundles.digest
  monkeypatch.setattr(bundles, "digest", lambda path, *args: "0" * 64 if path.name == "tiles.tar" else original(path, *args))
  assert verified.read(bundle)
  maps.Manager(SimpleNamespace(), prepare=lambda **_: None).audit()
  assert not verified.read(bundle) and bundles.capability()["status"] == "data_incompatible"


def test_receipt_does_not_survive_inode_replacement(tmp_path):
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  path = bundle.folder / "tiles.tar"
  replacement = bundle.folder / "replacement"
  replacement.write_bytes(path.read_bytes())
  replacement.replace(path)
  assert not verified.read(bundle)
  bundles.verify(bundle.folder)
  verified.require(bundle)


@pytest.mark.parametrize("change", ["content", "replacement", "permissions", "rename"])
def test_operation_hashes_require_the_complete_unchanged_identity(tmp_path, monkeypatch, change):
  path = tmp_path / "checked"
  path.write_bytes(b"original bytes")
  cache, scans, original = verified.Hashes(), [], bundles.digest
  def digest(source, *args):
    scans.append(source)
    return original(source, *args)
  monkeypatch.setattr(bundles, "digest", digest)
  first = cache.digest(path)
  assert cache.digest(path) == first and len(scans) == 1
  before = path.stat()
  if change == "content":
    path.write_bytes(b"different data")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
  elif change == "replacement":
    replacement = tmp_path / "new"
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)
  elif change == "permissions":
    path.chmod(0o444)
  else:
    moved = Path(str(path) + ".moved")
    path.replace(moved)
    moved.replace(path)
  assert cache.digest(path) == original(path) and len(scans) == 2
  assert (cache.digest(path) != first) == (change == "content")


def test_mutation_during_hash_is_not_recorded_as_verified(tmp_path, monkeypatch):
  path = tmp_path / "changing"
  path.write_bytes(b"initial bytes")
  original = bundles.digest
  def digest(source, *args):
    result = original(source, *args)
    source.write_bytes(b"changed bytes")
    return result
  monkeypatch.setattr(bundles, "digest", digest)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    verified.Hashes().digest(path)


def test_coarse_filesystem_clock_does_not_hide_a_same_tick_write(tmp_path, monkeypatch):
  path = tmp_path / "coarse-clock"
  path.write_bytes(b"initial bytes")
  actual_identity, actual_fstat = verified.identity, os.fstat
  quantum = 100_000_000  # model a filesystem whose metadata clock ticks at 100 ms
  def identity(source):
    value = actual_identity(source)
    value[3:] = [stamp // quantum * quantum for stamp in value[3:]]
    return value
  class CoarseStat:
    def __init__(self, value):
      self.value = value
    def __getattr__(self, name):
      return getattr(self.value, name)
    @property
    def st_ctime_ns(self):
      return self.value.st_ctime_ns // quantum * quantum
  monkeypatch.setattr(verified, "identity", identity)
  monkeypatch.setattr(os, "fstat", lambda fd: CoarseStat(actual_fstat(fd)))
  original = bundles.digest
  def digest(source, *args):
    checksum = original(source, *args)
    source.write_bytes(b"changed bytes")
    return checksum
  monkeypatch.setattr(bundles, "digest", digest)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    verified.Hashes().digest(path)


def test_compact_native_payload_preserves_all_guidance_fields():
  raw = response()
  raw["waypoints"] = [{"unused": "x" * 10000}]
  for step in raw["routes"][0]["legs"][0]["steps"]:
    step["intersections"] = [{"unused": "x" * 10000}]
  compact = native_worker.compact_response(raw)
  assert normalize(compact) == normalize(raw)
  assert len(json.dumps(compact)) < len(json.dumps(raw)) / 5


def test_idle_worker_is_released_during_active_guidance(monkeypatch):
  from openpilot.starpilot.tandem.routing import routingd
  # No destination lookup is needed: navigation keeps the completed route.
  closed = threading.Event()
  monkeypatch.setitem(sys.modules, "openpilot.common.params", SimpleNamespace(
    Params=lambda: SimpleNamespace(get=lambda _: b"active destination")))
  native = SimpleNamespace(last_used=0, close=closed.set)
  broker = routingd.Broker(native=native)
  try:
    assert closed.wait(2)
  finally:
    broker.close()
