"""Offline provider contracts, independent of hardware, cereal and the native installation."""
import copy
import fcntl
import json
import sys
from pathlib import Path
import threading
import time

import pytest

from openpilot.starpilot.tandem.routing import bundles, config as C
from openpilot.starpilot.tandem.routing.native_worker import route_options
from openpilot.starpilot.tandem.routing.normalize import normalize
from openpilot.starpilot.tandem.routing.routingd import Broker
from openpilot.starpilot.tandem.routing.navigationd import navigationd_type


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path))
  monkeypatch.setenv("TANDEM_STATE_DIR", str(tmp_path / "state"))
  monkeypatch.delenv("TANDEM_ROUTING", raising=False)
  for screen in C.SCREENS:
    monkeypatch.setenv(screen, "1")


def make_bundle(path, identity="test-graph", value=b"synthetic graph"):
  path.mkdir(parents=True)
  graph = path / "tiles.tar"
  graph.write_bytes(value)
  C.atomic_json(path / "manifest.json", {"schema": 1, "id": identity, "runtime_version": C.VERSION,
    "bounds": [-97, 40, -90, 44], "source": {"url": "synthetic"}, "attribution": "Synthetic test data",
    "files": {"tiles.tar": {"sha256": bundles.digest(graph), "bytes": len(value)}}})
  return bundles.load(path)


def response():
  points = [[-93.62, 41.58], [-93.61, 41.58], [-93.60, 41.58], [-93.60, 41.59]]
  def step(kind, location, distance, modifier="straight"):
    return {"maneuver": {"type": kind, "location": location, "modifier": modifier, "instruction": "Test instruction"},
            "distance": distance, "duration": distance / 10, "bannerInstructions": []}
  steps = [step("depart", points[0], 1660), step("turn", points[2], 1110, "left"), step("arrive", points[-1], 0)]
  steps[0]["bannerInstructions"] = [{"distanceAlongGeometry": 1000, "primary": {"text": "Test St", "type": "turn", "modifier": "left"},
    "sub": {"components": [{"type": "lane", "active": True, "directions": ["left", "straight"], "active_direction": "left"}]}}]
  return {"code": "Ok", "routes": [{"geometry": {"type": "LineString", "coordinates": points}, "distance": 2770, "duration": 277,
    "legs": [{"steps": steps, "annotation": {"maxspeed": [{"speed": 50, "unit": "km/h"}, {"unknown": True},
                                                             {"speed": 30, "unit": "mph"}]}}]}]}


def test_online_preferred_default_and_each_upstream_switch_wins(monkeypatch):
  assert C.enabled() and C.policy() == (False, "online")
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  assert C.enabled()
  for screen in C.SCREENS:
    monkeypatch.setenv(screen, "0")
    assert not C.enabled()
    monkeypatch.setenv(screen, "1")
  monkeypatch.setenv("TANDEM_ROUTING", "0")
  assert not C.enabled()
  class Original:
    pass
  assert navigationd_type(Original) is Original


def test_missing_runtime_and_wrong_receipt_are_not_ready():
  import shutil
  C.set_enabled(True)
  assert bundles.capability()["status"] == "runtime_missing"
  python = C.runtime_python()
  python.parent.mkdir(parents=True)
  python.symlink_to(sys.executable)
  C.atomic_json(python.parent.parent / "receipt.json", {"version": "0.0"})
  assert not C.runtime_ready()
  C.atomic_json(python.parent.parent / "receipt.json", {"version": C.VERSION})
  assert C.runtime_ready() and bundles.capability()["status"] == "data_missing"
  shutil.rmtree(python.parent)
  assert not C.runtime_ready()


def test_install_is_immutable_and_activation_atomic(tmp_path):
  first = make_bundle(tmp_path / "source")
  installed = bundles.install(first.folder)
  assert bundles.activate(first.id).generation == installed.generation
  with pytest.raises(C.RoutingError, match="bundle_exists"):
    bundles.install(make_bundle(tmp_path / "changed", value=b"different").folder)
  assert bundles.active().generation == first.generation
  second = make_bundle(tmp_path / "other", "other-graph")
  bundles.install(second.folder)
  bundles.activate(second.id)
  selector = json.loads((C.root() / "active.json").read_text())
  assert selector["previous"]["id"] == first.id
  bundles.activate(first.id)
  assert bundles.active().id == first.id


def test_corruption_missing_files_and_path_escape_rejected(tmp_path):
  bundle = make_bundle(tmp_path / "source")
  (bundle.folder / "tiles.tar").write_bytes(b"corrupted graph")
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    bundles.install(bundle.folder)
  for identity in ("../escape", "/data", "", ".hidden"):
    with pytest.raises(C.RoutingError, match="invalid_request"):
      bundles.activate(identity)
  (bundle.folder / "tiles.tar").unlink()
  with pytest.raises(C.RoutingError):
    bundles.load(bundle.folder)


