"""Exact state updates reuse shared-build data and publish only complete graphs."""
import hashlib
import io
import json
import shutil
import sys
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import bundles as B, catalog, config as C, datasets, downloads, images, tiles as T, verified
from openpilot.starpilot.tandem.routing.tools import states
from openpilot.starpilot.tandem.tests.test_routing_images import decoder  # noqa: F401


class Rectangle:
  def __init__(self, *bounds):
    self.bounds = bounds

  def intersects(self, other):
    a, b = self.bounds, other.bounds
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]

  def distance(self, other):
    a, b = self.bounds, other.bounds
    return max(a[0] - b[2], b[0] - a[2], 0) + max(a[1] - b[3], b[1] - a[3], 0)


@pytest.fixture
def shared(monkeypatch, tmp_path, request):
  request.getfixturevalue("decoder")
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "store"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_MOUNT_DIR", str(tmp_path / "mounts"))
  monkeypatch.setattr(C, "runtime_ready", lambda: True)
  for name in C.SCREENS:
    monkeypatch.setenv(name, "1")
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  # Geometry is a builder dependency, not a device/test-runtime dependency.
  monkeypatch.setitem(sys.modules, "shapely.geometry", SimpleNamespace(box=Rectangle))
  monkeypatch.setattr(states, "polygon", lambda path: Rectangle(*json.loads(path.read_text())))
  def pack(chunks, size, image, gate=lambda: None):
    digest, count = hashlib.sha256(), 0
    with image.open("wb") as target:
      target.write(b"fixture:")
      for chunk in chunks:
        gate()
        digest.update(chunk)
        count += len(chunk)
        target.write(chunk)
    assert count == size
    return {"bytes": count, "sha256": digest.hexdigest()}
  monkeypatch.setattr(images, "pack_stream", pack)
  graph = tmp_path / "graph"
  for level, lon, content in ((0, -94, b"Shared highway hierarchy"), (1, -94, b"Iowa arterial hierarchy"),
      (1, -91.5, b"Shared arterial hierarchy"), (2, -94, b"Iowa"), (2, -91.5, b"Shared border"),
      (2, -88, b"Illinois"), (2, -85, b"Complete-way fringe")):
    step = (4, 1, .25)[level]
    number = int((41 + 90) / step) * int(360 / step) + int((lon + 180) / step)
    digits = f"{number:09d}"
    path = graph / str(level) / digits[:3] / digits[3:6] / (digits[6:] + ".gph")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content * 20)
  first, second = tmp_path / "ia.poly", tmp_path / "il.poly"
  first.write_text("[-96, 40, -91, 44]")
  second.write_text("[-92, 40, -87, 44]")
  output = tmp_path / "published"
  data = states.partition(graph, output, "shared-test", {
    "us_state.IA": {"title": "Iowa", "polygon": first}, "us_state.IL": {"title": "Illinois", "polygon": second}},
    {"source": {"url": "synthetic"}, "attribution": "Synthetic graph", "built_at": "2026-11-04"}, "https://test.example/data")
  requested = []
  assets = {}
  for entry in data["dataset"]["parts"]:
    folder = output / "parts" / entry["id"]
    assets[entry["manifest"]] = (folder / "manifest.json").read_bytes()
    for name, spec in B.load(folder).manifest["files"].items():
      assets[spec["url"]] = (folder / name).read_bytes()
  class Response(io.BytesIO):
    status = 200
    headers = {}
  def open_(request, **_):
    url = request if isinstance(request, str) else request.full_url
    requested.append(url)
    return Response(assets[url])
  monkeypatch.setattr(downloads.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=open_))
  monkeypatch.setattr(catalog, "load", lambda **_: data)
  rows, backing = {}, {}
  monkeypatch.setattr(images, "sys", SimpleNamespace(platform="linux"))
  monkeypatch.setattr(images, "_mounts", lambda: rows)
  monkeypatch.setattr(images, "_backing", lambda row: backing[row["device"]])
  def command(args, **_):
    from pathlib import Path
    point = Path(args[-1])
    if args[0] == "mount":
      source = Path(args[-2])
      assert source.read_bytes().startswith(b"fixture:")
      (point / "tiles.tar").write_bytes(source.read_bytes()[8:])
      device = str(len(backing))
      backing[device] = source
      rows[point] = {"type": "squashfs", "options": {"ro", "nodev", "nosuid", "noexec"}, "device": device}
    else:
      rows.pop(point)
      (point / "tiles.tar").unlink()
  monkeypatch.setattr(images, "_command", command)
  return SimpleNamespace(data=data, requested=requested, mounts=rows, output=output, assets=assets, graph=graph)


