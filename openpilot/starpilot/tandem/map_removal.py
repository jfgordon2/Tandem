"""Remove managed snapshots under the same lock used by mapd admission."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
import fcntl
import os
import re
from pathlib import Path
import stat
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from openpilot.starpilot.maps.operation_owner import MapSnapshotOperationOwner


def remove_snapshots(owner: MapSnapshotOperationOwner, request: dict[str, object]) -> dict:
  """Check the displayed selection and make old generations unreachable before reclaiming files."""
  from openpilot.starpilot.maps.operation_owner import ACTIVE, GENERATION, OperationError, _ensure_owned_offline_root

  expected = request.get("expectedCurrentGeneration")
  if (set(request) != {"version", "op", "expectedCurrentGeneration"} or type(expected) is not str
      or (expected and GENERATION.fullmatch(expected) is None)):
    raise OperationError("invalid_request")

  from openpilot.starpilot.tandem.tile_removal import remove_owned_directory

  root = owner.root
  try:
    with owner._lock:
      if owner._closed:
        raise OperationError("unavailable")
      if owner._status["state"] in ACTIVE:
        raise OperationError("busy")
      if not owner._parked():
        raise OperationError("not_parked")
      if not root.exists():
        if expected:
          raise OperationError("selection_changed")
        return owner.snapshot()
      _ensure_owned_offline_root(root)
      flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
      fd = os.open(root / ".admission.lock", flags, 0o600)
      try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
          raise OperationError("unavailable")
        try:
          fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
          raise OperationError("busy") from error
        if owner._selected() != expected:
          raise OperationError("selection_changed")

        generations = root / "generations"
        info = generations.lstat() if generations.exists() or generations.is_symlink() else None
        if info is not None and (not stat.S_ISDIR(info.st_mode) or info.st_dev != root.stat().st_dev):
          raise OperationError("unavailable")
        if not owner._parked():
          raise OperationError("not_parked")

        selector = root / "current.json"
        selected = selector.exists() or selector.is_symlink()
        if selected and not stat.S_ISREG(selector.lstat().st_mode):
          raise OperationError("unavailable")
        quarantined = Path(tempfile.mkdtemp(prefix=".tandem-remove-", dir=root))
        if selected:
          selector.rename(quarantined / selector.name)
        try:
          if info is not None:
            generations.rename(quarantined / generations.name)
        except OSError:
          if selected:
            (quarantined / selector.name).rename(selector)
          raise
      finally:
        os.close(fd)

    # Any previous attempt interrupted after detaching its generation can be reclaimed too.
    for staged in root.glob(".tandem-remove-*"):
      if re.fullmatch(r"\.tandem-remove-[0-9a-z_]{8}", staged.name) and not staged.is_symlink():
        remove_owned_directory(staged)
    return owner.snapshot()
  except OSError as error:
    # A failed cleanup can leave a quarantined generation. It cannot be selected or reused.
    raise OperationError("unavailable") from error


def legacy_map_paths(data: Path = Path("/data")) -> tuple[Path, ...]:
  """The two downloaded map formats used by Tandem's release branch."""
  if os.environ.get("OPENPILOT_PREFIX"):
    return ()
  navigation = data / "tandem/navigation"
  return data / "media/0/osm/offline", navigation / "bundles", navigation / "downloads", navigation / "staging"


def remove_legacy_maps(parked: Callable[[], bool], data: Path = Path("/data")) -> bool:
  """Reuse release's map roots, install lock and reader leases."""
  from openpilot.starpilot.tandem.tile_removal import remove_owned_directory

  paths = legacy_map_paths(data)
  if not paths:
    return True
  _, bundles, downloads, staging = paths
  navigation = bundles.parent
  if not parked():
    return False
  with ExitStack() as locks:
    if navigation.exists():
      if navigation.resolve() != navigation:
        return False
      for path in (bundles, downloads, staging):
        if path.is_symlink():
          return False
      names = [navigation / ".install.lock"]
      for path in (bundles, downloads):
        if path.is_dir():
          folders = tuple(folder for folder in path.iterdir() if folder.is_dir() or folder.is_symlink())
          if any(folder.is_symlink() for folder in folders):
            return False
          names.extend(folder / ".lease" for folder in folders)
      for path in names:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        locks.callback(os.close, fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
          return False
        try:
          fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
          return False
    for path in paths:
      if not parked():
        return False
      remove_owned_directory(path)
    if navigation.is_dir():
      for name in ("active.json", "map-job.json", "map-request.json", "map-cancel.json", "map-road.json"):
        (navigation / name).unlink(missing_ok=True)
  return True

def remove_all_maps(owner: MapSnapshotOperationOwner, request: dict[str, object]) -> dict:
  """Clear managed snapshots and ask navtilesd to clear all of its downloaded data."""
  from openpilot.starpilot.maps.operation_owner import OperationError
  from openpilot.common.params import Params
  from openpilot.starpilot.navigation.offline_roads import roads_root
  from openpilot.starpilot.navigation.owner import NavigationOwner
  from openpilot.starpilot.tandem.tile_removal import request_clear_tiles

  if not owner._parked():
    raise OperationError("not_parked")
  if Params().get("NavDestination") or NavigationOwner().read_routing().get("destination"):
    raise OperationError("busy")
  status = remove_snapshots(owner, request)
  if not request_clear_tiles(roads_root(), owner._parked):
    raise OperationError("unavailable")
  if not remove_legacy_maps(owner._parked):
    raise OperationError("unavailable")
  return status
