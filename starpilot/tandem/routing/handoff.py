"""Pair the existing road downloader with the broker, without importing its installer.

Runs on StarPilot's existing update_maps thread. The scoped views keep the real
selection and DownloadMaps flag intact while its unchanged downloader handles
one state. The broker owns the barrier between states and the final installation.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import threading
import time
import uuid
from typing import Any, TYPE_CHECKING

from openpilot.starpilot.tandem.routing import config as C, demand

if TYPE_CHECKING:
  from openpilot.common.params import Params

_scope = threading.local()


def in_progress() -> bool:
  return getattr(_scope, "active", False)


def on_map_download_started(selection: str) -> None:
  if not in_progress():
    from openpilot.starpilot.tandem.routing.maps import on_map_download_started as companion
    companion(selection)


def enqueue(selection: str, **values: Any) -> dict:
  job = {"id": uuid.uuid4().hex, "selection": selection, "created": time.time(), **values}  # noqa: TID251
  C.atomic_json(C.root() / "map-request.json", job)
  return job


def available() -> bool:
  """Wake/probe before claiming road work; a missing broker leaves mapd alone."""
  if not demand.wake():
    return False
  end, identity = time.monotonic() + 5, uuid.uuid4().hex
  while time.monotonic() < end and C.enabled():
    try:
      with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(max(.001, end - time.monotonic()))
        connection.connect(str(C.socket_path()))
        connection.sendall(json.dumps({"protocol": C.PROTOCOL, "id": identity, "action": "status"}).encode() + b"\n")
        with connection.makefile("rb") as stream:
          response = json.loads(stream.readline(65536))
        return bool(response.get("id") == identity and response.get("protocol") == C.PROTOCOL)
    except (OSError, ValueError):
      time.sleep(.05)
  return False


def regions_for(selection: str) -> list[str]:
  """The road regions a selection downloads, one per state for a whole country."""
  from openpilot.starpilot.common.maps_selection import normalize_maps_selected
  from openpilot.starpilot.common.maps_catalog import VALID_MAP_TOKENS
  regions = set(filter(None, normalize_maps_selected(selection).split(",")))
  if "nation.US" in regions:
    regions.remove("nation.US")
    regions.update(t for t in VALID_MAP_TOKENS if t.startswith("us_state."))
  for path in (C.root() / "catalog.json", Path(__file__).with_name("catalog.json")):
    try:
      data = json.loads(path.read_text())
      if data["schema"] == 2 and regions and regions <= data["dataset"]["regions"].keys():
        return sorted(regions)
    except (OSError, ValueError, KeyError, TypeError):
      pass
  return []


def road_receipt(identity: str) -> dict:
  value = demand.read_map("map-road.json")
  return value if value.get("id") == identity else {"id": identity, "completed": []}


def cancelled(identity: str, memory: Params) -> bool:
  return (not C.enabled() or memory.get_bool("CancelDownloadMaps")
          or demand.read_map("map-cancel.json").get("id") == identity
          or demand.read_map("map-request.json").get("id") != identity)


def wait_for_road_idle(identity: str, memory: Params, subscriber: Any = None) -> bool:
  """Waits up to 10 seconds for mapd to finish what it's doing, so a new command isn't ignored. False if it doesn't."""
  # mapd ignores new download commands while active. Its cancellation can take
  # longer than the upstream updater's five-second wait (an archive is in flight).
  # Drain that operation before issuing the next command, including after restart.
  if subscriber is None:
    import cereal.messaging as messaging
    subscriber = messaging.SubMaster(["mapdExtendedOut"])
  observed, end = False, time.monotonic() + 10
  while not cancelled(identity, memory):
    subscriber.update(250)
    if subscriber.updated["mapdExtendedOut"]:
      observed = True
      if not subscriber["mapdExtendedOut"].downloadProgress.active:
        return True
    if not observed and time.monotonic() >= end:
      raise C.RoutingError("road_download_failed")
  return False


class SelectionView:
  """Params as StarPilot's road downloader sees them, with MapsSelected set to one region."""

  def __init__(self, params: Params, selection: str) -> None:
    self.params, self.selection = params, selection

  def __getattr__(self, name: str) -> Any:
    return getattr(self.params, name)

  def get(self, key: str, *args: Any, **kwargs: Any) -> Any:
    return self.selection if key == "MapsSelected" else self.params.get(key, *args, **kwargs)

  def put(self, key: str, value: Any) -> None:
    if key not in ("MapsSelected", "LastMapsUpdate"):
      self.params.put(key, value)


