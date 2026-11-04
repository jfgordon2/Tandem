"""Read-only SquashFS graph images. Mounts stay outside physical storage accounting."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import fcntl
import hashlib
import os
from pathlib import Path
import selectors
import re
import shutil
import subprocess
import sys
import tempfile
import time

from openpilot.starpilot.tandem.routing import config as C, verified


def is_image(bundle) -> bool:
  return bundle.manifest["schema"] == 3


def mount_root() -> Path:
  identity = hashlib.sha256(str(C.root().resolve()).encode()).hexdigest()[:16]
  base = Path("/dev/shm") if sys.platform == "linux" else Path(tempfile.gettempdir())
  default = base / f"tandem-routing-mounts-{os.getuid()}" / identity
  return Path(os.getenv("TANDEM_ROUTING_MOUNT_DIR", str(default)))


def mount_path(bundle) -> Path:
  return mount_root() / f"{bundle.id}-{bundle.generation}"


def source(bundle) -> Path:
  return bundle.folder / bundle.manifest["graph"]["file"]


def graph_path(bundle) -> Path:
  return mount_path(bundle) / "tiles.tar" if is_image(bundle) else bundle.folder / "tiles.tar"


def _unescape(value):
  for escaped, char in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
    value = value.replace(escaped, char)
  return value


def _mounts() -> dict:
  result = {}
  if sys.platform != "linux":
    return result
  for row in Path("/proc/self/mountinfo").read_text().splitlines():
    left, right = row.split(" - ", 1)
    fields, details = left.split(), right.split()
    result[Path(_unescape(fields[4]))] = {"device": fields[2], "options": set(fields[5].split(",")), "type": details[0]}
  return result


def _command(arguments, timeout=15):
  prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
  try:
    subprocess.run([*prefix, *arguments], check=True, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  except (OSError, subprocess.SubprocessError):
    raise C.RoutingError("data_incompatible") from None


def _backing(row):
  return Path(_unescape((Path("/sys/dev/block") / row["device"] / "loop/backing_file").read_text().strip()))


def require_mounted(bundle) -> Path:
  if not is_image(bundle):
    return graph_path(bundle)
  point = mount_path(bundle)
  row = _mounts().get(point)
  if (point.is_symlink() or not row or row["type"] != "squashfs"
      or not {"ro", "nosuid", "nodev", "noexec"} <= row["options"]):
    raise C.RoutingError("data_incompatible")
  try:
    backing = _backing(row)
    if backing.resolve() != source(bundle).resolve():
      raise C.RoutingError("data_incompatible")
    graph = graph_path(bundle)
    if graph.is_symlink() or graph.stat().st_size != bundle.manifest["graph"]["bytes"]:
      raise C.RoutingError("data_incompatible")
    return graph
  except OSError:
    raise C.RoutingError("data_incompatible") from None


def ensure(bundle) -> Path:
  verified.require(bundle)
  if not is_image(bundle):
    return graph_path(bundle)
  if sys.platform != "linux":
    raise C.RoutingError("data_incompatible")
  point = mount_path(bundle)
  if point in _mounts():
    return require_mounted(bundle)
  parent = mount_root().parent
  parent.mkdir(parents=True, exist_ok=True, mode=0o700)
  if parent.is_symlink() or parent.stat().st_uid not in (0, os.getuid()) or parent.stat().st_mode & 0o022:
    raise C.RoutingError("data_incompatible")
  mount_root().mkdir(exist_ok=True, mode=0o700)
  root_stat = mount_root().stat()
  if (mount_root().is_symlink() or root_stat.st_uid not in (0, os.getuid()) or root_stat.st_mode & 0o022
      or point.is_symlink()):
    raise C.RoutingError("data_incompatible")
  point.mkdir(exist_ok=True, mode=0o700)
  if any(point.iterdir()):
    raise C.RoutingError("data_incompatible")
  _command(["mount", "-t", "squashfs", "-o", "ro,nodev,nosuid,noexec,loop", str(source(bundle).resolve()), str(point.resolve())])
  return require_mounted(bundle)


def unmount(bundle) -> None:
  """Caller must hold the bundle's exclusive reader lease."""
  if not is_image(bundle):
    return
  _unmount_point(mount_path(bundle))


