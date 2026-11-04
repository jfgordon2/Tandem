"""Image acceptance streams data; runtime mounts obey receipts and reader leases."""
import hashlib
import io
import shutil
import sys
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem.routing import bundles, config as C, downloads, images, verified


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "store"))
  monkeypatch.setenv("TANDEM_PREFS_DIR", str(tmp_path / "prefs"))
  monkeypatch.setenv("TANDEM_ROUTING_MOUNT_DIR", str(tmp_path / "mounts"))


@pytest.fixture
def decoder(monkeypatch, tmp_path):
  # Exercise the real bounded pipe protocol without needing kernel mounts or
  # installed packaging tools in unit-test jobs. Real images run in native QA.
  script, log = tmp_path / "unsquashfs", tmp_path / "decoder.calls"
  script.write_text(f"#!{sys.executable}\n" + f'''import pathlib,sys
if '-version' in sys.argv:
  print('unsquashfs version 4.6.1')
else:
  assert sys.argv[sys.argv.index('-processors')+1]=='1'
  assert sys.argv[sys.argv.index('-data-queue')+1]=='4'
  assert sys.argv[sys.argv.index('-frag-queue')+1]=='1'
  image=pathlib.Path(sys.argv[-2])
  data=image.read_bytes()
  assert data.startswith(b'fixture:')
  with pathlib.Path({str(log)!r}).open('a') as out: out.write('decode\\n')
  sys.stdout.buffer.write(data[8:])
''')
  script.chmod(0o700)
  original = shutil.which
  monkeypatch.setattr(images.shutil, "which", lambda name: str(script) if name == "unsquashfs" else original(name))
  return SimpleNamespace(script=script, log=log)


def make_image(path, identity="image-test"):
  path.mkdir(parents=True)
  logical = b"mapped road graph, restrictions, signs and lane data\n" * 100
  payload = b"fixture:" + logical
  (path / "tiles.squashfs").write_bytes(payload)
  manifest = {"schema": 3, "id": identity, "runtime_version": C.VERSION,
    "source": {"url": "synthetic"}, "attribution": "Synthetic test data", "bounds": [-97, 40, -90, 44],
    "graph": {"format": "squashfs", "file": "tiles.squashfs", "path": "tiles.tar", "bytes": len(logical),
              "sha256": hashlib.sha256(logical).hexdigest()},
    "files": {"tiles.squashfs": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}}}
  C.atomic_json(path / "manifest.json", manifest)
  return bundles.load(path), logical


def fake_kernel(monkeypatch, bundle, logical):
  rows, calls = {}, []
  monkeypatch.setattr(images, "sys", SimpleNamespace(platform="linux"))
  monkeypatch.setattr(images, "_mounts", lambda: rows)
  monkeypatch.setattr(images, "_backing", lambda _: images.source(bundle))
  def command(args, **_):
    calls.append(args)
    point = images.mount_path(bundle)
    if args[0] == "mount":
      assert args[-2] == str(images.source(bundle).resolve())
      assert "ro,nodev,nosuid,noexec,loop" in args
      (point / "tiles.tar").write_bytes(logical)
      rows[point] = {"type": "squashfs", "options": {"ro", "nodev", "nosuid", "noexec"}, "device": "7:0"}
    else:
      assert args == ["umount", str(point)]
      rows.pop(point)
      (point / "tiles.tar").unlink()
  monkeypatch.setattr(images, "_command", command)
  return rows, calls


def test_image_installs_without_expanded_copy_and_reuses_receipt(decoder, monkeypatch):
  source, _ = make_image(C.root() / "downloads" / "test" / "ready")
  bundle = bundles.install(source.folder, consume=True)
  assert {p.name for p in bundle.folder.iterdir()} == {"tiles.squashfs", "manifest.json", verified.RECEIPT}
  assert decoder.log.read_text().splitlines() == ["decode"]
  assert not (bundle.folder / "tiles.tar").exists()
  assert not images.source(bundle).stat().st_mode & 0o222
  monkeypatch.setattr(images, "verify_graph", lambda *_: pytest.fail("activation or periodic check decoded the graph again"))
  bundles.activate(bundle.id)
  bundles.verify(bundle.folder)
  verified.require(bundle)


def test_lazy_mount_is_reused_and_kept_while_reader_holds_lease(decoder, tmp_path, monkeypatch):
  source, logical = make_image(tmp_path / "source")
  bundle = bundles.install(source.folder)
  rows, calls = fake_kernel(monkeypatch, bundle, logical)
  with images.reader(bundle):
    assert images.require_mounted(bundle).read_bytes() == logical
    images.ensure(bundle)
    images.release_unused()
    assert len(calls) == 1 and rows
    with pytest.raises(C.RoutingError, match="busy"):
      bundles.remove(bundle.id)
  images.release_unused()
  assert not rows and [c[0] for c in calls] == ["mount", "umount"]


def test_global_removal_unmounts_before_deleting_image(decoder, tmp_path, monkeypatch):
  from openpilot.starpilot.tandem.routing import maps
  source, logical = make_image(tmp_path / "source")
  bundle = bundles.install(source.folder)
  rows, calls = fake_kernel(monkeypatch, bundle, logical)
  images.ensure(bundle)
  maps.remove_all()
  assert not rows and calls[-1][0] == "umount" and not bundle.folder.exists()


def test_corrupt_manifest_can_still_be_removed_and_unmounted(decoder, tmp_path, monkeypatch):
  source, logical = make_image(tmp_path / "source")
  bundle = bundles.install(source.folder)
  rows, _ = fake_kernel(monkeypatch, bundle, logical)
  images.ensure(bundle)
  (bundle.folder / "manifest.json").write_text("broken")
  bundles.remove(bundle.id)
  assert not rows and not bundle.folder.exists()


