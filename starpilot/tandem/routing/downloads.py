"""Resumable, checksum-verified catalog downloads with a pause/cancel gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

from openpilot.starpilot.tandem.routing import archive, bundles, config as C
from openpilot.starpilot.tandem.routing.tools.manage import HTTPSRedirect


def fetch(url: str, target: Path, size: int, checksum: str, gate=lambda: None, progress=lambda done, total: None):
  if not url.startswith("https://"):
    raise C.RoutingError("data_incompatible")
  gate()
  target.parent.mkdir(parents=True, exist_ok=True)
  done = target.stat().st_size if target.exists() else 0
  if done == size:
    if bundles.digest(target, gate) == checksum:
      gate()
      progress(size, size)
      return
    target.unlink()  # a damaged completed cache file must be downloaded again
    done = 0
  if done > size:
    target.unlink()
    done = 0
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
  if done != size or bundles.digest(target, gate) != checksum:
    target.unlink(missing_ok=True)
    raise C.RoutingError("data_incompatible")


def prepare(package: dict, gate=lambda: None, progress=lambda done, total: None, installing=lambda: None):
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
  if ready.exists():
    try:
      from openpilot.starpilot.tandem.routing import verified
      existing = bundles.load(ready)
      if existing.generation == package["sha256"] and verified.read(existing):
        existing = bundles.verify(ready, gate)
        progress(total, total)
        return existing
    except C.RoutingError as error:
      if error.code != "data_incompatible":
        raise
    # Preserve complete physical parts across an interrupted assembly.
    for name, record in data["files"].items():
      source = ready / name
      target = folder / name
      if "download" not in record and source.is_file() and not source.is_symlink() and not target.exists():
        source.replace(target)
    shutil.rmtree(ready)  # reclaim interrupted expansion before checking free space
  ready.mkdir()
  transports = {r.get("download", {}).get("name", n): r.get("download", r) for n, r in data["files"].items()}
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
    fetch(url, folder / asset, transport["bytes"], transport["sha256"], gate,
          lambda n, _total, baseline=done: progress(baseline + n, total))
    done += transport["bytes"]
  gate()
  installing()
  for name, record in data["files"].items():
    gate()
    if "download" in record:
      archive.expand(folder / record["download"]["name"], ready / name, record, gate)
    else:
      shutil.move(folder / name, ready / name)
  gate()
  return bundles.verify(ready, gate)


def install(package: dict, gate=lambda: None, progress=lambda done, total: None, installing=lambda: None, *, activate=True, pack_gate=None):
  if package.get("kind") == "dataset":
    from openpilot.starpilot.tandem.routing import datasets
    return datasets.install(package, gate, progress, installing, pack_gate=pack_gate)
  ready = prepare(package, gate, progress, installing)
  folder = ready.folder.parent
  bundle = bundles.install(ready.folder, consume=True, gate=gate)
  shutil.rmtree(folder)
  gate()
  if activate:
    bundles.activate(bundle.id)
  return bundle
