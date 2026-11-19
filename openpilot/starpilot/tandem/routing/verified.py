"""Cheap readiness receipts. Full data checks run at installation or while parked."""
from __future__ import annotations

import json
import math
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from openpilot.starpilot.tandem.routing import config as C

if TYPE_CHECKING:
  from openpilot.starpilot.tandem.routing.bundles import Bundle

RECEIPT = ".verified.json"
INTERVAL = 24 * 60 * 60


def identity(path: Path) -> list[int]:
  value = path.lstat()
  if not stat.S_ISREG(value.st_mode):
    raise C.RoutingError("data_incompatible")
  return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


class Hashes:
  """Operation-local hash evidence; never shared with startup or parked audits."""

  def __init__(self) -> None:
    self._checked: dict[Path, tuple] = {}   # path -> (stat before reading, checksum), so unchanged files aren't reread

  def digest(self, path: Path, gate: C.Gate = lambda: None) -> str:
    """The file's SHA-256, reusing this operation's earlier checksum when the file hasn't changed."""
    from openpilot.starpilot.tandem.routing.bundles import digest
    path = Path(path).absolute()
    gate()
    before = identity(path)
    previous = self._checked.get(path)
    if previous and previous[0] == before:
      return str(previous[1])
    # The device's filesystem clock can have a coarser tick than st_*_ns
    # suggests. Start hashing only after the file's ctime tick has passed;
    # otherwise a same-size write/chmod in that tick could evade identity checks.
    end = time.monotonic() + 2
    with tempfile.TemporaryFile(dir=path.parent) as probe:
      mode = 0o400
      while True:
        gate()
        os.fchmod(probe.fileno(), mode)
        mode ^= 0o200
        tick = os.fstat(probe.fileno()).st_ctime_ns
        before = identity(path)
        if tick > before[4]:
          break
        if time.monotonic() >= end:
          raise C.RoutingError("data_incompatible")
        time.sleep(.005)
    checksum = digest(path, gate)
    if identity(path) != before:
      raise C.RoutingError("data_incompatible")
    self._checked[path] = (before, checksum)
    return checksum


def files(bundle: Bundle) -> dict:
  return {name: identity(bundle.folder / name) for name in bundle.manifest["files"]}


def read(bundle: Bundle) -> dict:
  """The bundle's verification receipt, or {} when it has none or it doesn't match."""
  try:
    path = bundle.folder / RECEIPT
    if path.is_symlink():
      return {}
    value = json.loads(path.read_text())
    if (type(value.get("schema")) is not int or value["schema"] != 1 or value.get("generation") != bundle.generation
        or value.get("files") != files(bundle) or type(value.get("checked_at")) not in (int, float)
        or not math.isfinite(value["checked_at"]) or value["checked_at"] < 0):
      return {}
    return dict(value)
  except (OSError, ValueError, TypeError, AttributeError, C.RoutingError):
    return {}


def require(bundle: Bundle) -> None:
  if not read(bundle):
    raise C.RoutingError("data_incompatible")


def write(bundle: Bundle, expected: dict) -> None:
  if files(bundle) != expected:
    raise C.RoutingError("data_incompatible")
  C.atomic_json(bundle.folder / RECEIPT, {"schema": 1, "generation": bundle.generation,
                                        "files": expected, "checked_at": time.time()})  # noqa: TID251
  sync_directory(bundle.folder)


def sync_directory(folder: Path) -> None:
  fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
  try:
    os.fsync(fd)
  finally:
    os.close(fd)


def due(bundle: Bundle) -> bool:
  value = read(bundle)
  age = time.time() - value.get("checked_at", 0)  # noqa: TID251
  return not value or not 0 <= age < INTERVAL


def invalidate(bundle: Bundle) -> None:
  (bundle.folder / RECEIPT).unlink(missing_ok=True)
