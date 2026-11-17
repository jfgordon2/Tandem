"""Storage & Data reads and actions through StarPilot's recording and model owners."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import shutil
import stat
import threading
import time
from typing import TYPE_CHECKING, Any

from openpilot.selfdrive.ui.tandem.prefs import Choice
from openpilot.starpilot.tandem.uploads import MODES, PREFERENCE, upload_mode

UPLOADS = Choice(PREFERENCE, MODES)

if TYPE_CHECKING:
  from openpilot.starpilot.models.manager import ModelManager


def _bytes(paths: Iterable[Path]) -> float:
  """Count local files once, including tiles shared between map generations."""
  seen: set[tuple[int, int]] = set()
  size = 0
  for path in paths:
    try:
      root = path.lstat()
    except FileNotFoundError:
      continue
    if not stat.S_ISDIR(root.st_mode):
      continue
    for folder, directories, files in os.walk(path):
      for name in directories + files:
        try:
          info = (Path(folder) / name).lstat()
        except FileNotFoundError:
          if name in directories:
            directories.remove(name)
          continue
        if name in directories and info.st_dev != root.st_dev:
          directories.remove(name)
        if stat.S_ISREG(info.st_mode) and info.st_dev == root.st_dev:
          if info.st_nlink > 1:
            key = (info.st_dev, info.st_ino)
            if key in seen:
              continue
            seen.add(key)
          size += info.st_size
  return float(size)


def _recordings_size() -> float:
  """Count the known recording folders while excluding boot and crash logs."""
  from openpilot.system.loggerd.storage_roots import legacy_segment, open_recording_root, recording_roots, root_current

  total = 0.0
  for root in recording_roots():
    try:
      fd = open_recording_root(root.path)
    except FileNotFoundError:
      continue
    try:
      if not root_current(root, fd):
        continue
      with os.scandir(fd) as entries:
        total += _bytes(Path(root.path) / entry.name for entry in entries
                        if legacy_segment(entry.name) and entry.is_dir(follow_symlinks=False))
    finally:
      os.close(fd)
  return total


def delete_recordings(parked: Callable[[], bool]) -> bool:
  """Delete closed drive segments through the native deleter's inode checks."""
  from openpilot.system.loggerd.deleter import _delete_legacy, _directories_by_age
  from openpilot.system.loggerd.storage_roots import DIR_FLAGS, legacy_segment, open_recording_root, recording_roots, root_current

  if not parked():
    return False
  complete = True
  for segment in _directories_by_age(recording_roots()):
    if not legacy_segment(segment.name):
      continue
    root_fd = fd = -1
    try:
      root_fd = open_recording_root(segment.root.path)
      if not root_current(segment.root, root_fd):
        complete = False
        continue
      fd = os.open(segment.name, DIR_FLAGS, dir_fd=root_fd)
      opened = os.fstat(fd)
      if (opened.st_dev, opened.st_ino) != (segment.device, segment.inode):
        complete = False
        continue
      fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
      if not parked():
        return False
      complete = _delete_legacy(segment.root, root_fd, segment.name, fd) and complete
    except FileNotFoundError:
      continue
    except OSError:
      complete = False
    finally:
      if fd >= 0:
        os.close(fd)
      if root_fd >= 0:
        os.close(root_fd)
  return complete


