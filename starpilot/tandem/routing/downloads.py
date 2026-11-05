"""Resumable, checksum-verified catalog downloads with a pause/cancel gate."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import urllib.request

from openpilot.starpilot.tandem.routing import archive, bundles, config as C, verified
from openpilot.starpilot.tandem.routing.tools.manage import HTTPSRedirect


def fetch(url: str, target: Path, size: int, checksum: str, gate=lambda: None, progress=lambda done, total: None, *, checks=None, readonly=False):
  if not url.startswith("https://"):
    raise C.RoutingError("data_incompatible")
  gate()
  target.parent.mkdir(parents=True, exist_ok=True)
  if target.is_symlink():
    raise C.RoutingError("data_incompatible")
  def digest():
    if readonly and target.stat().st_mode & 0o222:
      target.chmod(target.stat().st_mode & ~0o222)
    return checks.digest(target, gate) if checks else bundles.digest(target, gate)
  done = target.stat().st_size if target.exists() else 0
  if done == size:
    if digest() == checksum:
      gate()
      progress(size, size)
      return
    target.unlink()  # a damaged completed cache file must be downloaded again
    done = 0
  if done > size:
    target.unlink()
    done = 0
  if readonly and target.exists() and not target.stat().st_mode & 0o200:
    target.chmod(target.stat().st_mode | 0o200)  # resume an incomplete private download
  failures = 0
  while done < size:
    gate()
    opener = urllib.request.build_opener(HTTPSRedirect())
    headers = {"Range": f"bytes={done}-"} if done else {}
    try:
      with opener.open(urllib.request.Request(url, headers=headers), timeout=15) as response:
        if response.status == 206:
          if not response.headers.get("Content-Range", "").startswith(f"bytes {done}-"):
            raise C.RoutingError("data_incompatible")
        elif response.status == 200:
          done = 0  # Server doesn't support ranges; restart this file safely.
        else:
          raise C.RoutingError("download_failed")
        with target.open("ab" if done else "wb") as stream:
          progress(done, size)
          while True:
            gate()
            chunk = response.read(min(256 * 1024, size - done + 1))
            if not chunk:
              break
            done += len(chunk)
            if done > size:
              raise C.RoutingError("data_incompatible")
            stream.write(chunk)
            stream.flush()
            failures = 0
            progress(done, size)
      if done < size:
        raise OSError("incomplete transfer")
    except OSError:
      failures += 1
      if failures >= 3:
        raise C.RoutingError("download_failed") from None
      # Let the network monitor observe the loss, then its gate waits for
      # Wi-Fi before reopening the connection with a Range request.
      time.sleep(.5)
      gate()
      done = target.stat().st_size if target.exists() else 0
  gate()
  if done != size or digest() != checksum:
    target.unlink(missing_ok=True)
    raise C.RoutingError("data_incompatible")


@dataclass
class Pending:
  package: dict
  data: dict
  ready: Path
  checks: verified.Hashes
  cached: bool = False


def _transfer(package, gate, progress, *, checks=None, reuse=True):
  """Transfer/hash physical files; receipt acceptance and decoding stay serial."""
  checks = checks or verified.Hashes()
  gate()
  opener = urllib.request.build_opener(HTTPSRedirect())
  with opener.open(package["manifest"], timeout=15) as response:
    raw = response.read(65537)
  if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != package["sha256"]:
    raise C.RoutingError("data_incompatible")
  try:
    data = bundles.validate_manifest(json.loads(raw))
  except ValueError:
    raise C.RoutingError("data_incompatible") from None
  if data["id"] != package["id"]:
    raise C.RoutingError("data_incompatible")
  try:
    total = sum(r.get("download", r)["bytes"] for r in data["files"].values())
    if total != package["bytes"]:
      raise ValueError
  except (KeyError, TypeError, ValueError, AttributeError):
    raise C.RoutingError("data_incompatible") from None
  folder = C.root() / "downloads" / package["sha256"]
  folder.mkdir(parents=True, exist_ok=True)
  ready = folder / "ready"
  if folder.is_symlink() or ready.is_symlink():
    raise C.RoutingError("data_incompatible")
  transports = {r.get("download", {}).get("name", n): r.get("download", r) for n, r in data["files"].items()}
  if ready.exists() and reuse:
    try:
      existing = bundles.load(ready)
      if existing.generation == package["sha256"] and verified.read(existing):
        return Pending(package, data, ready, checks, cached=True)
    except C.RoutingError as error:
      if error.code != "data_incompatible":
        raise
  if ready.exists():
    # Preserve complete and partial physical parts across an interrupted job.
    for name in transports:
      source = ready / name
      target = folder / name
      if source.is_file() and not source.is_symlink() and not target.exists():
        source.replace(target)
    shutil.rmtree(ready)  # reclaim interrupted expansion before checking free space
  ready.mkdir()
  already = sum(min((folder / n).stat().st_size, r["bytes"]) for n, r in transports.items() if (folder / n).is_file())
  expanded = sum(r["bytes"] for r in data["files"].values() if "download" in r)
  # Compressed input plus one expanded graph. The ready directory is renamed
  # into place, so installation does not need another expanded copy.
  if shutil.disk_usage(folder).free < total - already + expanded + 256 * 1024**2:
    raise C.RoutingError("no_space")
  (ready / "manifest.json").write_bytes(raw)
  done = 0
  for name, record in data["files"].items():
    transport = record.get("download", record)
    asset = transport.get("name", name)
    url = urllib.parse.urljoin(package["manifest"], transport.get("url", asset))
    target = ready / asset
    if (folder / asset).exists() and not target.exists():
      (folder / asset).replace(target)  # resume the previous cache layout too
    fetch(url, target, transport["bytes"], transport["sha256"], gate,
          lambda n, _total, baseline=done: progress(baseline + n, total), checks=checks,
          readonly=data["schema"] in (3, 4) and name == data["graph"]["file"])
    done += transport["bytes"]
  return Pending(package, data, ready, checks)


def _finish(pending, gate, installing=lambda: None):
  data, ready = pending.data, pending.ready
  gate()
  installing()
  if not pending.cached:
    for name, record in data["files"].items():
      gate()
      if "download" in record:
        source = ready / record["download"]["name"]
        archive.expand(source, ready / name, record, gate)
        source.unlink()
  gate()
  return bundles.verify(ready, gate, checks=pending.checks)


def prepare(package: dict, gate=lambda: None, progress=lambda done, total: None, installing=lambda: None, *, checks=None):
  pending = _transfer(package, gate, progress, checks=checks)
  try:
    result = _finish(pending, gate, installing)
  except C.RoutingError as error:
    if not pending.cached or error.code != "data_incompatible":
      raise
    pending = _transfer(package, gate, progress, reuse=False)
    result = _finish(pending, gate, installing)
  progress(package["bytes"], package["bytes"])
  return result


def prepare_many(packages, gate=lambda: None, progress=lambda done, total: None, *, parts_progress=None):
  """Two bounded transfers; the owner alone gates, publishes and verifies."""
  if not packages:
    progress(0, 0)
    if parts_progress is not None:
      parts_progress({})
    return []
  if len({part["sha256"] for part in packages}) != len(packages):
    raise C.RoutingError("invalid_request")
  stopped, permitted, mutex = threading.Event(), threading.Event(), threading.Lock()
  counts, total, reported = [0] * len(packages), sum(part["bytes"] for part in packages), None
  def update(index, done):
    with mutex:
      counts[index] = done
  def owner_gate():
    nonlocal reported
    permitted.clear()
    gate()
    permitted.set()
    with mutex:
      snapshot = tuple(counts)
    if snapshot != reported:
      progress(sum(snapshot), total)
      if parts_progress is not None:
        parts_progress({part["id"]: done for part, done in zip(packages, snapshot, strict=True)})
      reported = snapshot
  def worker_gate():
    while not stopped.is_set():
      if permitted.wait(.1):
        if not stopped.is_set():
          return
    raise C.RoutingError("interrupted")
  owner_gate()
  executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="routing-download")
  futures, results, remaining = {}, {}, iter(range(len(packages)))
  def submit(index, *, reuse=True):
    futures[executor.submit(_transfer, packages[index], worker_gate,
      lambda done, _total: update(index, done), reuse=reuse)] = index
  try:
    for _ in range(min(2, len(packages))):
      submit(next(remaining))
    while futures:
      owner_gate()
      completed, _ = wait(futures, timeout=.1, return_when=FIRST_COMPLETED)
      for future in completed:
        index = futures.pop(future)
        pending = future.result()
        try:
          results[index] = _finish(pending, owner_gate)
        except C.RoutingError as error:
          if not pending.cached or error.code != "data_incompatible":
            raise
          update(index, 0)
          submit(index, reuse=False)
          continue
        update(index, packages[index]["bytes"])
        next_index = next(remaining, None)
        if next_index is not None:
          submit(next_index)
    owner_gate()
    return [results[index] for index in range(len(packages))]
  finally:
    stopped.set()
    permitted.set()
    executor.shutdown(wait=True, cancel_futures=True)


def install(package: dict, gate=lambda: None, progress=lambda done, total: None, installing=lambda: None, *,
            activate=True, pack_gate=None, activity=None):
  if package.get("kind") == "dataset":
    from openpilot.starpilot.tandem.routing import datasets
    return datasets.install(package, gate, progress, installing, pack_gate=pack_gate, activity=activity)
  checks = verified.Hashes()
  ready = prepare(package, gate, progress, installing, checks=checks)
  folder = ready.folder.parent
  bundle = bundles.install(ready.folder, consume=True, gate=gate, checks=checks)
  shutil.rmtree(folder)
  gate()
  if activate:
    bundles.activate(bundle.id)
  return bundle
