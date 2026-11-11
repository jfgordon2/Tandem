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
from typing import TYPE_CHECKING
from collections.abc import Iterable, Iterator

from openpilot.starpilot.tandem.routing import config as C, verified

if TYPE_CHECKING:
  from openpilot.starpilot.tandem.routing.bundles import Bundle


def is_image(bundle: Bundle) -> bool:
  return bundle.manifest["schema"] in (3, 4)


def mount_root() -> Path:
  identity = hashlib.sha256(str(C.root().resolve()).encode()).hexdigest()[:16]
  base = Path("/dev/shm") if sys.platform == "linux" else Path(tempfile.gettempdir())
  default = base / f"tandem-routing-mounts-{os.getuid()}" / identity
  return Path(os.getenv("TANDEM_ROUTING_MOUNT_DIR", str(default)))


def mount_path(bundle: Bundle) -> Path:
  if _staged(bundle):
    folder = hashlib.sha256(str(bundle.folder.resolve()).encode()).hexdigest()[:16]
    return mount_root() / "incoming" / f"{bundle.id}-{bundle.generation}-{folder}"
  return mount_root() / f"{bundle.id}-{bundle.generation}"


def _staged(bundle: Bundle) -> bool:
  return bundle.folder.resolve().is_relative_to((C.root() / "downloads").resolve())


def source(bundle: Bundle) -> Path:
  """The bundle's graph file."""
  return Path(bundle.folder / str(bundle.manifest["graph"]["file"]))


def graph_path(bundle: Bundle) -> Path:
  return mount_path(bundle) / "tiles.tar" if is_image(bundle) else bundle.folder / "tiles.tar"


def _unescape(value: str) -> str:
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


