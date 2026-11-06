"""Compressed downloads retain graph integrity, cancellation and atomic activation."""
import copy
import hashlib
import io
import json
import sys
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import archive, bundles, config as C, downloads, verified
from openpilot.starpilot.tandem.tests.test_routing import make_bundle


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "routing"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))


def package(tmp_path, compressed=True):
  source = make_bundle(tmp_path / "source", "smaller-graph", b"mapped road and lane data\n" * 40000)
  manifest = source.manifest
  payload = (source.folder / "tiles.tar").read_bytes()
  asset = "tiles.tar"
  if compressed:
    asset += ".zst"
    transport = archive.compress(source.folder / "tiles.tar", source.folder / asset)
    manifest["schema"] = 2
    manifest["files"]["tiles.tar"]["download"] = transport
    payload = (source.folder / asset).read_bytes()
  raw = json.dumps(manifest).encode()
  catalog = {"id": manifest["id"], "manifest": "https://example.test/maps/manifest.json",
             "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(payload)}
  return catalog, raw, asset, payload, manifest


def serve(monkeypatch, raw, asset, payload):
  calls = []
  class Response(io.BytesIO):
    status = 200
    headers = {}
  def open_(request, **_):
    url = request if isinstance(request, str) else request.full_url
    calls.append(request)
    if url.endswith("manifest.json"):
      return Response(raw)
    assert url == "https://example.test/maps/" + asset
    start = int(request.get_header("Range")[6:-1]) if request.has_header("Range") else 0
    result = Response(payload[start:])
    if start:
      result.status = 206
      result.headers = {"Content-Range": f"bytes {start}-{len(payload)-1}/{len(payload)}"}
    return result
  monkeypatch.setattr(downloads.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=open_))
  return calls


@pytest.mark.parametrize("compressed", [False, True])
def test_download_installs_only_verified_expanded_graph_and_preserves_plain_packages(monkeypatch, tmp_path, compressed):
  entry, raw, asset, payload, manifest = package(tmp_path, compressed)
  calls = serve(monkeypatch, raw, asset, payload)
  folder = C.root() / "downloads" / entry["sha256"]
  folder.mkdir(parents=True)
  (folder / asset).write_bytes(payload[:9])
  progress, phases = [], []
  result = downloads.install(entry, progress=lambda n, total: progress.append((n, total)), installing=lambda: phases.append("install"))
  assert result.id == bundles.active().id == entry["id"]
  assert bundles.load(result.folder, verify=True).manifest == manifest
  assert {p.name for p in result.folder.iterdir()} == {"tiles.tar", "manifest.json", verified.RECEIPT}
  verified.require(result)
  assert not folder.exists() and phases == ["install"]
  assert progress[-1] == (len(payload), len(payload))
  assert calls[1].get_header("Range") == "bytes=9-"


@pytest.mark.parametrize("damage", ["transport_hash", "expanded_hash", "expanded_length", "truncated_footer", "trailing_data", "two_frames", "frame_checksum"])
def test_corrupt_compressed_package_keeps_previous_active_graph(monkeypatch, tmp_path, damage):
  previous = bundles.install(make_bundle(tmp_path / "previous", "previous").folder)
  bundles.activate(previous.id)
  entry, raw, asset, payload, manifest = package(tmp_path)
  record = manifest["files"]["tiles.tar"]
  if damage == "transport_hash":
    record["download"]["sha256"] = "0" * 64
  elif damage == "expanded_hash":
    record["sha256"] = "0" * 64
  elif damage == "expanded_length":
    record["bytes"] -= 1
  else:
    payload = {"truncated_footer": payload[:-1], "trailing_data": payload + b"x",
               "two_frames": payload + payload, "frame_checksum": payload[:-1] + bytes([payload[-1] ^ 1])}[damage]
    record["download"].update(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
  raw = json.dumps(manifest).encode()
  entry.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(payload))
  serve(monkeypatch, raw, asset, payload)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    downloads.install(entry)
  assert bundles.active().generation == previous.generation
  assert not (C.root() / "bundles" / entry["id"]).exists()
  assert not list((C.root() / "downloads").rglob("*.partial"))


def test_expansion_cancel_retains_archive_and_restarts_without_partial_output(tmp_path):
  _, _, asset, _, manifest = package(tmp_path)
  source, target = tmp_path / "source" / asset, tmp_path / "expanded.tar"
  target.write_bytes(b"previous output")
  calls = 0
  def gate():
    nonlocal calls
    calls += 1
    if calls == 4:
      raise C.RoutingError("cancelled")
  with pytest.raises(C.RoutingError, match="cancelled"):
    archive.expand(source, target, manifest["files"]["tiles.tar"], gate)
  assert source.exists() and target.read_bytes() == b"previous output"
  assert not target.with_name(target.name + ".partial").exists()
  archive.expand(source, target, manifest["files"]["tiles.tar"])
  assert bundles.digest(target) == manifest["files"]["tiles.tar"]["sha256"]


