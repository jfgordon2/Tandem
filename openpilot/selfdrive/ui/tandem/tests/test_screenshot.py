"""Screenshots on request (screenshot.py): the frame drawn offscreen, read back, then shown as usual."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from openpilot.selfdrive.ui.tandem import screenshot


def test_png_round_trips_and_texture_rows_come_back_upright(tmp_path: Path) -> None:
  pixels = np.zeros((2, 4, 4), np.uint8)
  pixels[0, 0] = (255, 0, 0, 255)          # a texture's first row is the picture's bottom row
  out = tmp_path / "shot.png"
  screenshot.save(pixels.tobytes(), 4, 2, out)
  image = Image.open(out)
  assert image.size == (4, 2) and image.mode == "RGBA"
  assert image.getpixel((0, 1)) == (255, 0, 0, 255)
  assert not out.with_name(out.name + ".partial").exists()


def test_a_portrait_read_back_turns_to_landscape() -> None:
  tall = np.zeros((4, 2, 4), np.uint8)
  tall[0, 0] = 1
  wide = screenshot.landscape(tall)
  assert wide.shape == (2, 4, 4) and wide[0, 3, 0] == 1   # a quarter turn clockwise: top left goes top right
  flat = np.zeros((2, 3, 4), np.uint8)
  assert screenshot.landscape(flat) is flat


class FakeRaylib:
  """Records the drawing calls a screenshot makes."""

  def __init__(self) -> None:
    self.calls: list[str] = []
    self.Rectangle = lambda *args: args
    self.Vector2 = lambda *args: args
    self.WHITE = "white"

  def get_render_width(self) -> int:
    return 3

  def get_render_height(self) -> int:
    return 2

  def load_render_texture(self, width: int, height: int) -> SimpleNamespace:
    self.calls.append("load_render_texture")
    return SimpleNamespace(texture=SimpleNamespace(width=width, height=height))

  def begin_texture_mode(self, target: object) -> None:
    self.calls.append("begin_texture_mode")

  def end_texture_mode(self) -> None:
    self.calls.append("end_texture_mode")

  def load_image_from_texture(self, texture: object) -> SimpleNamespace:
    return SimpleNamespace(to_bytes=lambda size: bytes(range(size)))

  def unload_image(self, image: object) -> None:
    self.calls.append("unload_image")

  def draw_texture_pro(self, *args: object) -> None:
    self.calls.append("draw_texture_pro")

  def unload_render_texture(self, target: object) -> None:
    self.calls.append("unload_render_texture")


def test_a_request_draws_one_frame_offscreen_still_shows_it_and_frees_it(tmp_path: Path) -> None:
  rl = FakeRaylib()
  request, output = tmp_path / "request", tmp_path / "shot.png"
  now = [0.0]
  shots = screenshot.Screenshots(rl, request, output, clock=lambda: now[0])
  shots.after_begin()
  shots.before_present()
  assert rl.calls == []                      # nothing asked
  request.touch()
  now[0] = max(screenshot.CHECK_S, screenshot.SETTLE_S)
  shots.after_begin()
  assert rl.calls == ["load_render_texture", "begin_texture_mode"]
  shots.before_present()
  assert rl.calls[2:] == ["end_texture_mode", "unload_image", "draw_texture_pro"]   # read, then shown on the screen
  assert not request.exists()
  now[0] += screenshot.CHECK_S
  shots.after_begin()
  assert rl.calls[-1] == "unload_render_texture"   # freed once its frame was presented
  deadline = time.monotonic() + 5
  while not output.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
  assert Image.open(output).size == (3, 2)


def test_a_sleeping_screen_is_woken_and_settles_before_the_picture(tmp_path: Path) -> None:
  rl = FakeRaylib()
  request, output = tmp_path / "request", tmp_path / "shot.png"
  now, awake, woken = [0.0], [False], []
  shots = screenshot.Screenshots(rl, request, output, clock=lambda: now[0], awake=lambda: awake[0], wake=lambda: woken.append(now[0]))
  request.touch()
  shots.watch()
  assert woken == [0.0]                      # asleep: wake it, as a touch would
  awake[0] = True
  shots.after_begin()                        # first frame awake
  now[0] = screenshot.SETTLE_S / 2
  shots.after_begin()
  assert rl.calls == []                      # still settling
  now[0] = screenshot.SETTLE_S
  shots.after_begin()
  assert rl.calls == ["load_render_texture", "begin_texture_mode"]
  shots.watch()
  assert woken == [0.0]                      # awake: left alone


def test_install_wraps_drawing_once_and_a_failure_never_stops_the_frame(monkeypatch) -> None:
  presented, begun = [], []
  rl = SimpleNamespace(begin_drawing=lambda: begun.append(True), end_drawing=lambda: presented.append(True))
  monkeypatch.setattr(screenshot.Screenshots, "after_begin", lambda self: 1 / 0)
  monkeypatch.setattr(screenshot.Screenshots, "before_present", lambda self: 1 / 0)
  logged = []
  monkeypatch.setitem(sys.modules, "openpilot.common.swaglog", SimpleNamespace(cloudlog=SimpleNamespace(exception=logged.append)))
  screenshot.install(rl)
  first = rl.end_drawing
  screenshot.install(rl)
  assert rl.end_drawing is first
  rl.begin_drawing()
  rl.end_drawing()
  assert begun == [True] and presented == [True] and logged == ["Tandem screenshot failed"] * 2
