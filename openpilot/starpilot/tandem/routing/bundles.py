"""Immutable, checksummed graph bundles, atomic activation, and native-reader leases."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from collections.abc import Iterator
from typing import TYPE_CHECKING

from openpilot.starpilot.tandem.routing import config as C, images, verified

if TYPE_CHECKING:
  from openpilot.starpilot.tandem.routing.verified import Hashes

ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


def digest(path: Path, gate: C.Gate = lambda: None, *, progress: C.Progress | None = None) -> str:
  """The file's SHA-256, read in chunks, calling gate between them and reporting progress."""
  checksum = hashlib.sha256()
  done, total = 0, path.stat().st_size if progress is not None else 0
  if progress is not None:
    progress(0, total)
  with path.open("rb") as stream:
    while True:
      gate()
      chunk = stream.read(1024**2)
      if not chunk:
        break
      checksum.update(chunk)
      done += len(chunk)
      if progress is not None:
        progress(done, total)
  return checksum.hexdigest()


def validate_manifest(data: dict) -> dict:
  """Validate installed files separately from their optional compressed transport."""
  try:
    if (type(data["schema"]) is not int or data["schema"] not in (1, 2, 3, 4)
        or not ID.fullmatch(data["id"]) or data["runtime_version"] != C.VERSION):
      raise ValueError
    bounds = data["bounds"]
    if (len(bounds) != 4 or not all(type(v) in (int, float) for v in bounds)
        or not -180 <= bounds[0] < bounds[2] <= 180 or not -90 <= bounds[1] < bounds[3] <= 90):
      raise ValueError
    if not data.get("source") or not data.get("attribution"):
      raise ValueError
    if data["schema"] in (3, 4):
      graph = data["graph"]
      expected = {graph["file"]}
      if data["schema"] == 4:
        dataset = data["dataset"]
        if (not ID.fullmatch(dataset["id"]) or not re.fullmatch("[a-f0-9]{64}", dataset["sha256"])
            or dataset["index"] != "tiles.json" or not isinstance(data["parts"], list) or not data["parts"]
            or len(set(data["parts"])) != len(data["parts"]) or not all(ID.fullmatch(p) for p in data["parts"])):
          raise ValueError
        if data.get("kind") not in ("tile-part", "state-set") or graph["file"] == dataset["index"]:
          raise ValueError
        if data["kind"] == "state-set":
          regions = data["regions"]
          if (not regions or len(set(regions)) != len(regions) or set(data["region_parts"]) != set(regions)
              or any(not re.fullmatch(r"us_state\.[A-Z]{2}", region) or not data["region_parts"][region]
                     or not set(data["region_parts"][region]) <= set(data["parts"]) for region in regions)):
            raise ValueError
        expected.add(dataset["index"])
      if (graph["format"] != "squashfs" or graph["path"] != "tiles.tar" or set(data["files"]) != expected
          or type(graph["bytes"]) is not int or graph["bytes"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", graph["sha256"])):
        raise ValueError
    elif "tiles.tar" not in data["files"]:
      raise ValueError
    names = set(data["files"])
    for name, record in data["files"].items():
      if (not ID.fullmatch(name) or type(record["bytes"]) is not int or record["bytes"] <= 0
          or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
        raise ValueError
      if "download" in record:
        transport = record["download"]
        if (data["schema"] != 2 or transport["encoding"] != "zstd" or not ID.fullmatch(transport["name"])
            or transport["name"] in names or type(transport["bytes"]) is not int or transport["bytes"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", transport["sha256"])):
          raise ValueError
        names.add(transport["name"])
    return data
  except (ValueError, KeyError, TypeError, AttributeError):
    raise C.RoutingError("data_incompatible") from None


@dataclass(frozen=True)
class Bundle:
  """An installed routing graph: its folder, manifest, and generation (the manifest's checksum)."""
  folder: Path
  manifest: dict
  generation: str

  @property
  def id(self) -> str:
    return str(self.manifest["id"])

  def covers(self, lat: float, lon: float) -> bool:
    west, south, east, north = self.manifest["bounds"]
    return bool(south <= lat <= north and west <= lon <= east)


def load(folder: Path, verify: bool = False, gate: C.Gate = lambda: None, *, logical: bool = True, checks: Hashes | None = None,
         logical_progress: C.Progress | None = None, physical_progress: C.Progress | None = None) -> Bundle:
  """Loads the bundle in folder, checking its files against the manifest.

  Args:
    folder: The bundle's folder.
    verify: Check every file's checksum too, not just its size.
    gate: Called between steps to stop.
    logical: With verify, also check the graph image's contents.
    checks: Checksums already taken in this operation, reused.
    logical_progress: Reports the graph check's progress.
    physical_progress: Reports the checksums' progress.

  Raises:
    RoutingError: data_incompatible when anything doesn't match.
  """
  try:
    manifest_path = folder / "manifest.json"
    if folder.is_symlink() or manifest_path.is_symlink():
      raise C.RoutingError("data_incompatible")
    data = validate_manifest(json.loads(manifest_path.read_text()))
    done, total = 0, sum(r["bytes"] for r in data["files"].values())
    for name, record in data["files"].items():
      if not ID.fullmatch(name) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
        raise C.RoutingError("data_incompatible")
      path = folder / name
      if type(record["bytes"]) is not int or record["bytes"] <= 0:
        raise C.RoutingError("data_incompatible")
      if path.is_symlink() or not path.is_file() or path.stat().st_size != record["bytes"]:
        raise C.RoutingError("data_incompatible")
      if verify:
        report = (lambda n, _total, baseline=done: physical_progress(baseline + n, total)) if physical_progress else None
        value = checks.digest(path, gate) if checks else digest(path, gate, **({"progress": report} if report else {}))
        if value != record["sha256"]:
          raise C.RoutingError("data_incompatible")
        done += record["bytes"]
        if physical_progress is not None:
          physical_progress(done, total)
    if verify and logical and data["schema"] in (3, 4):
      images.verify_graph(folder, data, gate, **({"progress": logical_progress} if logical_progress is not None else {}))
    return Bundle(folder, data, digest(manifest_path, gate))
  except (OSError, ValueError, KeyError, TypeError):
    raise C.RoutingError("data_incompatible") from None


def folders() -> list[Path]:
  """Include damaged bundles so explicit map removal can still reclaim them."""
  return [path for path in sorted((C.root() / "bundles").glob("*"))
          if ID.fullmatch(path.name) and path.is_dir() and not path.is_symlink()]


def installed() -> list[Bundle]:
  result = []
  for folder in folders():
    try:
      result.append(load(folder))
    except C.RoutingError:
      continue
  return result


def routing_bundles() -> list[Bundle]:
  """A committed state set is authoritative, even while an old lease drains."""
  present = installed()
  try:
    selected = json.loads((C.root() / "active.json").read_text())
    if "state_selection" in selected:
      return [bundle for bundle in present if bundle.id == selected["id"] and bundle.generation == selected["generation"]]
  except (OSError, ValueError, KeyError, TypeError):
    pass
  # Shared sets are usable only through their committed exact-selection
  # pointer. A missing/corrupt pointer must not resurrect a retired state.
  return [bundle for bundle in present if bundle.manifest.get("kind") != "state-set"]


def verify(folder: Path, gate: C.Gate = lambda: None, *, checks: Hashes | None = None, logical_progress: C.Progress | None = None,
           physical_progress: C.Progress | None = None) -> Bundle:
  """Explicit full check; never invoked by the route worker's startup path."""
  C.require_parked()
  bundle = load(folder)
  if images.is_image(bundle):
    path = images.source(bundle)
    if path.stat().st_mode & 0o222:
      path.chmod(path.stat().st_mode & ~0o222)
  before = verified.files(bundle)
  try:
    checked = load(folder, verify=True, gate=gate, logical=not bool(verified.read(bundle)), checks=checks,
                   logical_progress=logical_progress, physical_progress=physical_progress)
    if checked.generation != bundle.generation:
      raise C.RoutingError("data_incompatible")
    for name in (*checked.manifest["files"], "manifest.json"):
      with (folder / name).open("rb") as stream:
        os.fsync(stream.fileno())
    verified.write(checked, before)
    return checked
  except C.RoutingError as error:
    if error.code == "data_incompatible":
      verified.invalidate(bundle)
    raise
  except OSError:
    verified.invalidate(bundle)
    raise C.RoutingError("data_incompatible") from None
  finally:
    if hasattr(os, "posix_fadvise"):
      for name in bundle.manifest["files"]:
        try:
          with (folder / name).open("rb") as stream:
            os.posix_fadvise(stream.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
        except OSError:
          pass


def active() -> Bundle:
  """The bundle active.json selects. Raises RoutingError data_missing when none is, data_incompatible when it's damaged."""
  try:
    selection = json.loads((C.root() / "active.json").read_text())
    if not ID.fullmatch(selection["id"]):
      raise C.RoutingError("data_incompatible")
    folder = C.root() / "bundles" / selection["id"]
    if folder.is_symlink():
      raise C.RoutingError("data_incompatible")
    bundle = load(folder)
    if bundle.generation != selection["generation"]:
      raise C.RoutingError("data_incompatible")
    return bundle
  except FileNotFoundError:
    raise C.RoutingError("data_missing") from None
  except (OSError, ValueError, KeyError, TypeError):
    raise C.RoutingError("data_incompatible") from None


def selected(message: dict) -> Bundle:
  """The bundle a request names, or the active one when it names none."""
  identity = message.get("bundle")
  if identity is None:
    return active()  # existing benchmark/protocol callers
  if not isinstance(identity, str) or not ID.fullmatch(identity):
    raise C.RoutingError("invalid_request")
  active_selection = None
  try:
    active_selection = json.loads((C.root() / "active.json").read_text())
    if "state_selection" in active_selection and active_selection.get("id") != identity:
      raise C.RoutingError("superseded")
  except (OSError, ValueError, TypeError):
    pass
  bundle = load(C.root() / "bundles" / identity)
  if bundle.manifest.get("kind") == "state-set" and (not isinstance(active_selection, dict) or "state_selection" not in active_selection
      or active_selection.get("id") != bundle.id or active_selection.get("generation") != bundle.generation):
    raise C.RoutingError("superseded")
  return bundle


def for_trip(start: tuple[float, float, float | None], destination: dict) -> Bundle:
  """A verified bundle covering both ends of a trip. Raises RoutingError when none covers them."""
  candidates = [b for b in routing_bundles() if b.covers(start[0], start[1]) and
                b.covers(destination["latitude"], destination["longitude"])]
  if not candidates:
    raise C.RoutingError("outside_coverage" if installed() else "data_missing")
  candidates = [b for b in candidates if verified.read(b)]
  if not candidates:
    raise C.RoutingError("data_incompatible")
  # Use one connected graph per request; never stitch unrelated extracts.
  return max(candidates, key=lambda b: (b.manifest.get("built_at", ""),
                                      -sum(r["bytes"] for r in b.manifest["files"].values())))


@contextmanager
def lock() -> Iterator[None]:
  C.root().mkdir(parents=True, exist_ok=True)
  with (C.root() / ".install.lock").open("a") as stream:
    fcntl.flock(stream, fcntl.LOCK_EX)
    yield


def activate(bundle_id: str) -> Bundle:
  """Makes an installed, verified bundle the active one, while parked."""
  C.require_parked()
  if not ID.fullmatch(bundle_id):
    raise C.RoutingError("invalid_request")
  with lock():
    bundle = load(C.root() / "bundles" / bundle_id)
    if not verified.read(bundle):
      bundle = verify(bundle.folder)
    try:
      previous = json.loads((C.root() / "active.json").read_text())
    except (OSError, ValueError):
      previous = None
    selection = {"id": bundle.id, "generation": bundle.generation, "previous": previous}
    if bundle.manifest.get("kind") == "state-set":
      selection["state_selection"] = bundle.manifest["regions"]
      selection["previous"] = None
    C.atomic_json(C.root() / "active.json", selection)
  return bundle


def install(source: Path, *, consume: bool = False, gate: C.Gate = lambda: None, checks: Hashes | None = None,
            logical_progress: C.Progress | None = None) -> Bundle:
  """Installs a downloaded bundle from source, verified, into the bundles folder.

  Args:
    source: The downloaded bundle's folder.
    consume: Move the files rather than copy them.
    gate: Called between steps to stop.
    checks: Checksums already taken in this operation, reused.
    logical_progress: Reports the graph check's progress.
  """
  C.require_parked()
  bundle = verify(source, gate, checks=checks, logical_progress=logical_progress)
  if consume and not source.resolve().is_relative_to((C.root() / "downloads").resolve()):
    raise C.RoutingError("invalid_request")
  target = C.root() / "bundles" / bundle.id
  with lock():
    target.parent.mkdir(parents=True, exist_ok=True)
    repair = False
    if target.exists():
      if target.is_symlink() or (target / "manifest.json").is_symlink() or digest(target / "manifest.json") != bundle.generation:
        raise C.RoutingError("bundle_exists")
      try:
        existing = load(target)
        if verified.read(existing):
          return existing
        return verify(target, gate)
      except C.RoutingError as error:
        if error.code != "data_incompatible":
          raise
        repair = True  # same immutable manifest; replace damaged stored bytes
    size = 0 if consume else sum(record["bytes"] for record in bundle.manifest["files"].values())
    if shutil.disk_usage(target.parent).free < size + 256 * 1024**2:
      raise C.RoutingError("no_space")
    staging = C.root() / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(dir=staging) as temporary:
      ready = source if consume else Path(temporary) / "ready"
      if not consume:
        ready.mkdir()
        for name in (*bundle.manifest["files"], "manifest.json"):
          gate()
          shutil.copyfile(source / name, ready / name)
        verify(ready, gate)
      gate()
      C.require_parked()
      if repair:
        with (target / ".lease").open("a") as lease:
          try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
          except BlockingIOError:
            raise C.RoutingError("busy") from None
          images.unmount_id(bundle.id)
          previous = Path(temporary) / "damaged"
          target.replace(previous)
          try:
            ready.replace(target)
          except OSError:
            previous.replace(target)
            raise
      else:
        ready.replace(target)
      verified.sync_directory(target.parent)
  return load(target)


def remove(bundle_id: str) -> None:
  """Removes an inactive bundle, while parked."""
  C.require_parked()
  if not ID.fullmatch(bundle_id):
    raise C.RoutingError("invalid_request")
  with lock():
    folder = C.root() / "bundles" / bundle_id
    if folder.is_symlink():
      raise C.RoutingError("data_incompatible")
    if not folder.is_dir():
      raise C.RoutingError("data_missing")
    with (folder / ".lease").open("a") as stream:
      try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
      except BlockingIOError:
        raise C.RoutingError("busy") from None
      images.unmount_id(bundle_id)
      try:
        selection = json.loads((C.root() / "active.json").read_text())
        if selection.get("id") == bundle_id:
          (C.root() / "active.json").unlink()
      except (FileNotFoundError, ValueError, AttributeError):
        pass
      shutil.rmtree(folder)


def capability() -> dict:
  """Whether offline routing can route now: ready with the generation of the installed data, or the reason it can't."""
  if not C.enabled():
    return {"status": "disabled", "generation": ""}
  if not C.runtime_ready():
    return {"status": "runtime_missing", "generation": ""}
  try:
    present = routing_bundles()
    available = [b for b in present if verified.read(b)]
    if not available:
      raise C.RoutingError("data_incompatible" if present else "data_missing")
    try:
      bundle = active()
      verified.require(bundle)
    except C.RoutingError:
      bundle = available[0]
    generation = hashlib.sha256("".join(b.generation for b in available).encode()).hexdigest()
    return {"status": "ready", "generation": generation, "id": bundle.id, "title": bundle.manifest.get("title", bundle.id)}
  except C.RoutingError as error:
    return {"status": error.code, "generation": ""}
