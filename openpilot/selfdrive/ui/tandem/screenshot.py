"""Save what the screen shows, on request, for checking a change on the device from a computer.

`touch /tmp/tandem-screenshot` on the device, and the next frame is saved as /tmp/tandem-screenshot.png (written to a
temporary name, then renamed, so a copy never reads half a file); the request file is removed once it's taken. /tmp is
in memory on the comma, so nothing is written to storage and nothing leaves the device. If the panel reads back
portrait, the picture is turned to the landscape the UI draws.

install() wraps raylib's end_drawing, so the frame is read just before it's presented, with every widget drawn. Reading
the pixels takes a few milliseconds on the drawing thread; turning and compressing them happen on a worker thread.

StarPilot stops drawing while the screen sleeps, so a request wakes it as a touch would (restarting the screen timeout)
and the picture is taken once it has been awake for SETTLE_S, past the first frames after waking.
"""
from __future__ import annotations

import os
import struct
import threading
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

REQUEST = Path("/tmp/tandem-screenshot")
OUTPUT = Path("/tmp/tandem-screenshot.png")
CHECK_S = 0.5   # how often the request file is looked for
SETTLE_S = 1.0  # how long the screen is awake before the picture


def png(pixels: np.ndarray) -> bytes:
  """An 8-bit RGBA PNG of an (height, width, 4) array."""
  height, width, _ = pixels.shape
  rows = np.concatenate([np.zeros((height, 1), np.uint8), pixels.reshape(height, width * 4)], axis=1)   # filter 0 per row

  def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
  header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
  return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)) + chunk(b"IEND", b"")


def landscape(pixels: np.ndarray) -> np.ndarray:
  """The picture as the UI draws it: a portrait read-back turned a quarter clockwise."""
  return np.rot90(pixels, k=-1) if pixels.shape[0] > pixels.shape[1] else pixels


def save(raw: bytes, width: int, height: int, output: Path = OUTPUT) -> None:
  """Turn, compress and write one frame; the rename makes it appear whole."""
  pixels = landscape(np.frombuffer(raw, np.uint8).reshape(height, width, 4))
  partial = output.with_name(output.name + ".partial")
  partial.write_bytes(png(np.ascontiguousarray(pixels)))
  os.replace(partial, output)


class Screenshots:
  """Watches for the request and reads the frame before it's presented."""

  def __init__(self, rl: Any, request: Path = REQUEST, output: Path = OUTPUT, clock: Callable[[], float] = time.monotonic,
               awake: Callable[[], bool] = lambda: True, wake: Callable[[], None] = lambda: None):
    """Makes the watcher.

    Args:
      rl: The raylib binding.
      request: The file that asks for a picture.
      output: Where the picture goes.
      clock: Monotonic seconds.
      awake: Whether the screen is on (StarPilot's device.awake).
      wake: Turns the screen on as a touch would.
    """
    self._rl, self._request, self._output, self._clock = rl, request, output, clock
    self._awake, self._wake = awake, wake
    self._next = 0.0
    self._busy = False
    self._awake_since: float | None = None

  def watch(self) -> None:
    """Off the drawing thread, while the screen sleeps and nothing is drawn: wake it for a waiting request."""
    if self._request.exists() and not self._awake():
      self._wake()

  def before_present(self) -> None:
    """Called each frame just before it's presented; takes a picture when one was asked for."""
    now = self._clock()
    if not self._awake():
      self._awake_since = None
    elif self._awake_since is None:
      self._awake_since = now
    if self._busy or now < self._next or self._awake_since is None or now - self._awake_since < SETTLE_S:
      return
    self._next = now + CHECK_S
    if not self._request.exists():
      return
    image = self._rl.load_image_from_screen()
    try:
      raw = bytes(image.to_bytes(image.width * image.height * 4))
      width, height = image.width, image.height
    finally:
      self._rl.unload_image(image)
    self._request.unlink(missing_ok=True)
    self._busy = True

    def write() -> None:
      try:
        save(raw, width, height, self._output)
      finally:
        self._busy = False
    threading.Thread(target=write, name="tandem-screenshot", daemon=True).start()


def install(rl: Any, wake: bool = False) -> None:
  """Wrap rl.end_drawing once, so every frame passes by the screenshot check.

  Args:
    rl: The raylib binding.
    wake: Watch for requests while the screen sleeps and wake it, through StarPilot's display device (on the device).
  """
  if hasattr(rl, "_tandem_end_drawing"):
    return
  if not wake:
    shots = Screenshots(rl)
  else:
    from openpilot.selfdrive.ui.ui_state import device
    # StarPilot's touch handling restarts the screen timeout this way; it only sets the next timeout time.
    shots = Screenshots(rl, awake=lambda: bool(device.awake), wake=getattr(device, "_reset_interactive_timeout", lambda: None))

    def watch() -> None:
      while True:
        time.sleep(CHECK_S)
        try:
          shots.watch()
        except Exception:
          pass
    threading.Thread(target=watch, name="tandem-screenshot-watch", daemon=True).start()
  rl._tandem_end_drawing = rl.end_drawing

  def end_drawing() -> None:
    try:
      shots.before_present()
    except Exception:   # a screenshot must never stop the UI
      from openpilot.common.swaglog import cloudlog
      cloudlog.exception("Tandem screenshot failed")
    rl._tandem_end_drawing()

  rl.end_drawing = end_drawing
