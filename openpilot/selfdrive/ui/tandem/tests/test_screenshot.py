"""Screenshots on request (screenshot.py): the frame before it's presented, as a landscape PNG in /tmp."""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from openpilot.selfdrive.ui.tandem import screenshot


def test_png_round_trips_and_portrait_turns_to_landscape(tmp_path: Path) -> None:
  pixels = np.zeros((4, 2, 4), np.uint8)   # portrait, as the comma's panel reads back
  pixels[0, 0] = (255, 0, 0, 255)          # top left
  out = tmp_path / "shot.png"
  screenshot.save(pixels.tobytes(), 2, 4, out)
  image = Image.open(out)
  assert image.size == (4, 2) and image.mode == "RGBA"
  assert image.getpixel((3, 0)) == (255, 0, 0, 255)   # a quarter turn clockwise: top left goes top right
  assert not out.with_name(out.name + ".partial").exists()
  wide = np.full((2, 3, 4), 7, np.uint8)
  assert screenshot.landscape(wide) is wide


class FakeImage:
  width, height = 3, 2

  def to_bytes(self, size: int) -> bytes:
    return bytes(range(size))


def test_a_request_takes_one_frame_and_is_cleared(tmp_path: Path) -> None:
  unloaded = []
  rl = SimpleNamespace(load_image_from_screen=FakeImage, unload_image=unloaded.append)
  request, output = tmp_path / "request", tmp_path / "shot.png"
  now = [0.0]
  shots = screenshot.Screenshots(rl, request, output, clock=lambda: now[0])
  shots.before_present()
  assert not output.exists()                 # nothing asked
  request.touch()
  shots.before_present()
  assert request.exists()                    # looked for at most every CHECK_S
  now[0] = max(screenshot.CHECK_S, screenshot.SETTLE_S)
  shots.before_present()
  assert not request.exists() and len(unloaded) == 1
  deadline = time.monotonic() + 5
  while not output.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
  assert Image.open(output).size == (3, 2)


def test_install_wraps_end_drawing_once_and_a_failure_never_stops_the_frame(monkeypatch) -> None:
  presented = []
  rl = SimpleNamespace(end_drawing=lambda: presented.append(True))
  monkeypatch.setattr(screenshot.Screenshots, "before_present", lambda self: 1 / 0)
  logged = []
  monkeypatch.setitem(__import__("sys").modules, "openpilot.common.swaglog", SimpleNamespace(cloudlog=SimpleNamespace(exception=logged.append)))
  screenshot.install(rl)
  first = rl.end_drawing
  screenshot.install(rl)
  assert rl.end_drawing is first
  rl.end_drawing()
  assert presented == [True] and logged == ["Tandem screenshot failed"]


def test_a_sleeping_screen_is_woken_and_settles_before_the_picture(tmp_path: Path) -> None:
  rl = SimpleNamespace(load_image_from_screen=FakeImage, unload_image=lambda image: None)
  request, output = tmp_path / "request", tmp_path / "shot.png"
  now, awake, woken = [0.0], [False], []
  shots = screenshot.Screenshots(rl, request, output, clock=lambda: now[0], awake=lambda: awake[0], wake=lambda: woken.append(now[0]))
  request.touch()
  shots.watch()
  assert woken == [0.0]                      # asleep: wake it, as a touch would
  awake[0] = True
  shots.before_present()                     # first frame awake
  now[0] = screenshot.SETTLE_S / 2
  shots.before_present()
  assert request.exists()                    # still settling
  now[0] = screenshot.SETTLE_S
  shots.before_present()
  assert not request.exists()
  shots.watch()
  assert woken == [0.0]                      # nothing waiting: left alone