@pytest.mark.parametrize("damage", ["writable", "wrong_fs", "missing_flag", "wrong_source", "wrong_size"])
def test_native_reader_rejects_unexpected_mount_state(decoder, tmp_path, monkeypatch, damage):
  source, logical = make_image(tmp_path / "source")
  bundle = bundles.install(source.folder)
  rows, _ = fake_kernel(monkeypatch, bundle, logical)
  images.ensure(bundle)
  row = rows[images.mount_path(bundle)]
  if damage == "writable":
    row["options"].discard("ro")
  elif damage == "wrong_fs":
    row["type"] = "ext4"
  elif damage == "missing_flag":
    row["options"].discard("noexec")
  elif damage == "wrong_source":
    monkeypatch.setattr(images, "_backing", lambda _: tmp_path / "different-image")
  else:
    images.graph_path(bundle).write_bytes(b"truncated")
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    images.require_mounted(bundle)


def test_image_download_verifies_and_installs_only_physical_bytes(decoder, tmp_path, monkeypatch):
  source, _ = make_image(tmp_path / "source")
  raw = (source.folder / "manifest.json").read_bytes()
  payload = images.source(source).read_bytes()
  class Response(io.BytesIO):
    status = 200
    headers = {}
  def open_(request, **_):
    url = request if isinstance(request, str) else request.full_url
    return Response(raw if url.endswith("manifest.json") else payload)
  monkeypatch.setattr(downloads.urllib.request, "build_opener", lambda *_: SimpleNamespace(open=open_))
  entry = {"id": source.id, "manifest": "https://example.test/manifest.json", "sha256": hashlib.sha256(raw).hexdigest(),
           "bytes": len(payload)}
  bundle = downloads.install(entry)
  assert bundles.active().id == bundle.id and verified.read(bundle)
  assert images.source(bundle).stat().st_size == len(payload)
  assert not (bundle.folder / "tiles.tar").exists()


def test_damaged_logical_graph_is_rejected_before_receipt(decoder, tmp_path):
  source, _ = make_image(tmp_path / "source")
  manifest = source.manifest
  manifest["graph"]["sha256"] = "0" * 64
  C.atomic_json(source.folder / "manifest.json", manifest)
  with pytest.raises(C.RoutingError, match="data_incompatible"):
    bundles.verify(source.folder)
  assert not (source.folder / verified.RECEIPT).exists()


def test_mount_namespaces_are_separate_for_isolated_data_roots(monkeypatch, tmp_path):
  monkeypatch.delenv("TANDEM_ROUTING_MOUNT_DIR")
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "one"))
  first = images.mount_root()
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path / "two"))
  assert images.mount_root() != first


def test_truncated_image_can_be_repaired_without_changing_immutable_manifest(decoder, tmp_path, monkeypatch):
  monkeypatch.setattr(C, "runtime_ready", lambda: True)
  source, logical = make_image(tmp_path / "source")
  bundle = bundles.install(source.folder)
  images.source(bundle).chmod(0o600)
  images.source(bundle).write_bytes(b"truncated")
  assert bundles.capability()["status"] == "data_missing"
  repaired = bundles.install(source.folder)
  verified.require(repaired)
  assert repaired.generation == bundle.generation
  assert images.source(repaired).read_bytes() == b"fixture:" + logical


def test_streamed_compressor_receives_one_tar_without_expanded_disk_file(tmp_path, monkeypatch):
  script = tmp_path / "mksquashfs"
  script.write_text(f"#!{sys.executable}\n" + '''import pathlib,sys,tarfile
assert sys.argv[1]=='-' and '-tar' in sys.argv
assert sys.argv[sys.argv.index('-processors')+1]=='1'
assert sys.argv[sys.argv.index('-mem')+1]=='64M'
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
  item=next(iter(archive))
  assert item.name=='tiles.tar' and item.mode==0o444
  with pathlib.Path(sys.argv[2]).open('wb') as target:
    source=archive.extractfile(item)
    while block:=source.read(65536): target.write(block)
  assert archive.next() is None
''')
  script.chmod(0o700)
  monkeypatch.setattr(images.shutil, "which", lambda _: str(script))
  payload = b"native graph tile" * 65536
  output = tmp_path / "tiles.squashfs"
  result = images.pack_stream((payload[n:n+65536] for n in range(0, len(payload), 65536)), len(payload), output)
  assert output.read_bytes() == payload
  assert result == {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
  assert not (tmp_path / "tiles.tar").exists()


def test_cancelled_stream_terminates_compressor_even_when_its_pipe_is_full(tmp_path, monkeypatch):
  script = tmp_path / "mksquashfs"
  script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
  script.chmod(0o700)
  monkeypatch.setattr(images.shutil, "which", lambda _: str(script))
  processes, calls = [], 0
  popen = images.subprocess.Popen
  def start(*args, **kwargs):
    process = popen(*args, **kwargs)
    processes.append(process)
    return process
  monkeypatch.setattr(images.subprocess, "Popen", start)
  def gate():
    nonlocal calls
    calls += 1
    if calls == 4:
      raise C.RoutingError("interrupted")
  closed = []
  def source():
    try:
      yield bytes(2 * 1024**2)
    finally:
      closed.append(True)
  producer = source()
  with pytest.raises(C.RoutingError, match="interrupted"):
    images.pack_stream(producer, 2 * 1024**2, tmp_path / "tiles.squashfs", gate)
  assert len(processes) == 1 and processes[0].poll() is not None
  assert closed == [True]  # close a mounted input before its reader lease unwinds
