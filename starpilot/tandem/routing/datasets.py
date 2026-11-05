"""Exact state selections over one shared build, assembled only while parked."""
from __future__ import annotations

from contextlib import ExitStack
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from openpilot.starpilot.tandem.routing import bundles as B, config as C, downloads, images, tiles as T, verified


def compatible(bundle, dataset):
  return (bundle.manifest.get("kind") == "state-set" and bundle.manifest.get("dataset", {}).get("id") == dataset["id"]
          and bundle.manifest["dataset"]["sha256"] == dataset["sha256"])


def base(dataset):
  candidates = [b for b in B.installed() if compatible(b, dataset) and verified.read(b)]
  return max(candidates, key=lambda b: len(b.manifest["parts"]), default=None)


def selection_id(dataset, selected):
  suffix = hashlib.sha256(json.dumps(sorted(selected)).encode()).hexdigest()[:16]
  return dataset["id"] + "-set-" + suffix


def plan(dataset, selected, *, reuse=True):
  selected = sorted(selected)
  if not set(selected) <= set(dataset["regions"]):
    raise C.RoutingError("invalid_request")
  required = sorted({part for region in selected for part in dataset["regions"][region]["parts"]})
  previous = base(dataset) if reuse and required else None
  present = set(previous.manifest["parts"]) if previous else set()
  missing = [part for part in dataset["parts"] if part["id"] in set(required) - present]
  return {"kind": "dataset", "id": selection_id(dataset, selected), "title": "Offline routes", "regions": selected,
          "bytes": sum(part["bytes"] for part in missing), "parts": required, "missing": missing, "dataset": dataset}


def _checked_index(bundle, dataset):
  index = T.read_index(bundle.folder / "tiles.json", dataset["sha256"])
  allowed = set(bundle.manifest["parts"])
  if any(row["part"] not in allowed or row["offset"] + row["bytes"] > bundle.manifest["graph"]["bytes"] for row in index):
    raise C.RoutingError("data_incompatible")
  return index


def _clear_downloads(keep=None):
  """Caller owns the updater lock; a completed selection needs no input cache."""
  images.release_unused()
  if any(point.is_relative_to(images.mount_root() / "incoming") for point in images._mounts()):
    raise C.RoutingError("busy")
  cache = C.root() / "downloads"
  if cache.exists():
    if keep is None:
      shutil.rmtree(cache)
    else:
      for path in cache.iterdir():
        if path.name not in keep:
          if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
          else:
            path.unlink()


def _replacement_reserve(dataset, required):
  estimate = sum(part["bytes"] for part in dataset["parts"] if part["id"] in required)
  return int(estimate * 1.1) + 64 * 1024**2 + 256 * 1024**2


def _cached_bytes(part):
  folder = C.root() / "downloads" / part["sha256"]
  present = 0
  for name in ("tiles.squashfs", "tiles.json"):
    paths = (folder / name, folder / "ready" / name)
    present += max((path.stat().st_size for path in paths if path.is_file() and not path.is_symlink()), default=0)
  return min(part["bytes"], present)


def install(package, gate=lambda: None, progress=lambda done, total: None, installing=lambda: None, *, pack_gate=None, activity=None):
  C.require_parked()
  C.root().mkdir(parents=True, exist_ok=True)
  with (C.root() / "dataset-update.lock").open("a") as lock:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
      raise C.RoutingError("busy") from None
    # Only this installer owns this directory. Reclaim an image left by a
    # power loss before checking space or resuming the verified part cache.
    staging = C.root() / "downloads/assembled"
    if staging.is_symlink():
      raise C.RoutingError("data_incompatible")
    for abandoned in staging.glob("tmp*"):
      if abandoned.is_dir() and not abandoned.is_symlink():
        shutil.rmtree(abandoned)
    return _install(package, gate, progress, installing, pack_gate=pack_gate, activity=activity)


