"""Indexed native extract: startup reads one small index, not every tile header."""
from __future__ import annotations

import io
from pathlib import Path
import struct
import tarfile

from openpilot.starpilot.tandem.routing import config as C


def write(tiles: Path, target: Path) -> None:
  paths = sorted(tiles.rglob("*.gph"))
  if not paths:
    raise C.RoutingError("data_missing")
  entries = []
  with tarfile.open(target, "w", format=tarfile.USTAR_FORMAT) as archive:
    index = tarfile.TarInfo("index.bin")
    index.size = len(paths) * 16
    archive.addfile(index, io.BytesIO(bytes(index.size)))
    index_offset = 512
    for path in paths:
      relative = path.relative_to(tiles)
      level, *parts = relative.with_suffix("").parts
      tile = int("".join(parts))
      if int(level) not in (0, 1, 2) or not 0 <= tile < 2**22:
        raise C.RoutingError("data_incompatible")
      graph_id = tile * 8 + int(level)
      info = archive.gettarinfo(str(path), str(relative))
      info.uid = info.gid = info.mtime = 0
      info.uname = info.gname = ""
      entries.append((archive.offset + 512, graph_id, info.size))
      with path.open("rb") as stream:
        archive.addfile(info, stream)
  with target.open("r+b") as stream:
    stream.seek(index_offset)
    for entry in entries:
      stream.write(struct.pack("<QII", *entry))