class MemoryView:
  """Memory params as the road downloader sees them, so cancelling one region doesn't clear the whole paired job."""

  def __init__(self, memory: Params, identity: str) -> None:
    self.memory, self.identity, self.was_cancelled = memory, identity, False

  def __getattr__(self, name: str) -> Any:
    return getattr(self.memory, name)

  def get_bool(self, key: str) -> bool:
    if key == "CancelDownloadMaps":
      self.was_cancelled |= cancelled(self.identity, self.memory)
      return self.was_cancelled
    return bool(self.memory.get_bool(key))

  def remove(self, key: str) -> None:
    # Keep the existing ThreadManager lock until the whole paired job finishes.
    if key not in ("DownloadMaps", "CancelDownloadMaps"):
      self.memory.remove(key)


def coordinate(updater: Any, now: float, params: Params, memory: Params, selection: str, date: str) -> bool:
  """Runs a paired job from StarPilot's update_maps: road data one region at a time, with the broker's routes.

  StarPilot's road maps always finish, even when routing data fails.

  Returns:
    True when it handled the download; False to let StarPilot's downloader run as usual.
  """
  if in_progress() or not C.enabled():
    return False
  regions = regions_for(selection)
  if not regions or not available():
    return False
  pending, previous = demand.read_map("map-request.json"), demand.read_map()
  if not (pending.get("paired") and pending.get("selection") == selection and
          (previous.get("id") != pending.get("id") or previous.get("phase") in demand.ACTIVE_MAP_PHASES)):
    pending = enqueue(selection, paired=True, road_regions=regions)
  identity = pending["id"]
  memory.put_bool("DownloadMaps", True)
  view = MemoryView(memory, identity)
  dated = False
  _scope.active = True
  acknowledge_by = time.monotonic() + 30
  try:
    while True:
      if cancelled(identity, memory):
        C.atomic_json(C.root() / "map-cancel.json", {"id": identity})
        return True
      receipt, job = road_receipt(identity), demand.read_map()
      completed = set(receipt["completed"])
      if job.get("id") != identity:
        if time.monotonic() >= acknowledge_by:
          raise C.RoutingError("worker_failed")  # the guarded hook falls back to original mapd
        time.sleep(.1)
        continue
      terminal = job.get("phase") not in demand.ACTIVE_MAP_PHASES
      if terminal and job.get("phase") == "cancelled":
        return True
      # Even a routing/runtime/space failure must finish StarPilot's road maps.
      region = next((r for r in regions if r not in completed), None) if terminal else \
        job.get("road_region") if not job.get("paused") else None
      if region and region not in completed:
        try:
          progress = json.loads(memory.get("MapsDownloadProgress", encoding="utf-8") or "{}")
        except (ValueError, TypeError):
          progress = {}
        fresh = progress.get("selectedKey") == region and progress.get("updatedAt", 0) >= pending["created"]
        if not (fresh and progress.get("completed")):
          if not wait_for_road_idle(identity, memory):
            C.atomic_json(C.root() / "map-cancel.json", {"id": identity})
            return True
          updater(now, SelectionView(params, region), view, manual_update=True)
          progress = json.loads(memory.get("MapsDownloadProgress", encoding="utf-8") or "{}")
        if view.was_cancelled or cancelled(identity, memory):
          C.atomic_json(C.root() / "map-cancel.json", {"id": identity})
          return True
        if (progress.get("selectedKey") != region or not progress.get("completed") or progress.get("cancelled")
            or progress.get("primaryLocation", region) != region
            or progress.get("downloadedFiles", 0) < progress.get("totalFiles", 0)):
          C.atomic_json(C.root() / "map-road.json", {**receipt, "error": "road_download_failed"})
          return True
        completed.add(region)
        C.atomic_json(C.root() / "map-road.json", {"id": identity, "completed": sorted(completed)})
      if completed == set(regions):
        if not dated:
          params.put("LastMapsUpdate", date)
          dated = True
        if terminal:
          C.atomic_json(C.root() / "map-job.json", {**job, "road_ready": True})
          return True
      time.sleep(.1)
  finally:
    _scope.active = False
    memory.remove("DownloadMaps")
    memory.remove("CancelDownloadMaps")