def unused_models(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
  """Keep bundled, active and randomizer-eligible models out of bulk removal."""
  if snapshot["randomizer"]:
    return ()
  active = {snapshot["activeSmallModel"], snapshot["activeBigModel"], snapshot["currentModel"]}
  return tuple(row["value"] for row in snapshot["models"]
               if row["installed"] and not row["builtin"] and row["value"] not in active)


def remove_models(manager: ModelManager, selected: tuple[str, ...], parked: Callable[[], bool]) -> bool:
  """Revalidate confirmed selections and let the native model owner delete each file."""
  complete = True
  for model in selected:
    if not parked():
      return False
    fresh = manager.snapshot()
    if fresh["downloading"]:
      return False
    if model not in unused_models(fresh):
      complete = False
      continue
    manager.action("delete", {"model": model})
  return complete


def sizes(model_root: Path) -> dict[str, float]:
  """Measure release's three categories against native storage paths."""
  from openpilot.common.hardware import PC
  from openpilot.starpilot.maps.storage import offline_root
  from openpilot.starpilot.navigation.google_tiles import google_root
  from openpilot.starpilot.navigation.offline_roads import KINDS, roads_root
  from openpilot.starpilot.tandem.map_removal import legacy_map_paths

  usage = shutil.disk_usage(Path.home() if PC else "/data")
  road_tiles = roads_root()
  map_paths = (offline_root(), google_root() / "tiles", *(road_tiles / kind for kind in KINDS), *legacy_map_paths())
  return {"Drives": _recordings_size(), "Maps": _bytes(map_paths),
          "Models": _bytes((model_root.parent,)), "Total": float(usage.total), "Free": float(usage.free)}


@dataclass(frozen=True)
class StorageSample:
  """The latest measurement and the models covered by a confirmation."""

  usage: dict[str, float]
  unused: tuple[str, ...] = ()
  model_busy: bool = False
  map_generation: str | None = None


class StorageOwner:
  """Keep storage scans and deletes off the UI thread."""

  def __init__(self, params: Any, request_toggle: Callable[[str, bool], bool], local: Callable[[], bool], parked: Callable[[], bool],
               engaged: Callable[[], bool]) -> None:
    self._params = params
    self._request_toggle = request_toggle
    self._local = local
    self._parked = parked
    self._engaged = engaged
    self.sample = StorageSample({})
    self._models: ModelManager | None = None
    self._job: Future[tuple[StorageSample, str | None]] | None = None
    self._next = 0.0

  @property
  def busy(self) -> bool:
    """Only one storage action or measurement runs at a time."""
    return self._job is not None

  def allowed(self) -> bool:
    """Destructive commands require a local, parked device."""
    return self._local() and self._parked()

  def record(self, key: str) -> bool:
    """Read the native recording preference."""
    return bool(self._params.get_bool(key))

  def record_allowed(self, key: str) -> bool:
    """Honor engagement and the native fleet camera lock."""
    return self._local() and not self._engaged() and (key != "RecordFront" or not self._params.get_bool("RecordFrontLock"))

  def set_record(self, key: str, on: bool) -> None:
    """Use the existing native toggle and restart request."""
    if self.record_allowed(key):
      self._request_toggle(key, on)

  @property
  def uploads(self) -> int:
    """Show the same automatic upload mode the manager reads."""
    mode = upload_mode(self._params)
    return MODES.index(mode) if mode is not None else -1

  def uploads_allowed(self) -> bool:
    """Only the local UI may change its automatic upload policy."""
    return self._local()

  def set_uploads(self, index: int) -> None:
    """Save one of release's three automatic upload modes."""
    if self.uploads_allowed():
      UPLOADS.set(MODES[index])

  def _manager(self) -> ModelManager:
    """Create a read-only catalog client until the driver confirms a removal."""
    if self._models is None:
      from openpilot.starpilot.models.manager import ModelManager
      self._models = ModelManager(parked=self.allowed)
    return self._models

  def _start(self, action: Callable[[], bool] | None = None) -> None:
    """Run one command and refresh the displayed state afterwards."""
    if self.busy:
      return
    job: Future[tuple[StorageSample, str | None]] = Future()
    previous = self.sample

    def work() -> None:
      """Collect a renderable result even if a file changes during the scan."""
      error = None
      try:
        if action is not None and not action():
          error = ""
      except Exception as failure:
        error = str(failure) or type(failure).__name__
      try:
        manager = self._manager()
        snapshot = manager.snapshot()
        usage = sizes(manager.root)
        generation = self._map_generation() if usage.get("Maps") else None
        current = StorageSample(usage, unused_models(snapshot), bool(snapshot["downloading"]), generation)
      except Exception:
        current = previous
      job.set_result((current, error))

    threading.Thread(target=work, daemon=True, name="tandem-storage").start()
    self._job = job

  def poll(self, *, refresh: bool = False) -> str | None:
    """Handle results on the UI thread and refresh when the panel is visible."""
    error = None
    if self._job is not None and self._job.done():
      self.sample, error = self._job.result()
      self._job = None
      self._next = time.monotonic() + 30.0
    if not self.busy and (refresh or time.monotonic() >= self._next):
      self._start()
    return error

  def delete_drives(self) -> None:
    """Recheck admission after confirmation, before starting the worker."""
    if self.allowed():
      self._start(lambda: delete_recordings(self.allowed))

  def _map_generation(self) -> str | None:
    """Read the native selection and leave the action disabled while it is busy."""
    from openpilot.starpilot.maps.operation_owner import ACTIVE, request_operation

    try:
      reply = request_operation({"version": 1, "op": "status"}, timeout_s=1)
      result = reply.get("result", {})
      generation = result.get("selectedGeneration")
      if reply.get("ok") and result.get("state") not in (ACTIVE | {"unavailable"}) and isinstance(generation, str):
        return generation
    except (OSError, RuntimeError, ValueError):
      pass
    return None

  def delete_maps(self, generation: str) -> None:
    """Delete the displayed map selection through the parked operation owner."""
    if not self.allowed():
      return

    def remove() -> bool:
      """Wait for all native and legacy stores to acknowledge the confirmed deletion."""
      from openpilot.starpilot.maps.operation_owner import request_operation

      if not self.allowed():
        return False
      result = request_operation({"version": 1, "op": "tandem_remove", "expectedCurrentGeneration": generation}, timeout_s=90)
      return result.get("ok") is True

    self._start(remove)

  def delete_models(self, selected: tuple[str, ...]) -> None:
    """Remove only the models shown when the driver opened the confirmation."""
    if self.allowed() and selected and not self.sample.model_busy:
      self._start(lambda: remove_models(self._manager(), selected, self.allowed))