def update(selection):
  package, missing = catalog.plan(selection)
  assert not missing and len(package) == 1
  return downloads.install(package[0])


def test_incremental_states_reuse_border_tiles_and_no_op_update_checks_full_hash(shared, monkeypatch):
  first = update("us_state.IA")
  first_image = images.source(first).read_bytes()
  first_parts = set(first.manifest["parts"])
  shared.requested.clear()
  second = update("us_state.IA,us_state.IL")
  assert not first.folder.exists() and B.active().id == second.id
  assert set(second.manifest["regions"]) == {"us_state.IA", "us_state.IL"}
  assert all(not any(part in url for part in first_parts) for url in shared.requested)
  assert len(shared.requested) == 3  # only Illinois-exclusive manifest, image and inventory
  assert not shared.mounts
  assert sum(1 for _ in (C.root() / "bundles").iterdir()) == 1
  shared.requested.clear()
  full_checks = []
  original = B.digest
  def digest(path, *args):
    if path.name == "tiles.squashfs":
      full_checks.append(path)
    return original(path, *args)
  monkeypatch.setattr(B, "digest", digest)
  assert update("us_state.IA,us_state.IL").generation == second.generation
  assert full_checks and not shared.requested
  # Deselect Illinois: no downloads and canonical Iowa bytes match the first update.
  first_again = update("us_state.IA")
  assert not shared.requested and images.source(first_again).read_bytes() == first_image
  assert catalog.ready_regions() == {"us_state.IA"}


def test_deselect_one_state_needs_no_network_and_drops_only_unreferenced_parts(shared):
  both = update("us_state.IA,us_state.IL")
  data = shared.data["dataset"]
  common = set(data["regions"]["us_state.IA"]["parts"]) & set(data["regions"]["us_state.IL"]["parts"])
  shared.requested.clear()
  remaining = update("us_state.IL")
  assert not shared.requested and not both.folder.exists()
  assert set(remaining.manifest["parts"]) == set(data["regions"]["us_state.IL"]["parts"])
  assert common <= set(remaining.manifest["parts"])
  assert catalog.ready_regions() == {"us_state.IL"}
  with pytest.raises(C.RoutingError, match="outside_coverage"):
    B.for_trip((41, -94, None), {"latitude": 41, "longitude": -88})


def test_interrupted_assembly_keeps_active_graph_and_reuses_completed_downloads(shared):
  first = update("us_state.IA")
  package = catalog.plan("us_state.IA,us_state.IL")[0][0]
  def interrupt():
    raise C.RoutingError("interrupted")
  with pytest.raises(C.RoutingError, match="interrupted"):
    downloads.install(package, pack_gate=interrupt)
  assert B.active().generation == first.generation and verified.read(first)
  assert not shared.mounts
  shared.requested.clear()
  update("us_state.IA,us_state.IL")
  assert all(not url.endswith((".squashfs", ".tiles.json")) for url in shared.requested)


def test_failed_staged_mount_validation_releases_its_mount(shared, monkeypatch):
  incoming = downloads.prepare(shared.data["dataset"]["parts"][0])
  def reject(_):
    raise C.RoutingError("data_incompatible")
  monkeypatch.setattr(images, "require_mounted", reject)
  with pytest.raises(C.RoutingError, match="data_incompatible"), images.staged_reader(incoming):
    pytest.fail("invalid mount was exposed to the assembler")
  assert not shared.mounts and not images.mount_path(incoming).exists()


def test_cancelling_cached_pack_verification_keeps_its_valid_receipt(shared, monkeypatch):
  part = shared.data["dataset"]["parts"][0]
  incoming = downloads.prepare(part)
  def cancelled(*_):
    raise C.RoutingError("cancelled")
  monkeypatch.setattr(B, "verify", cancelled)
  with pytest.raises(C.RoutingError, match="cancelled"):
    downloads.prepare(part)
  assert verified.read(incoming) and images.source(incoming).exists()


def test_new_dataset_version_never_reuses_old_graph_ids(shared):
  old = update("us_state.IA")
  newer = json.loads(json.dumps(shared.data))
  newer["dataset"]["sha256"] = "f" * 64
  package = catalog.plan("us_state.IA", newer)[0][0]
  assert package["bytes"] > 0 and len(package["missing"]) == len(package["parts"])
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    downloads.install(package)
  assert B.active().generation == old.generation