def _command(arguments: list[str], timeout: float = 15) -> None:
  prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]
  try:
    subprocess.run([*prefix, *arguments], check=True, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  except (OSError, subprocess.SubprocessError):
    raise C.RoutingError("data_incompatible") from None


def _backing(row: dict) -> Path:
  return Path(_unescape((Path("/sys/dev/block") / row["device"] / "loop/backing_file").read_text().strip()))


def require_mounted(bundle: Bundle) -> Path:
  """The bundle's graph path, mounting its image if it isn't mounted yet."""
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


@contextmanager
def _mount_lock(*, blocking: bool = True) -> Iterator[None]:
  """Serialize directory creation/mount/unmount with cleanup across processes."""
  parent = mount_root().parent
  parent.mkdir(parents=True, exist_ok=True, mode=0o700)
  if parent.is_symlink() or parent.stat().st_uid not in (0, os.getuid()) or parent.stat().st_mode & 0o022:
    raise C.RoutingError("data_incompatible")
  mount_root().mkdir(exist_ok=True, mode=0o700)
  root_stat = mount_root().stat()
  if mount_root().is_symlink() or root_stat.st_uid not in (0, os.getuid()) or root_stat.st_mode & 0o022:
    raise C.RoutingError("data_incompatible")
  path = mount_root() / ".mount.lock"
  if path.is_symlink():
    raise C.RoutingError("data_incompatible")
  with path.open("a") as stream:
    fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    yield


def ensure(bundle: Bundle) -> Path:
  verified.require(bundle)
  if not is_image(bundle):
    return graph_path(bundle)
  if sys.platform != "linux":
    raise C.RoutingError("data_incompatible")
  with _mount_lock():
    return _ensure_locked(bundle)


def _ensure_locked(bundle: Bundle) -> Path:
  point = mount_path(bundle)
  if point in _mounts():
    return require_mounted(bundle)
  if point.is_symlink():
    raise C.RoutingError("data_incompatible")
  if _staged(bundle):
    point.parent.mkdir(exist_ok=True, mode=0o700)
    if point.parent.is_symlink() or point.parent.stat().st_uid != os.getuid() or point.parent.stat().st_mode & 0o022:
      raise C.RoutingError("data_incompatible")
  point.mkdir(exist_ok=True, mode=0o700)
  if any(point.iterdir()):
    raise C.RoutingError("data_incompatible")
  _command(["mount", "-t", "squashfs", "-o", "ro,nodev,nosuid,noexec,loop", str(source(bundle).resolve()), str(point.resolve())])
  return require_mounted(bundle)


def unmount(bundle: Bundle) -> None:
  """Caller must hold the bundle's exclusive reader lease."""
  if not is_image(bundle):
    return
  with _mount_lock():
    _unmount_point(mount_path(bundle))


def _unmount_point(point: Path) -> None:
  # Caller holds the namespace transition lock as well as any bundle lease.
  row = _mounts().get(point)
  if row:
    if row["type"] != "squashfs" or "ro" not in row["options"]:
      raise C.RoutingError("data_incompatible")
    _command(["umount", str(point)])
  if point.exists() and not point.is_symlink():
    point.rmdir()


def unmount_id(identity: str) -> None:
  """Caller holds this ID's exclusive lease, including for a corrupt manifest."""
  if mount_root().exists():
    with _mount_lock():
      for point in mount_root().glob(f"{identity}-*"):
        if point.name.rpartition("-")[0] == identity and not point.is_symlink():
          _unmount_point(point)


def release_unused() -> None:
  """Also reclaim orphan mounts after a service restart. Never force an unmount."""
  if not mount_root().exists():
    return
  try:
    with _mount_lock(blocking=False):
      _release_unused_locked()
  except (OSError, C.RoutingError):
    pass  # a transition owns the namespace; idle cleanup can wait until later


def _release_unused_locked() -> None:
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
  for point in (mount_root() / "incoming").glob("*"):
    if not point.is_dir() or point.is_symlink():
      continue
    try:
      row = _mounts().get(point)
      if not row:
        point.rmdir()
        continue
      folder = _backing(row).parent
      if folder.is_symlink() or not folder.resolve().is_relative_to((C.root() / "downloads").resolve()):
        continue
      if folder.exists():
        with (folder / ".lease").open("a") as lease:
          fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
          _unmount_point(point)
      else:
        _unmount_point(point)
    except (OSError, C.RoutingError):
      pass


@contextmanager
def reader(bundle: Bundle) -> Iterator[None]:
  """Holds a shared lease on the bundle while its graph is read, so it isn't removed underneath."""
  with (bundle.folder / ".lease").open("a") as lease:
    try:
      fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
      raise C.RoutingError("busy") from None
    verified.require(bundle)
    ensure(bundle)
    yield


@contextmanager
def staged_reader(bundle: Bundle) -> Iterator[Path]:
  """One incoming part at a time; its lease also protects crash cleanup."""
  if not _staged(bundle):
    raise C.RoutingError("invalid_request")
  with (bundle.folder / ".lease").open("a") as lease:
    try:
      fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
      raise C.RoutingError("busy") from None
    try:
      ensure(bundle)
      yield graph_path(bundle)
    finally:
      fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
      with _mount_lock():
        _unmount_point(mount_path(bundle))


def pack_stream(chunks: Iterable[bytes], size: int, image: Path, gate: C.Gate = lambda: None, *, progress: C.Progress | None = None) -> dict:
  """Wrap a streamed native tar in SquashFS; never materialize an expanded file."""
  import tarfile
  from openpilot.starpilot.tandem.routing import tiles
  tool = shutil.which("mksquashfs")
  if tool is None:
    raise C.RoutingError("data_incompatible")
  info = tarfile.TarInfo("tiles.tar")
  info.size, info.mode = size, 0o444
  command = [tool, "-", str(image.resolve()), "-tar", "-comp", "gzip", "-Xcompression-level", "6", "-b", "131072",
             "-processors", "2", "-mem", "64M", "-noappend", "-no-xattrs", "-no-progress", "-mkfs-time", "0", "-all-time", "0"]
  count, digest = 0, hashlib.sha256()
  sent = 0
  if progress is not None:
    progress(0, size)
  def outer() -> Iterator[bytes]:
    nonlocal count
    yield info.tobuf(format=tarfile.GNU_FORMAT)
    for block in chunks:
      count += len(block)
      if count > size:
        raise C.RoutingError("data_incompatible")
      digest.update(block)
      yield block
    if count != size:
      raise C.RoutingError("data_incompatible")
    yield bytes(tiles.padded(512 + size + 1024, tarfile.RECORDSIZE) - 512 - size)
  try:
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
      stdin = process.stdin
      if stdin is None:   # Popen always gives the pipe asked for; this tells the type checker
        raise C.RoutingError("worker_failed")
      try:
        os.set_blocking(stdin.fileno(), False)
        with selectors.DefaultSelector() as selector:
          selector.register(stdin, selectors.EVENT_WRITE)
          deadline = time.monotonic() + 300
          for block in outer():
            pending = memoryview(block)
            while pending:
              gate()
              if time.monotonic() > deadline:
                raise C.RoutingError("timeout")
              if process.poll() is not None:
                raise C.RoutingError("data_incompatible")
              if selector.select(.2):
                try:
                  pending = pending[os.write(stdin.fileno(), pending[:tiles.BLOCK]):]
                  deadline = time.monotonic() + 300
                except BlockingIOError:
                  pass
            sent += len(block)
            if progress is not None:
              progress(min(size, max(0, sent - 512)), size)
        stdin.close()
        while process.poll() is None:
          gate()
          if time.monotonic() > deadline:
            raise C.RoutingError("timeout")
          time.sleep(.1)
        if process.returncode:
          raise C.RoutingError("no_space" if shutil.disk_usage(image.parent).free < 256 * 1024**2 else "data_incompatible")
      finally:
        if process.poll() is None:
          process.terminate()
          try:
            process.wait(timeout=3)
          except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
  except (OSError, subprocess.SubprocessError):
    raise C.RoutingError("data_incompatible") from None
  finally:
    # Close a producer suspended on a mounted input before its lease unwinds.
    # An exception traceback can otherwise retain that file descriptor.
    close = getattr(chunks, "close", None)
    if close is not None:
      close()
  return {"bytes": count, "sha256": digest.hexdigest()}


def verify_graph(folder: Path, manifest: dict, gate: C.Gate = lambda: None, *, progress: C.Progress | None = None) -> None:
  """Stream the logical graph once at acceptance, with bounded decoder queues."""
  graph = manifest["graph"]
  tool = shutil.which("unsquashfs")
  if tool is None:
    raise C.RoutingError("data_incompatible")
  command = [tool, "-cat", "-no-progress", "-processors", "1", *_queue_options(tool),
             str((folder / graph["file"]).resolve()), "tiles.tar"]
  count, digest = 0, hashlib.sha256()
  if progress is not None:
    progress(0, graph["bytes"])
  with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
    stdout = process.stdout
    if stdout is None:   # Popen always gives the pipe asked for; this tells the type checker
      raise C.RoutingError("worker_failed")
    try:
      deadline = time.monotonic() + 300
      with selectors.DefaultSelector() as selector:
        selector.register(stdout, selectors.EVENT_READ)
        while True:
          paused = time.monotonic()
          gate()
          deadline += time.monotonic() - paused
          if time.monotonic() > deadline:
            raise C.RoutingError("timeout")
          if not selector.select(.2):
            continue
          block = os.read(stdout.fileno(), min(256 * 1024, graph["bytes"] - count + 1))
          if not block:
            break
          count += len(block)
          if count > graph["bytes"]:
            raise C.RoutingError("data_incompatible")
          digest.update(block)
          if progress is not None:
            progress(count, graph["bytes"])
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
def _queue_options(tool: str) -> list[str]:
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
