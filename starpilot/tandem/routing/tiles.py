"""Deterministic indexed extracts assembled with bounded tile-data buffers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile
from collections.abc import Callable
from collections.abc import Iterable, Iterator

from openpilot.starpilot.tandem.routing import config as C

PATH = re.compile(r"([012])/((?:[0-9]{3}/)*[0-9]{3})\.gph\Z")
SHA = re.compile("[a-f0-9]{64}\\Z")
MAX_INDEX = 32 * 1024**2
MAX_TILE = 256 * 1024**2
BLOCK = 256 * 1024


def graph_id(name: str) -> int:
  match = PATH.fullmatch(name)
  if not match:
    raise C.RoutingError("data_incompatible")
  level, number = int(match[1]), int(match[2].replace("/", ""))
  if number >= (360 // (4, 1, .25)[level]) * (180 // (4, 1, .25)[level]):
    raise C.RoutingError("data_incompatible")
  return number * 8 + level


def padded(size: int, block: int = 512) -> int:
  return (size + block - 1) // block * block


def header(name: str, size: int) -> bytes:
  info = tarfile.TarInfo(name)
  info.size, info.mode = size, 0o644
  return info.tobuf(format=tarfile.USTAR_FORMAT)


def layout(records: list[dict]) -> tuple[list[dict], int]:
  """Where each tile goes in the extract, by part and path, and the extract's size."""
  result, seen = [], set()
  offset = 512 + padded(len(records) * 16)
  for record in sorted(records, key=lambda row: (row["part"], row["path"])):
    identity = graph_id(record["path"])
    if identity in seen:
      raise C.RoutingError("data_incompatible")
    seen.add(identity)
    result.append({**record, "offset": offset + 512})
    offset += 512 + padded(record["bytes"])
  if not result:
    raise C.RoutingError("data_missing")
  return result, padded(offset + 1024, tarfile.RECORDSIZE)


def read_index(path: Path, dataset: str) -> list[dict]:
  """A part's tile index, checked against its dataset."""
  try:
    if path.is_symlink() or path.stat().st_size > MAX_INDEX:
      raise ValueError
    value = json.loads(path.read_text())
    if value["schema"] != 1 or value["dataset"] != dataset or not isinstance(value["tiles"], list) or not 0 < len(value["tiles"]) <= 100_000:
      raise ValueError
    seen, result = set(), []
    for row in value["tiles"]:
      identity = graph_id(row["path"])
      if (identity in seen or type(row["bytes"]) is not int or not 0 < row["bytes"] <= MAX_TILE
          or not SHA.fullmatch(row["sha256"]) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}", row["part"])
          or type(row["offset"]) is not int or row["offset"] < 512 or row["offset"] % 512):
        raise ValueError
      seen.add(identity)
      result.append({key: row[key] for key in ("path", "bytes", "sha256", "part", "offset")})
    return result
  except (OSError, ValueError, KeyError, TypeError, AttributeError):
    raise C.RoutingError("data_incompatible") from None


def stream(records: list[dict], read: Callable[[dict], Iterable[bytes]], gate: C.Gate = lambda: None) -> Iterator[bytes]:
  """Yield a canonical tar; read(row) yields only that tile's bytes."""
  index = b"".join(struct.pack("<QII", row["offset"], graph_id(row["path"]), row["bytes"]) for row in records)
  yield header("index.bin", len(index))
  yield index
  yield bytes(padded(len(index)) - len(index))
  written = 512 + padded(len(index))
  for row in records:
    gate()
    if row["offset"] != written + 512:
      raise C.RoutingError("data_incompatible")
    yield header(row["path"], row["bytes"])
    digest, count = hashlib.sha256(), 0
    iterator = iter(read(row))
    try:
      for chunk in iterator:
        gate()
        count += len(chunk)
        if len(chunk) > BLOCK or count > row["bytes"]:
          raise C.RoutingError("data_incompatible")
        digest.update(chunk)
        yield chunk
    finally:
      close = getattr(iterator, "close", None)
      if close is not None:
        close()
    if count != row["bytes"] or digest.hexdigest() != row["sha256"]:
      raise C.RoutingError("data_incompatible")
    yield bytes(padded(count) - count)
    written += 512 + padded(count)
  yield bytes(padded(written + 1024, tarfile.RECORDSIZE) - written)


def file_chunks(path: Path, offset: int, size: int) -> Iterator[bytes]:
  """size bytes of path from offset, in bounded chunks."""
  with path.open("rb") as source:
    source.seek(offset)
    while size:
      chunk = source.read(min(BLOCK, size))
      if not chunk:
        raise C.RoutingError("data_incompatible")
      size -= len(chunk)
      yield chunk