def _unmount_point(point):
  row = _mounts().get(point)
  if row:
    if row["type"] != "squashfs" or "ro" not in row["options"]:
      raise C.RoutingError("data_incompatible")
    _command(["umount", str(point)])
  if point.exists() and not point.is_symlink():
    point.rmdir()


def unmount_id(identity):
  """Caller holds this ID's exclusive lease, including for a corrupt manifest."""
  for point in mount_root().glob(f"{identity}-*"):
    if point.name.rpartition("-")[0] == identity and not point.is_symlink():
      _unmount_point(point)


def release_unused() -> None:
  """Also reclaim orphan mounts after a service restart. Never force an unmount."""
  from openpilot.starpilot.tandem.routing.bundles import ID
  for point in mount_root().glob("*"):
    identity, separator, generation = point.name.rpartition("-")
    if not separator or not ID.fullmatch(identity) or not re.fullmatch("[a-f0-9]{64}", generation) or point.is_symlink():
      continue
    folder = C.root() / "bundles" / identity
    try:
      if folder.is_dir() and not folder.is_symlink():
        with (folder / ".lease").open("a") as lease:
          fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
          _unmount_point(point)
      else:
        _unmount_point(point)
    except (OSError, C.RoutingError):
      pass  # a live reader or a busy kernel mount wins; retry after it closes


@contextmanager
def reader(bundle):
  with (bundle.folder / ".lease").open("a") as lease:
    try:
      fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
      raise C.RoutingError("busy") from None
    verified.require(bundle)
    ensure(bundle)
    yield


def verify_graph(folder: Path, manifest: dict, gate=lambda: None) -> None:
  """Stream the logical graph once at acceptance, with bounded decoder queues."""
  graph = manifest["graph"]
  tool = shutil.which("unsquashfs")
  if tool is None:
    raise C.RoutingError("data_incompatible")
  command = [tool, "-cat", "-no-progress", "-processors", "1", *_queue_options(tool),
             str((folder / graph["file"]).resolve()), "tiles.tar"]
  count, digest = 0, hashlib.sha256()
  with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
    try:
      deadline = time.monotonic() + 300
      with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
          paused = time.monotonic()
          gate()
          deadline += time.monotonic() - paused
          if time.monotonic() > deadline:
            raise C.RoutingError("timeout")
          if not selector.select(.2):
            continue
          block = os.read(process.stdout.fileno(), min(256 * 1024, graph["bytes"] - count + 1))
          if not block:
            break
          count += len(block)
          if count > graph["bytes"]:
            raise C.RoutingError("data_incompatible")
          digest.update(block)
      if process.wait(timeout=10) or count != graph["bytes"] or digest.hexdigest() != graph["sha256"]:
        raise C.RoutingError("data_incompatible")
    finally:
      if process.poll() is None:
        process.terminate()
        try:
          process.wait(timeout=3)
        except subprocess.TimeoutExpired:
          process.kill()
          process.wait()


@lru_cache(maxsize=2)
def _queue_options(tool):
  try:
    version = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=10)
  except (OSError, subprocess.SubprocessError):
    raise C.RoutingError("data_incompatible") from None
  match = re.search(r"version\s+(\d+)\.(\d+)", version.stdout + version.stderr)
  if match and tuple(map(int, match.groups())) >= (4, 7):
    return ["-mem", "8M"]
  return ["-data-queue", "4", "-frag-queue", "1"]


def pack(graph: Path, image: Path) -> None:
  tool = shutil.which("mksquashfs")
  if tool is None:
    raise C.RoutingError("data_incompatible")
  subprocess.run([tool, str(graph.resolve()), str(image.resolve()), "-comp", "gzip", "-Xcompression-level", "6",
                  "-b", "131072", "-processors", "2", "-mem", "64M", "-noappend", "-no-xattrs", "-no-progress"],
                 check=True, stdout=subprocess.DEVNULL)