def test_window_limit_is_enforced_before_expanding(monkeypatch, tmp_path):
  _, _, asset, _, manifest = package(tmp_path)
  monkeypatch.setattr(archive, "WINDOW", 1024)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    archive.expand(tmp_path / "source" / asset, tmp_path / "expanded.tar", manifest["files"]["tiles.tar"])
  assert not (tmp_path / "expanded.tar").exists()


def test_free_space_includes_expanded_graph_and_reclaims_interrupted_expansion(monkeypatch, tmp_path):
  entry, raw, asset, payload, manifest = package(tmp_path)
  calls = serve(monkeypatch, raw, asset, payload)
  ready = C.root() / "downloads" / entry["sha256"] / "ready"
  ready.mkdir(parents=True)
  (ready / "tiles.tar.partial").write_bytes(b"interrupted")
  required = len(payload) + manifest["files"]["tiles.tar"]["bytes"] + 256 * 1024**2
  monkeypatch.setattr(downloads.shutil, "disk_usage", lambda _: SimpleNamespace(free=required - 1))
  with pytest.raises(C.RoutingError, match="no_space"):
    downloads.install(entry)
  assert len(calls) == 1 and not (ready / "tiles.tar.partial").exists()


@pytest.mark.parametrize("change", [
  {"encoding": "gzip"}, {"name": "../outside"}, {"name": "tiles.tar"}, {"bytes": True}, {"sha256": "not a hash"},
])
def test_transport_metadata_is_validated_before_download(tmp_path, change):
  *_, manifest = package(tmp_path)
  value = copy.deepcopy(manifest)
  value["files"]["tiles.tar"]["download"].update(change)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    bundles.validate_manifest(value)


def test_consuming_install_cannot_move_a_maintainer_source_bundle(tmp_path):
  source = make_bundle(tmp_path / "source")
  with pytest.raises(C.RoutingError, match="invalid_request"):
    bundles.install(source.folder, consume=True)
  assert source.folder.exists() and not bundles.installed()


def test_cli_compressed_download_still_requires_separate_activation(monkeypatch, tmp_path):
  from openpilot.starpilot.tandem.routing.tools import manage
  entry, raw, asset, payload, _ = package(tmp_path)
  serve(monkeypatch, raw, asset, payload)
  result = manage.download(entry["manifest"])
  assert bundles.load(result.folder, verify=True).id == entry["id"]
  with pytest.raises(C.RoutingError, match="data_missing"):
    bundles.active()


@pytest.mark.parametrize("cancelled", [False, True])
def test_agnos_command_decoder_needs_no_python_module(monkeypatch, tmp_path, cancelled):
  _, _, asset, _, manifest = package(tmp_path)
  monkeypatch.setitem(sys.modules, "zstandard", None)
  target = tmp_path / "decoded.tar"
  calls = 0
  def gate():
    nonlocal calls
    calls += 1
    if cancelled and calls == 4:
      raise C.RoutingError("cancelled")
  if cancelled:
    with pytest.raises(C.RoutingError, match="cancelled"):
      archive.expand(tmp_path / "source" / asset, target, manifest["files"]["tiles.tar"], gate)
    assert not target.exists() and not list(tmp_path.glob("*.partial"))
  else:
    archive.expand(tmp_path / "source" / asset, target, manifest["files"]["tiles.tar"], gate)
    assert bundles.digest(target) == manifest["files"]["tiles.tar"]["sha256"]


@pytest.mark.parametrize("size", [1, 255, 256, 65791, 65792, 8 * 1024**2 + 1])
def test_frame_content_size_encodings_and_stream_window(tmp_path, size):
  source, compressed, target = tmp_path / "tiles.tar", tmp_path / "tiles.tar.zst", tmp_path / "result.tar"
  source.write_bytes((b"mapped data " * (size // 12 + 1))[:size])
  archive.compress(source, compressed)
  archive.expand(compressed, target, {"bytes": size, "sha256": bundles.digest(source)})
  assert bundles.digest(target) == bundles.digest(source)


def test_cancel_during_final_graph_validation_does_not_install(tmp_path):
  source = make_bundle(tmp_path / "source", value=b"data" * 1024**2)
  calls = 0
  def gate():
    nonlocal calls
    calls += 1
    if calls == 3:
      raise C.RoutingError("cancelled")
  with pytest.raises(C.RoutingError, match="cancelled"):
    bundles.install(source.folder, gate=gate)
  assert not bundles.installed() and source.folder.exists()