def test_single_selection_matches_incremental_tar_regardless_of_order(shared, monkeypatch, tmp_path):
  both = update("us_state.IA,us_state.IL")
  canonical = images.source(both).read_bytes()
  other = tmp_path / "other-store"
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(other))
  update("us_state.IL")
  incremental = update("us_state.IA,us_state.IL")
  assert images.source(incremental).read_bytes() == canonical


def test_partition_retains_every_hierarchy_level_and_fringe_tile_once(shared):
  bundle = update("us_state.IA,us_state.IL")
  rows = T.read_index(bundle.folder / "tiles.json", bundle.manifest["dataset"]["sha256"])
  assert {row["path"][0] for row in rows} == {"0", "1", "2"}
  original = {path.relative_to(shared.graph).as_posix(): B.digest(path) for path in shared.graph.rglob("*.gph")}
  assert {row["path"]: row["sha256"] for row in rows} == original
  assert len(rows) == len(original)


def test_missing_region_coverage_fails_before_creating_any_pack(shared, tmp_path):
  first, absent = tmp_path / "ia.poly", tmp_path / "wi.poly"
  first.write_text("[-96, 40, -91, 44]")
  absent.write_text("[-90, 46, -89, 48]")
  output = tmp_path / "invalid-publication"
  with pytest.raises(C.RoutingError, match="coverage_unavailable"):
    states.partition(shared.graph, output, "missing-test", {
      "us_state.IA": {"title": "Iowa", "polygon": first}, "us_state.WI": {"title": "Wisconsin", "polygon": absent}},
      {"source": {"url": "synthetic"}, "attribution": "Synthetic", "built_at": "2026-11-04"}, "https://test.example/data")
  assert not output.exists()


def test_selection_pointer_hides_retired_state_even_while_reader_blocks_cleanup(shared):
  both = update("us_state.IA,us_state.IL")
  with images.reader(both):
    remaining = update("us_state.IL")
    assert both.folder.exists() and B.active().id == remaining.id
    assert catalog.ready_regions() == {"us_state.IL"}
    assert [b.id for b in B.routing_bundles()] == [remaining.id]
  datasets.cleanup()
  assert not both.folder.exists()


def test_corrupt_selection_pointer_does_not_resurrect_a_retired_state(shared):
  both = update("us_state.IA,us_state.IL")
  with images.reader(both):
    current = update("us_state.IL")
    (C.root() / "active.json").write_text("interrupted or damaged pointer")
    assert not B.routing_bundles() and not catalog.ready_regions()
    with pytest.raises(C.RoutingError, match="superseded"):
      B.selected({"bundle": both.id})
    with pytest.raises(C.RoutingError, match="superseded"):
      B.selected({"bundle": current.id})


def test_schema_checks_reject_missing_parts_and_mixed_dataset_metadata(shared):
  bad = json.loads(json.dumps(shared.data))
  bad["dataset"]["regions"]["us_state.IA"]["parts"].append("not-published")
  with pytest.raises(C.RoutingError, match="catalog_unavailable"):
    catalog.validate(bad)
  bundle = update("us_state.IA")
  rows = T.read_index(bundle.folder / "tiles.json", bundle.manifest["dataset"]["sha256"])
  value = {"schema": 1, "dataset": "0" * 64, "tiles": rows}
  C.atomic_json(bundle.folder / "tiles.json", value)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    T.read_index(bundle.folder / "tiles.json", bundle.manifest["dataset"]["sha256"])


def test_no_space_for_replacement_preserves_current_selection(shared, monkeypatch):
  first = update("us_state.IA")
  shared.requested.clear()
  original = shutil.disk_usage
  monkeypatch.setattr(datasets.shutil, "disk_usage", lambda path: SimpleNamespace(free=256 * 1024**2 + 1)
                      if path == C.root() else original(path))
  with pytest.raises(C.RoutingError, match="no_space"):
    update("us_state.IL")
  assert B.active().generation == first.generation
  assert not shared.requested  # reject before transferring any new state data


def test_deselect_all_clears_routes_without_download_or_compression(shared, monkeypatch):
  current = update("us_state.IA,us_state.IL")
  partial = C.root() / "downloads/partial-state/tiles.squashfs"
  partial.parent.mkdir(parents=True)
  partial.write_bytes(b"unfinished state download")
  shared.requested.clear()
  monkeypatch.setattr(images, "pack_stream", lambda *_: pytest.fail("clearing states recompressed data"))
  assert update("") is None
  assert not shared.requested and not current.folder.exists() and not shared.mounts
  assert B.routing_bundles() == [] and catalog.ready_regions() == set()
  assert B.capability()["status"] == "data_missing"
  assert not (C.root() / "downloads").exists()


