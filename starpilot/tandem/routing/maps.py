"""Persistent map jobs shared by manual downloads and StarPilot's update schedule."""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager, ExitStack
import fcntl

from openpilot.starpilot.tandem.routing import bundles, catalog, config as C, downloads, images, verified
from openpilot.starpilot.tandem.routing.demand import ACTIVE_MAP_PHASES as ACTIVE, download_pending as running, read_map as read
from openpilot.starpilot.tandem.routing.handoff import enqueue, in_progress


def request(selection: str, wait_for_road=False) -> str:
  original = selection
  selection = catalog.normalize_maps_selected(selection)
  if not selection and (original or catalog.load()["schema"] != 2):
    raise C.RoutingError("invalid_request")
  # mapd's published receipt uses epoch seconds, so this comparison must use
  # the same clock. All internal deadlines and rate estimates are monotonic.
  # Enqueue independently of graph installation. Its lock can be held while
  # copying/checksumming a large graph; road-map downloads must not wait for it.
  job = enqueue(selection, wait_for_road=wait_for_road)
  return job["id"]


def on_map_download_started(selection: str) -> None:
  """Minimal upstream hook after its schedule/gates have accepted an update."""
  try:
    if C.enabled() and not in_progress():
      request(selection, wait_for_road=True)
  except Exception:
    pass  # Routing must never break StarPilot's own road-data download.


def cancel() -> None:
  identity = read("map-request.json").get("id")
  if identity:
    C.atomic_json(C.root() / "map-cancel.json", {"id": identity})


@contextmanager
def deletion():
  """Remove routing graphs as part of the existing Delete/Remove maps action.

  Retain runtime, geographic selection, saved places, and the shared schedule.
  Reader leases prevent deleting a graph being used by a route calculation.
  """
  C.require_parked()
  with bundles.lock(), ExitStack() as leases:
    if running():
      raise C.RoutingError("busy")
    folders = bundles.folders()
    for folder in folders:
      stream = leases.enter_context((folder / ".lease").open("a"))
      try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
      except BlockingIOError:
        raise C.RoutingError("busy") from None
    yield
    import shutil
    for folder in folders:
      images.unmount_id(folder.name)
      shutil.rmtree(folder)
    shutil.rmtree(C.root() / "downloads", ignore_errors=True)
    for name in ("active.json", "map-job.json", "map-request.json", "map-cancel.json", "map-road.json"):
      (C.root() / name).unlink(missing_ok=True)


def remove_all():
  with deletion():
    pass