def test_active_reader_lease_blocks_removal_without_touching_other_maps(tmp_path):
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  bundles.activate(bundle.id)
  unrelated = tmp_path / "osm" / "offline"
  unrelated.mkdir(parents=True)
  (unrelated / "mapd-tile").write_text("keep")
  with (bundle.folder / ".lease").open("a") as stream:
    fcntl.flock(stream, fcntl.LOCK_SH)
    with pytest.raises(C.RoutingError, match="busy"):
      bundles.remove(bundle.id)
  bundles.remove(bundle.id)
  assert (unrelated / "mapd-tile").read_text() == "keep"
  with pytest.raises(C.RoutingError, match="data_missing"):
    bundles.active()


def test_symlink_bundle_rejected(tmp_path):
  source = make_bundle(tmp_path / "source")
  alias = tmp_path / "alias"
  alias.symlink_to(source.folder, target_is_directory=True)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    bundles.install(alias)


def test_corrupt_package_can_be_removed_and_reinstalled(tmp_path):
  source = make_bundle(tmp_path / "source")
  installed = bundles.install(source.folder)
  bundles.activate(installed.id)
  (installed.folder / "manifest.json").write_text("broken")
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    bundles.active()
  bundles.remove(installed.id)
  assert not installed.folder.exists()
  assert bundles.install(source.folder).id == source.id


def test_normalize_preserves_speed_slots_and_upcoming_banner():
  route = normalize(response())
  assert route["geometry"][0] == {"latitude": 41.58, "longitude": -93.62}
  assert [item["speed"] for item in route["maxspeed"]] == [50, 0, 30]
  assert route["steps"][0]["maneuver"] == "depart"
  assert route["steps"][0]["bannerInstructions"][0]["primary"]["modifier"] == "left"
  assert route["steps"][-1]["maneuver"] == "arrive"
  assert route["totalDistance"] == 2770 and route["totalDuration"] == 277


def test_actual_pinned_iowa_response_keeps_geometry_banners_and_legal_speeds():
  raw = json.loads((Path(__file__).parent / "fixtures/valhalla-iowa-3.9.1.json").read_text())
  route = normalize(raw)
  assert len(route["geometry"]) == 105 and len(route["maxspeed"]) == 104
  assert len(route["steps"]) == 8
  assert route["steps"][-1]["maneuver"] == "arrive"
  assert 2800 < route["totalDistance"] < 3000
  assert any(b.get("sub") for s in route["steps"] for b in s["bannerInstructions"])


@pytest.mark.parametrize("damage", ["coordinate_order", "nan", "negative", "units", "speed_slots", "type", "lane"])
def test_bad_native_data_rejected_before_publication(damage):
  value = response()
  route = value["routes"][0]
  if damage == "coordinate_order":
    route["geometry"]["coordinates"][0] = [41.58, -93.62]
  elif damage == "nan":
    route["duration"] = float("nan")
  elif damage == "negative":
    route["legs"][0]["steps"][0]["distance"] = -1
  elif damage == "units":
    route["legs"][0]["annotation"]["maxspeed"][0]["unit"] = "knots"
  elif damage == "speed_slots":
    route["legs"][0]["annotation"]["maxspeed"].pop()
  elif damage == "type":
    route["legs"][0]["steps"][1]["maneuver"]["type"] = "invented turn"
  else:
    route["legs"][0]["steps"][0]["bannerInstructions"][0]["sub"]["components"][0]["active"] = "yes"
  with pytest.raises(C.RoutingError, match="invalid_response"):
    normalize(value)


def test_native_options_are_local_keyless_and_do_not_reuse_mapbox_alt():
  data = {"start": [41.58, -93.62, 270], "destination": {"latitude": 41.59, "longitude": -93.60, "routeId": "alt-1"},
          "language": "main_de"}
  options = route_options(data)
  assert options["format"] == "osrm" and options["banner_instructions"]
  assert options["locations"][0]["heading"] == 270 and options["language"] == "de"
  assert "token" not in json.dumps(options) and "alternates" not in options
  data["start"][2] = None
  assert "heading" not in route_options(data)["locations"][0]
  data["start"][0] = float("inf")
  with pytest.raises(C.RoutingError, match="invalid_request"):
    route_options(data)


