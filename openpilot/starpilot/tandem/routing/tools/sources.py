"""Resumable, checked off-device source download with four bounded range streams."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request

from openpilot.starpilot.tandem.routing import config as C


def fetch(url: str, target: Path, *, workers=4):
  if not url.startswith("https://") or not 1 <= workers <= 4:
    raise C.RoutingError("invalid_request")
  target.parent.mkdir(parents=True, exist_ok=True)
  receipt = target.with_name(target.name + ".source.json")
  if target.exists() and receipt.exists():
    # Dated source snapshots are immutable. A checked local receipt lets a
    # long build resume without depending on the source host being online.
    previous = json.loads(receipt.read_text())
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    count = 0
    with target.open("rb") as stream:
      while block := stream.read(1024**2):
        md5.update(block)
        sha.update(block)
        count += len(block)
    if (previous.get("url") != url or previous.get("bytes") != count or previous.get("md5") != md5.hexdigest()
        or previous.get("sha256") != sha.hexdigest()):
      raise C.RoutingError("data_incompatible")
    return previous
  with urllib.request.urlopen(url + ".md5", timeout=60) as response:
    checksum = response.read(1024).decode().split()[0]
  if not re.fullmatch("[a-fA-F0-9]{32}", checksum):
    raise C.RoutingError("data_incompatible")
  with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as response:
    size = int(response.headers["Content-Length"])
  if size <= 0:
    raise C.RoutingError("data_incompatible")
  journal = target.with_name(target.name + ".ranges.json")
  prefix = target.with_name(target.name + ".part")
  if not target.exists():
    if journal.exists():
      state = json.loads(journal.read_text())
      if state["url"] != url or state["bytes"] != size or state["md5"] != checksum:
        raise C.RoutingError("data_incompatible")
    else:
      prefix.touch(exist_ok=True)
      length = prefix.stat().st_size
      if length > size:
        raise C.RoutingError("data_incompatible")
      width = max(1, (size - length + workers - 1) // workers)
      state = {"url": url, "bytes": size, "md5": checksum, "prefix": length,
               "ranges": [[start, min(start + width, size)] for start in range(length, size, width)]}
      C.atomic_json(journal, state)
    if prefix.stat().st_size != state["prefix"]:
      raise C.RoutingError("data_incompatible")
    def download(item):
      index, (start, end) = item
      path = target.with_name(target.name + f".range-{index}")
      done = path.stat().st_size if path.exists() else 0
      if done > end - start:
        raise C.RoutingError("data_incompatible")
      failures = 0
      while done < end - start:
        try:
          request = urllib.request.Request(url, headers={"Range": f"bytes={start + done}-{end - 1}"})
          with urllib.request.urlopen(request, timeout=60) as response, path.open("ab") as out:
            if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start + done}-{end - 1}/"):
              raise C.RoutingError("data_incompatible")
            while done < end - start:
              block = response.read(min(1024**2, end - start - done))
              if not block:
                raise OSError("incomplete source range")
              out.write(block)
              out.flush()
              done += len(block)
              failures = 0
              if done % (128 * 1024**2) < len(block):
                print(json.dumps({"source_range": index, "done": done, "bytes": end - start}), flush=True)
        except OSError:
          failures += 1
          if failures >= 5:
            raise
          time.sleep(1)
          done = path.stat().st_size if path.exists() else 0
      return path
    with ThreadPoolExecutor(max_workers=workers) as pool:
      paths = [prefix, *pool.map(download, enumerate(state["ranges"]))]
    joined = target.with_name(target.name + ".joining")
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    total = 0
    with joined.open("wb") as out:
      for path in paths:
        with path.open("rb") as source:
          while block := source.read(1024**2):
            md5.update(block)
            sha.update(block)
            total += len(block)
            out.write(block)
    if total != size or md5.hexdigest() != checksum.lower():
      joined.unlink()
      raise C.RoutingError("data_incompatible")
    joined.replace(target)
    for path in paths:
      path.unlink()
    journal.unlink()
  else:
    md5, sha = hashlib.md5(usedforsecurity=False), hashlib.sha256()
    total = 0
    with target.open("rb") as source:
      while block := source.read(1024**2):
        md5.update(block)
        sha.update(block)
        total += len(block)
    if total != size or md5.hexdigest() != checksum.lower():
      raise C.RoutingError("data_incompatible")
  result = {"url": url, "bytes": size, "md5": checksum.lower(), "sha256": sha.hexdigest()}
  C.atomic_json(receipt, result)
  return result


def merge(inputs, target: Path):
  """Deduplicate same-snapshot extracts before the single native graph build."""
  from openpilot.starpilot.tandem.routing.bundles import digest
  identity = [receipt["sha256"] for _, receipt in inputs]
  receipt = target.with_name(target.name + ".merge.json")
  if target.exists() and receipt.exists():
    result = json.loads(receipt.read_text())
    if result["inputs"] != identity or result["sha256"] != digest(target):
      raise C.RoutingError("data_incompatible")
    return result
  tool = shutil.which("osmium")
  if tool is None:
    raise C.RoutingError("data_missing")
  temporary = target.with_name(target.stem + ".pending.osm.pbf")
  subprocess.run([tool, "merge", *(str(path) for path, _ in inputs), "--output", str(temporary), "--overwrite", "--fsync"], check=True)
  result = {"inputs": identity, "bytes": temporary.stat().st_size, "sha256": digest(temporary),
            "tool": subprocess.check_output([tool, "--version"], text=True).splitlines()[0]}
  temporary.replace(target)
  C.atomic_json(receipt, result)
  return result