class Manager:
  def __init__(self, memory, allowed=lambda: True, stop=None, installer=downloads.install, prepare=None):
    self.memory, self.allowed = memory, allowed
    self.stop = stop or threading.Event()
    self.installer = installer
    if prepare is None:
      from openpilot.starpilot.tandem.routing.tools.runtime import prepare
    self.prepare = prepare
    self.thread = None
    self.state = {}
    self._write_at = 0.0
    self._audit_after = 0.0

  def publish(self, *, force=False, **values):
    transition = any(k in values and values[k] != self.state.get(k) for k in ("phase", "stage", "error", "paused"))
    self.state.update(values)
    now = time.monotonic()
    # Byte progress is hot; persist no more than five times per second except
    # transitions. The job survives UI closure and manager/device restart.
    if force or now - self._write_at >= .2 or transition:
      C.atomic_json(C.root() / "map-job.json", {**self.state, "updated": now})
      self._write_at = now

  def gate(self):
    while True:
      if self.stop.is_set():
        raise C.RoutingError("interrupted")
      if (not C.enabled() or read("map-cancel.json").get("id") == self.state["id"]
          or read("map-request.json").get("id") != self.state["id"]):
        raise C.RoutingError("cancelled")
      if self.allowed():
        if self.state.get("paused"):
          self.publish(paused=False)
        return
      if not self.state.get("paused"):
        self.publish(paused=True)
      self.stop.wait(.25)

  def tick(self):
    if self.thread is not None and self.thread.is_alive():
      return
    pending = read("map-request.json")
    previous = read()
    if not pending or (pending.get("id") == previous.get("id") and previous.get("phase") not in ACTIVE):
      if time.monotonic() >= self._audit_after and self.allowed() and C.enabled():
        self._audit_after = time.monotonic() + 60
        self.thread = threading.Thread(target=self.audit, daemon=True)
        self.thread.start()
      return
    self.thread = threading.Thread(target=self.run, args=(pending,), daemon=True)
    self.thread.start()

  def audit(self):
    def gate():
      if self.stop.is_set() or not self.allowed() or running() or not C.enabled():
        raise C.RoutingError("interrupted")
      C.require_parked()
    try:
      from openpilot.starpilot.tandem.routing.datasets import cleanup
      gate()
      cleanup()
      for bundle in bundles.installed():
        gate()
        if verified.due(bundle):
          with (bundle.folder / ".lease").open("a") as lease:
            fcntl.flock(lease, fcntl.LOCK_SH | fcntl.LOCK_NB)
            bundles.verify(bundle.folder, gate)
    except (C.RoutingError, OSError):
      pass  # never run a full scan in a route request or interrupt a map job

  def assembly_gate(self):
    """Stop the compressor across a drive; retain downloaded parts for retry."""
    if self.stop.is_set() or not self.allowed():
      raise C.RoutingError("interrupted")
    if (not C.enabled() or read("map-cancel.json").get("id") == self.state["id"]
        or read("map-request.json").get("id") != self.state["id"]):
      raise C.RoutingError("cancelled")
    try:
      C.require_parked()
    except C.RoutingError:
      raise C.RoutingError("interrupted") from None

  def prune_road(self, pending):
    from openpilot.starpilot.tandem.routing import road
    road.apply(pending["selection"], self.assembly_gate, self.memory, paired=pending.get("paired", False))

  def run(self, pending):
    previous = read()
    road_ready = previous.get("id") == pending["id"] and previous.get("road_ready", False)
    self.state = {**pending, "phase": "road" if pending.get("wait_for_road") else "prepare", "done": 0, "total": 0,
                  "regions_ready": [], "current_regions": [], "error": "", "paused": False}
    self.publish(phase=self.state["phase"], force=True)
    try:
      if pending.get("wait_for_road") and not road_ready:
        end = time.monotonic() + 180  # fail explicitly if mapd never starts
        observed = False
        while True:
          self.gate()
          try:
            road = json.loads(self.memory.get("MapsDownloadProgress", encoding="utf-8") or "{}")
          except (ValueError, TypeError):
            road = {}
          if (road.get("selectedKey") == pending["selection"] and road.get("updatedAt", 0) >= pending["created"]):
            observed |= bool(road.get("active"))
            if road.get("cancelled"):
              raise C.RoutingError("cancelled")
            if road.get("completed"):
              break
          if not observed and time.monotonic() > end:
            raise C.RoutingError("road_download_failed")
          self.stop.wait(.25)
      self.publish(phase="prepare", road_ready=not pending.get("paired", False))
      self.gate()
      packages, unsupported = catalog.plan(pending["selection"], catalog.load(refresh=True, gate=self.gate))
      self.publish(unsupported=sorted(unsupported))
      if unsupported and any(package.get("kind") == "dataset" for package in packages):
        self.prune_road(pending)  # completed legacy downloads still follow the requested selection
        raise C.RoutingError("coverage_unavailable")
      if any(package.get("kind") != "dataset" or package["parts"] for package in packages):
        self.prepare(cancelled=lambda: self._setup_cancelled())
      for package in packages:
        self.gate()
        if package.get("kind") != "dataset" and any(b.id == package["id"] and verified.read(b) for b in bundles.installed()):
          self.publish(regions_ready=sorted(set(self.state["regions_ready"]) | set(package["regions"])))
          continue
        self.publish(phase="download", done=0, total=package["bytes"], current_regions=package["regions"])
        kwargs = {"pack_gate": self.assembly_gate, "activity": self.publish} if package.get("kind") == "dataset" else {}
        if pending.get("paired"):
          if package.get("kind") != "dataset" or sorted(package["regions"]) != pending["road_regions"]:
            raise C.RoutingError("coverage_unavailable")
          from openpilot.starpilot.tandem.routing.paired import Transfers
          kwargs["transfer"] = Transfers(self).fetch
        installed = self.installer(package, gate=self.gate, progress=lambda done, total: self.publish(done=done, total=total),
                                   installing=lambda: self.publish(phase="install", stage="", done=0, total=0), **kwargs)
        if installed is not None:
          # Keep one previous compatible graph for recovery; do not accumulate
          # a full extra graph on every Weekly/Monthly update.
          older = [b for b in bundles.installed() if b.id != installed.id and b.manifest.get("regions") and
                   set(b.manifest["regions"]) <= set(installed.manifest.get("regions", []))]
          older.sort(key=lambda b: b.manifest.get("built_at", ""), reverse=True)
          for old in older[1:]:
            self.gate()
            try:
              bundles.remove(old.id)
            except C.RoutingError:
              pass  # an active reader's lease wins over background cleanup
        self.publish(regions_ready=sorted(set(self.state["regions_ready"]) | set(package["regions"])))
      self.prune_road(pending)
      if unsupported:
        raise C.RoutingError("coverage_unavailable")
      self.publish(phase="ready", done=self.state["total"], error="", current_regions=[])
    except C.RoutingError as error:
      if error.code == "interrupted":
        self.publish(paused=True)  # retain an active journal so a restarted manager resumes
      else:
        self.publish(phase="cancelled" if error.code == "cancelled" else "failed", error=error.code)
    except Exception:
      self.publish(phase="failed", error="download_failed")
    finally:
      # Large inventories are temporary. Return unused native/Python heap
      # pages after an update or an interrupted assembly, before a drive.
      from openpilot.starpilot.tandem.routing.native_worker import release_heap
      release_heap()

  def _setup_cancelled(self):
    # Runtime installer already rechecks parked state and cancellation between
    # subprocess polls. Pause at each poll when Wi-Fi is unavailable.
    self.gate()
    return False

  def close(self):
    self.stop.set()
    if self.thread is not None:
      self.thread.join(20)


def run(stop: threading.Event):
  from cereal import log
  import cereal.messaging as messaging
  from openpilot.common.params import Params
  params, memory = Params(), Params(memory=True)
  sm = messaging.SubMaster(["deviceState"])
  permitted = threading.Event()
  manager = Manager(memory, permitted.is_set, stop)
  try:
    while not stop.wait(.5):
      sm.update(0)
      # The existing road-data scheduler owns its own gates. Routing downloads
      # are deliberately Wi-Fi-only and pause across a drive or active trip.
      safe = (not params.get_bool("IsOnroad") and not params.get("NavDestination") and sm.valid["deviceState"]
              and 0 <= time.monotonic() - sm.recv_time.get("deviceState", 0) <= 3
              and sm["deviceState"].networkType == log.DeviceState.NetworkType.wifi)
      permitted.set() if safe else permitted.clear()
      manager.tick()
  finally:
    manager.close()
