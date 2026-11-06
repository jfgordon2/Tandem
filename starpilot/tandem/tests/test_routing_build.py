"""Connected multi-extract graph builds preserve inputs and declared coverage."""
import hashlib
import json
import struct
import tarfile

import pytest

from openpilot.starpilot.tandem.routing import config as C
from openpilot.starpilot.tandem.routing.tools import build as B


def test_multiple_states_feed_one_native_build_and_keep_provenance(monkeypatch, tmp_path):
  first, second = tmp_path / "iowa.pbf", tmp_path / "illinois.pbf"
  first.write_bytes(b"Iowa source")
  second.write_bytes(b"Illinois source")
  output, commands = tmp_path / "bundle", []
  monkeypatch.setattr(B.subprocess, "check_output", lambda command, **_: '{"mjolnir": {}}' if "get_config" in command[-2] else "/native/builder")
  def run(command, **kwargs):
    commands.append(command)
    tile = output / "tiles/2/000/001.gph"
    tile.parent.mkdir(parents=True)
    tile.write_bytes(b"connected test graph")
  monkeypatch.setattr(B.subprocess, "run", run)
  B.build(first, output, "ia-il-test", "Iowa and Illinois", [-97, 36, -87, 44], "https://example.test/ia.pbf",
          additional_sources=((second, "https://example.test/il.pbf"),), regions=("us_state.IA", "us_state.IL"), storage="zstd")
  assert len(commands) == 1 and commands[0][-2:] == [str(first), str(second)]
  manifest = json.loads((output / "manifest.json").read_text())
  config = json.loads((output / "build-config.json").read_text())["mjolnir"]
  assert config["include_driving"] and not config["include_pedestrian"] and not config["include_bicycle"]
  assert all(config[name] for name in ("include_driveways", "hierarchy", "shortcuts"))
  assert not any(config[name] for name in ("keep_osm_node_ids", "keep_all_osm_node_ids", "include_platforms",
                                         "import_bike_share_stations", "include_construction", "pedestrian_areas"))
  assert manifest["schema"] == 2 and manifest["profile"] == "driving"
  record = manifest["files"]["tiles.tar"]
  B.transport.expand(output / record["download"]["name"], output / "roundtrip.tar", record)
  assert (output / "roundtrip.tar").read_bytes() == (output / "tiles.tar").read_bytes()
  assert manifest["regions"] == ["us_state.IA", "us_state.IL"]
  assert manifest["source"] == manifest["sources"][0]
  assert [p["sha256"] for p in manifest["sources"]] == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)]
  assert manifest["sources"][1]["url"] == "https://example.test/il.pbf"
  with tarfile.open(output / "tiles.tar") as archive:
    assert archive.getmembers()[0].name == "index.bin"
    offset, tile, size = struct.unpack("<QII", archive.extractfile("index.bin").read())
    entry = archive.getmember("2/000/001.gph")
    assert offset == entry.offset_data and tile == 10 and size == entry.size
  with pytest.raises(C.RoutingError, match="bundle_exists"):
    B.build(first, output, "ia-il-test", "Existing", [-97, 36, -87, 44], "https://example.test/ia.pbf")


def test_missing_secondary_source_does_not_start_a_partial_build(tmp_path):
  first = tmp_path / "iowa.pbf"
  first.write_bytes(b"Iowa source")
  output = tmp_path / "bundle"
  with pytest.raises(C.RoutingError, match="data_missing"):
    B.build(first, output, "missing-test", "Missing", [-97, 36, -87, 44], "https://example.test/ia.pbf",
            additional_sources=((tmp_path / "missing.pbf", "https://example.test/missing.pbf"),))
  assert not output.exists()


def test_default_package_stores_only_indexed_squashfs_image(monkeypatch, tmp_path):
  source = tmp_path / "state.pbf"
  source.write_bytes(b"OSM source")
  output = tmp_path / "bundle"
  monkeypatch.setattr(B.subprocess, "check_output", lambda command, **_: '{"mjolnir": {}}' if "get_config" in command[-2] else "/native/builder")
  def run(*_, **__):
    tile = output / "tiles/2/000/001.gph"
    tile.parent.mkdir(parents=True)
    tile.write_bytes(b"native graph fixture")
  monkeypatch.setattr(B.subprocess, "run", run)
  monkeypatch.setattr(B.images, "pack", lambda graph, image: image.write_bytes(b"packed:" + graph.read_bytes()))
  def verify_graph(folder, manifest, gate):
    graph = manifest["graph"]
    raw = (folder / graph["file"]).read_bytes()[7:]
    assert hashlib.sha256(raw).hexdigest() == graph["sha256"] and len(raw) == graph["bytes"]
  monkeypatch.setattr(B.images, "verify_graph", verify_graph)
  B.build(source, output, "state-image", "State", [-97, 40, -90, 44], "https://example.test/source.pbf")
  manifest = json.loads((output / "manifest.json").read_text())
  assert manifest["schema"] == 3 and set(manifest["files"]) == {"tiles.squashfs"}
  assert manifest["graph"]["path"] == "tiles.tar"
  with tarfile.open(output / "tiles.tar") as graph:
    assert graph.getmembers()[0].name == "index.bin"