def test_damaged_cached_pack_is_refetched_before_reuse(shared):
  update("us_state.IA")
  package = catalog.plan("us_state.IA,us_state.IL")[0][0]
  def interrupt():
    raise C.RoutingError("interrupted")
  with pytest.raises(C.RoutingError, match="interrupted"):
    downloads.install(package, pack_gate=interrupt)
  path = next((C.root() / "downloads").glob("*/ready/tiles.squashfs"))
  path.chmod(0o600)
  payload = path.read_bytes()
  path.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
  shared.requested.clear()
  update("us_state.IA,us_state.IL")
  assert sum(url.endswith(".squashfs") for url in shared.requested) == 1
  assert catalog.ready_regions() == {"us_state.IA", "us_state.IL"}


def test_old_explicit_request_is_superseded_after_deselection(shared):
  both = update("us_state.IA,us_state.IL")
  with images.reader(both):
    update("us_state.IL")
    with pytest.raises(C.RoutingError, match="superseded"):
      B.selected({"bundle": both.id})


def test_shared_manager_applies_empty_update_and_does_not_prepare_runtime(shared):
  from openpilot.starpilot.tandem.routing import maps
  update("us_state.IA")
  shared.requested.clear()
  manager = maps.Manager(SimpleNamespace(), prepare=lambda **_: pytest.fail("clearing maps installed a runtime"))
  maps.request("")
  manager.run(maps.read("map-request.json"))
  assert maps.read()["phase"] == "ready" and B.capability()["status"] == "data_missing"
  assert not shared.requested


def test_restart_reclaims_only_abandoned_assembly_output(shared):
  update("us_state.IA")
  abandoned = C.root() / "downloads/assembled/tmp-abandoned/ready"
  abandoned.mkdir(parents=True)
  (abandoned / "tiles.squashfs").write_bytes(b"interrupted image")
  update("us_state.IL")
  assert not abandoned.parent.exists()


def test_finished_selection_removes_cached_data_for_unchecked_states(shared):
  update("us_state.IA")
  partial = C.root() / "downloads/unchecked-state/partial.squashfs"
  partial.parent.mkdir(parents=True)
  partial.write_bytes(b"unfinished, no longer wanted")
  shared.requested.clear()
  update("us_state.IA")
  assert not shared.requested and not (C.root() / "downloads").exists()


def test_empty_selection_and_global_removal_reclaim_damaged_graphs(shared):
  from openpilot.starpilot.tandem.routing import maps
  damaged = update("us_state.IA")
  images.source(damaged).chmod(0o600)
  images.source(damaged).write_bytes(b"damaged image")
  assert not B.installed()
  assert update("") is None and not damaged.folder.exists()
  damaged = update("us_state.IL")
  with images.reader(damaged):
    (damaged.folder / "manifest.json").write_text("damaged manifest")
    with pytest.raises(C.RoutingError, match="busy"):
      maps.remove_all()
    assert damaged.folder.exists()
  maps.remove_all()
  assert not damaged.folder.exists() and not shared.mounts


def test_drive_transition_aborts_assembly_and_resumes_without_refetching_packs(shared, monkeypatch):
  from openpilot.starpilot.tandem.routing import maps
  original = update("us_state.IA")
  parked = [True]
  manager = maps.Manager(None, allowed=lambda: parked[0], prepare=lambda **_: None)
  pack = images.pack_stream
  def start_drive(chunks, length, output, gate):
    parked[0] = False
    return pack(chunks, length, output, gate)
  monkeypatch.setattr(images, "pack_stream", start_drive)
  maps.request("us_state.IA,us_state.IL")
  pending = maps.read("map-request.json")
  manager.run(pending)
  assert maps.read()["paused"] and maps.read()["phase"] == "install"
  assert B.active().generation == original.generation and not shared.mounts
  parked[0] = True
  monkeypatch.setattr(images, "pack_stream", pack)
  shared.requested.clear()
  manager.run(pending)
  assert maps.read()["phase"] == "ready" and catalog.ready_regions() == {"us_state.IA", "us_state.IL"}
  assert all(not url.endswith((".squashfs", ".tiles.json")) for url in shared.requested)
