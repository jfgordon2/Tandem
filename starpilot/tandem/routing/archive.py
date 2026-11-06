"""Bounded zstd transport for a plain, memory-mapped installed graph tar."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess

from openpilot.starpilot.tandem.routing import config as C

CHUNK = 256 * 1024
WINDOW = 64 * 1024**2


def _frame(path: Path, size: int) -> None:
  """Our format is one sized, checksummed frame without a dictionary.

  Check its block boundaries too: streaming zstd readers accept an unfinished
  frame after emitting all content, so output length/hash alone miss that case.
  """
  with path.open("rb") as stream:
    # Zstandard format specification: frame descriptor, optional window and
    # dictionary ID, then the content size. Our builder always includes size/CRC.
    # https://github.com/facebook/zstd/blob/dev/doc/zstd_compression_format.md
    def integer(count):
      value = stream.read(count)
      if len(value) != count:
        raise C.RoutingError("data_incompatible")
      return int.from_bytes(value, "little")
    if stream.read(4) != b"\x28\xb5\x2f\xfd":
      raise C.RoutingError("data_incompatible")
    descriptor = integer(1)
    single = bool(descriptor & 32)
    if descriptor & 24 or not descriptor & 4:
      raise C.RoutingError("data_incompatible")
    window = 0
    if not single:
      value = integer(1)
      base = 1 << (10 + (value >> 3))
      window = base + (base >> 3) * (value & 7)
    dictionary = integer((0, 1, 2, 4)[descriptor & 3])
    field = (1 if single else 0, 2, 4, 8)[descriptor >> 6]
    content = integer(field) + (256 if field == 2 else 0)
    if not field or content != size or dictionary or (content if single else window) > WINDOW:
      raise C.RoutingError("data_incompatible")
    length = path.stat().st_size
    while True:
      block = stream.read(3)
      if len(block) != 3:
        raise C.RoutingError("data_incompatible")
      value = int.from_bytes(block, "little")
      kind, count, last = (value >> 1) & 3, value >> 3, value & 1
      if kind == 3 or count > 128 * 1024:
        raise C.RoutingError("data_incompatible")
      stream.seek(1 if kind == 1 else count, 1)
      if stream.tell() > length:
        raise C.RoutingError("data_incompatible")
      if last:
        if stream.tell() + 4 != length:
          raise C.RoutingError("data_incompatible")
        return


@contextmanager
def _reader(source: Path):
  try:
    import zstandard as zstd
  except ImportError:
    # AGNOS includes the native command even when its system Python lacks the
    # optional module. A pipe bounds memory and applies backpressure while paused.
    decoder = shutil.which("zstd")
    if decoder is None:
      raise C.RoutingError("data_incompatible") from None
    with subprocess.Popen([decoder, "-q", "-d", "-c", f"-M{WINDOW}", "--", str(source)],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
      try:
        yield process.stdout
        if process.wait(timeout=10):
          raise C.RoutingError("data_incompatible")
      finally:
        if process.poll() is None:
          process.terminate()
          try:
            process.wait(timeout=3)
          except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
  else:
    try:
      with source.open("rb") as stream, zstd.ZstdDecompressor(max_window_size=WINDOW).stream_reader(stream) as reader:
        yield reader
    except zstd.ZstdError:
      raise C.RoutingError("data_incompatible") from None


def expand(source: Path, target: Path, record: dict, gate=lambda: None) -> None:
  partial = target.with_name(target.name + ".partial")
  try:
    gate()
    _frame(source, record["bytes"])
    count, checksum = 0, hashlib.sha256()
    with partial.open("wb") as output:
      with _reader(source) as reader:
        while True:
          gate()
          chunk = reader.read(min(CHUNK, record["bytes"] - count + 1))
          if not chunk:
            break
          count += len(chunk)
          if count > record["bytes"]:
            raise C.RoutingError("data_incompatible")
          checksum.update(chunk)
          output.write(chunk)
    if count != record["bytes"] or checksum.hexdigest() != record["sha256"]:
      raise C.RoutingError("data_incompatible")
    gate()
    partial.replace(target)
  finally:
    partial.unlink(missing_ok=True)


def compress(source: Path, target: Path) -> dict:
  """Off-device only. Return transport metadata; leave installed bytes intact."""
  import zstandard as zstd
  with source.open("rb") as stream, target.open("wb") as output:
    zstd.ZstdCompressor(level=6, threads=2, write_checksum=True).copy_stream(stream, output, size=source.stat().st_size)
  from openpilot.starpilot.tandem.routing.bundles import digest
  return {"encoding": "zstd", "name": target.name, "bytes": target.stat().st_size, "sha256": digest(target)}