def _install(package, gate, progress, installing, *, pack_gate, activity):
  C.require_parked()
  dataset, selected = package["dataset"], set(package["regions"])
  if not selected:
    gate()
    with B.lock():
      C.require_parked()
      gate()
      C.atomic_json(C.root() / "active.json", {"id": None, "generation": "", "state_selection": []})
    cleanup()
    _clear_downloads()
    return None
  # Re-plan at execution; a scheduled job may have waited behind another update.
  package = plan(dataset, selected)
  previous = base(dataset)
  if previous is not None:
    try:
      kwargs = {}
      if activity is not None and previous.id == package["id"]:
        size = sum(r["bytes"] for r in previous.manifest["files"].values())
        activity(phase="install", stage="check", done=0, total=size)
        kwargs["physical_progress"] = lambda n, total: activity(phase="install", stage="check", done=n, total=total)
      previous = B.verify(previous.folder, gate, **kwargs)  # full checks before reuse, outside startup
    except C.RoutingError as error:
      if error.code != "data_incompatible":
        raise
      previous = None
      package = plan(dataset, selected, reuse=False)
  if previous and previous.id == package["id"]:
    B.activate(previous.id)
    _clear_downloads()
    cleanup(previous)
    return previous
  required = set(package["parts"])
  _clear_downloads({part["sha256"] for part in package["missing"]})
  remaining = sum(part["bytes"] - _cached_bytes(part) for part in package["missing"])
  if shutil.disk_usage(C.root()).free < remaining + _replacement_reserve(dataset, required):
    raise C.RoutingError("no_space")
  old_rows = _checked_index(previous, dataset) if previous else []
  rows = {row["path"]: row for row in old_rows if row["part"] in required}
  sources = {}
  def report_parts(counts):
    missing = {part["id"]: part["bytes"] for part in package["missing"]}
    regions = {}
    for region in sorted(selected):
      needed = set(dataset["regions"][region]["parts"]) & missing.keys()
      done, total = sum(counts.get(part, 0) for part in needed), sum(missing[part] for part in needed)
      regions[region] = {"done": done, "total": total, "downloaded": done >= total}
    activity(phase="download", stage="", done=sum(counts.values()), total=package["bytes"], region_progress=regions)
  kwargs = {"parts_progress": report_parts} if activity is not None else {}
  incoming_parts = downloads.prepare_many(package["missing"], gate, progress, **kwargs)
  for part, incoming in zip(package["missing"], incoming_parts, strict=True):
    gate()
    if (incoming.manifest.get("kind") != "tile-part" or incoming.manifest["dataset"]["sha256"] != dataset["sha256"]
        or incoming.manifest["parts"] != [part["id"]]):
      raise C.RoutingError("data_incompatible")
    sources[part["id"]] = incoming
    for row in _checked_index(incoming, dataset):
      if row["part"] != part["id"] or row["path"] in rows:
        raise C.RoutingError("data_incompatible")
      rows[row["path"]] = row
  if {row["part"] for row in rows.values()} != required:
    raise C.RoutingError("data_incompatible")
  indexed, length = T.layout(list(rows.values()))
  free = shutil.disk_usage(C.root()).free
  # Reserve space for the compressed replacement, not an expanded tar.
  # Old image stays intact until the new one is verified and atomically active.
  if free < _replacement_reserve(dataset, required):
    raise C.RoutingError("no_space")
  installing()
  if activity is not None:
    activity(phase="install", stage="build", done=0, total=2 * length)
  check = pack_gate or gate
  staging = C.root() / "downloads" / "assembled"
  staging.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(dir=staging) as temporary:
    ready = Path(temporary) / "ready"
    ready.mkdir()
    with ExitStack() as leases:
      leases.callback(images.release_unused)
      old_graph = None
      if previous:
        leases.enter_context(images.reader(previous))
        old_graph = images.graph_path(previous)
      with ExitStack() as incoming_lease:
        current, graph = None, None
        def read(row):
          nonlocal current, graph
          original = rows[row["path"]]
          if row["part"] in sources:
            if current != row["part"]:
              incoming_lease.close()
              current = row["part"]
              graph = incoming_lease.enter_context(images.staged_reader(sources[current]))
            path = graph
          else:
            path = old_graph
          if path is None:
            raise C.RoutingError("data_incompatible")
          yield from T.file_chunks(path, original["offset"], original["bytes"])
        kwargs = {"progress": lambda n, _total: activity(phase="install", stage="build", done=n, total=2 * length)} if activity else {}
        logical = images.pack_stream(T.stream(indexed, read, check), length, ready / "tiles.squashfs", check, **kwargs)
    check()
    if activity is not None:
      activity(phase="install", stage="check", done=length, total=2 * length)
    C.atomic_json(ready / "tiles.json", {"schema": 1, "dataset": dataset["sha256"], "tiles": indexed})
    # Set final permissions before hashing, so identity-bound evidence remains
    # valid through acceptance. No ctime changes are excused by the cache.
    (ready / "tiles.squashfs").chmod(0o444)
    checks = verified.Hashes()
    bounds = [dataset["regions"][region]["bounds"] for region in selected]
    manifest = {"schema": 4, "id": package["id"], "kind": "state-set", "title": "Offline routes", "runtime_version": C.VERSION,
      "source": dataset["source"], "attribution": dataset["attribution"], "built_at": dataset["built_at"],
      "profile": "driving", "regions": sorted(selected), "parts": sorted(required),
      "region_parts": {region: dataset["regions"][region]["parts"] for region in sorted(selected)},
      "dataset": {"id": dataset["id"], "sha256": dataset["sha256"], "index": "tiles.json"},
      "bounds": [min(b[0] for b in bounds), min(b[1] for b in bounds), max(b[2] for b in bounds), max(b[3] for b in bounds)],
      "graph": {"format": "squashfs", "file": "tiles.squashfs", "path": "tiles.tar", **logical},
      "files": {name: {"bytes": (ready / name).stat().st_size, "sha256": checks.digest(ready / name, check)}
                for name in ("tiles.squashfs", "tiles.json")}}
    if dataset.get("sources"):
      manifest["sources"] = dataset["sources"]
    C.atomic_json(ready / "manifest.json", manifest)
    kwargs = {"logical_progress": lambda n, _total: activity(phase="install", stage="check", done=length + n, total=2 * length)} if activity else {}
    bundle = B.install(ready, consume=True, gate=check, checks=checks, **kwargs)
    check()
    B.activate(bundle.id)
  # Completed parts are only a resumable download cache. Their tiles now live
  # in the single compressed image, so permanent storage does not double.
  _clear_downloads()
  cleanup(bundle)
  return bundle


def cleanup(current=None):
  """Retire superseded US sets, including deselected states; reader leases win."""
  try:
    current = current or B.active()
  except C.RoutingError:
    try:
      if json.loads((C.root() / "active.json").read_text()).get("state_selection") != []:
        return
    except (OSError, ValueError, AttributeError):
      return
    current = None
  if current is not None and (current.manifest.get("kind") != "state-set" or not verified.read(current)):
    return
  for folder in B.folders():
    if current is not None and folder.name == current.id:
      continue
    try:
      # Ownership is still readable when a damaged graph fails B.load().
      manifest = B.validate_manifest(json.loads((folder / "manifest.json").read_text()))
      regions = manifest.get("regions", [])
      managed = manifest.get("kind") == "state-set" or any(r.startswith("us_state.") for r in regions)
    except (OSError, ValueError, C.RoutingError):
      managed = False
    if current is None or managed:
      try:
        B.remove(folder.name)
      except C.RoutingError as error:
        if error.code not in ("busy", "park_to_change"):
          raise