def test_broker_supersedes_old_request_and_serializes_native(monkeypatch):
  from openpilot.starpilot.tandem.routing import routingd
  monkeypatch.setattr(routingd, "capability", lambda: {"status": "ready", "generation": "graph"})
  entered, release = threading.Event(), threading.Event()
  class Native:
    last_used = time.monotonic()
    def call(self, message):
      if message["name"] == "old":
        entered.set()
        assert release.wait(2)
      return {"status": "ok", "name": message["name"]}
    def close(self):
      pass
  broker = Broker(Native())
  results = {}
  def submit(name):
    results[name] = broker.submit({"caller": "preview", "generation": "graph", "name": name})
  old = threading.Thread(target=submit, args=("old",))
  old.start()
  assert entered.wait(2)
  new = threading.Thread(target=submit, args=("new",))
  new.start()
  for _ in range(100):
    if broker.jobs.qsize():
      break
    time.sleep(.001)
  release.set()
  old.join(2)
  new.join(2)
  broker.close()
  assert results["old"]["status"] == "superseded"
  assert results["new"] == {"status": "ok", "name": "new"}


def test_no_route_and_malformed_results_are_distinct():
  value = copy.deepcopy(response())
  value["code"] = "NoRoute"
  with pytest.raises(C.RoutingError, match="no_route"):
    normalize(value)
  with pytest.raises(C.RoutingError, match="invalid_response"):
    normalize({})


def test_insufficient_space_preserves_current_bundle(tmp_path, monkeypatch):
  first = bundles.install(make_bundle(tmp_path / "first").folder)
  bundles.activate(first.id)
  second = make_bundle(tmp_path / "second", "second")
  monkeypatch.setattr(bundles.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 0})())
  with pytest.raises(C.RoutingError, match="no_space"):
    bundles.install(second.folder)
  assert bundles.active().id == first.id
  assert not (C.root() / "bundles" / second.id).exists()


def test_runtime_cancellation_terminates_child(monkeypatch):
  from openpilot.starpilot.tandem.routing.tools import runtime
  children = []
  original = runtime.subprocess.Popen
  def spawn(*args, **kwargs):
    child = original(*args, **kwargs)
    children.append(child)
    return child
  monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
  with pytest.raises(C.RoutingError, match="cancelled"):
    runtime.checked_run([sys.executable, "-c", "import time; time.sleep(30)"], cancelled=lambda: True)
  assert len(children) == 1 and children[0].poll() is not None


def test_runtime_aborts_when_parked_guard_changes(monkeypatch):
  from openpilot.starpilot.tandem.routing.tools import runtime
  def driving():
    raise C.RoutingError("park_to_change")
  monkeypatch.setattr(C, "require_parked", driving)
  with pytest.raises(C.RoutingError, match="park_to_change"):
    runtime.checked_run([sys.executable, "-c", "import time; time.sleep(30)"])


def test_download_cancelled_staging_is_not_installed(tmp_path, monkeypatch):
  import io
  from openpilot.starpilot.tandem.routing.tools import manage
  source = make_bundle(tmp_path / "source")
  class Opener:
    def open(self, url, **kwargs):
      return io.BytesIO((source.folder / ("manifest.json" if url.endswith("manifest.json") else "tiles.tar")).read_bytes())
  monkeypatch.setattr(manage.urllib.request, "build_opener", lambda *_: Opener())
  with pytest.raises(C.RoutingError, match="cancelled"):
    manage.download("https://example.com/manifest.json", cancelled=lambda: True)
  assert not bundles.installed() and not list((C.root() / "staging").iterdir())
  with pytest.raises(C.RoutingError, match="invalid_request"):
    manage.HTTPSRedirect().redirect_request(None, None, 302, "", {}, "http://example.com/tiles.tar")


def test_native_crash_and_hang_are_bounded_and_restartable(tmp_path, monkeypatch):
  from openpilot.starpilot.tandem.routing.routingd import Native
  script = tmp_path / "python"
  def program(body):
    script.write_text(f"#!{sys.executable}\n" + body)
    script.chmod(0o700)
  monkeypatch.setattr(C, "runtime_python", lambda: script)
  native = Native()
  bundle = bundles.install(make_bundle(tmp_path / "source").folder)
  message = {"bundle": bundle.id, "generation": bundle.generation}
  try:
    program("raise SystemExit(1)\n")
    assert native.call(message)["status"] == "worker_failed"
    native.retry_at = 0
    program("import time\ntime.sleep(30)\n")
    started = time.monotonic()
    # A hung worker must not block the broker while filling its stdin pipe either.
    assert native.call({**message, "_deadline": started + .2, "unused": "x" * 1024**2})["status"] == "timeout"
    assert time.monotonic() - started < 2 and native.process is None
    native.retry_at = 0
    program('import sys\nfor line in sys.stdin: print(\'{"status":"ok"}\', flush=True)\n')
    assert native.call(message) == {"status": "ok"}
    child = native.process
  finally:
    native.close()
  assert child.poll() is not None
