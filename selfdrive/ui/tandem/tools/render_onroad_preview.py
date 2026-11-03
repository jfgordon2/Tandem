#!/usr/bin/env python3
"""Render the Essentials driving view with every bundled animation for asset previews.

Drawing uses EssentialsOnroadView and its owned TurnSignalRenderer. This preview also permits the
indicator packs that Essentials normally replaces with its built-in chevrons. Only the inputs are faked:

  * no camera: VisionIPC is stubbed, so the road area is the camera-off background
  * car data: messaging is stubbed with real cereal structs (speed, cruise, blinkers, blind spot)
  * settings: an isolated params store (OPENPILOT_PREFIX), never your real one
  * timing: the turn-signal renderer gets a controlled clock, so frame N of the
    output is exactly animation frame N after the blinker comes on

Compiled modules (params, transformations) are used when they load; otherwise
pure-Python stand-ins are used (the HUD does not depend on them).

Examples:
  python selfdrive/ui/tandem/tools/render_onroad_preview.py --pack sequential --out /tmp/preview
  python selfdrive/ui/tandem/tools/render_onroad_preview.py --pack bouncing_ball --right --gif /tmp/ball.gif
  python selfdrive/ui/tandem/tools/render_onroad_preview.py --pack flow --hazards --blindspot --frames 1

On Linux without a display, run it under `xvfb-run -a`. On macOS a window may
flash briefly while rendering.
"""
from __future__ import annotations

import argparse
import enum
import os
import re
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WIDTH, HEIGHT = 2160, 1080
MPH = 0.44704
FRAME_PATTERN = re.compile(r"turn_signal(?:_(\d+))?\.png", re.IGNORECASE)
TIMING_PATTERN = re.compile(r"(traditional|static)_(\d+)", re.IGNORECASE)


def signals_dir(pack: str) -> Path:
  """Folder holding a bundled pack's frames (mirrors BUNDLED_SIGNAL_PATHS in turn_signals.py)."""
  if pack == "frog":
    return ROOT / "starpilot/assets/holiday_themes/world_frog_day/signals"
  return ROOT / "selfdrive/ui/tandem/assets/signal_packs" / pack / "signals"


def pack_timing(directory: Path) -> tuple[int, int, str]:
  """(frame count, frame duration in ms, style) read from a signal pack's files."""
  frames = [p for p in directory.iterdir() if FRAME_PATTERN.fullmatch(p.name)]
  style, ms = ("traditional" if len(frames) > 1 else "static"), 125
  for path in directory.iterdir():
    if match := TIMING_PATTERN.fullmatch(path.name):
      style = match[1].lower()
      ms = max(16, int(match[2])) if int(match[2]) else 125  # same rules as turn_signals.py
  return len(frames), ms, style


# ── input stubs ──────────────────────────────────────────────────────────────

class _AlwaysDict(dict):
  def __init__(self, value):
    super().__init__()
    self._value = value

  def __missing__(self, key):
    return self._value


def install_stubs():
  """Replace live inputs (camera, messaging) and any compiled module that won't load."""
  visionipc = types.ModuleType("msgq.visionipc")

  class VisionStreamType(enum.IntEnum):
    VISION_STREAM_ROAD = 0
    VISION_STREAM_DRIVER = 1
    VISION_STREAM_WIDE_ROAD = 2
    VISION_STREAM_MAP = 3

  class VisionIpcClient:
    def __init__(self, *args, **kwargs):
      self.num_buffers = self.buffer_len = self.width = self.height = self.stride = self.uv_offset = 0
      self.frame_id = self.timestamp_sof = 0

    def connect(self, *args, **kwargs):
      return False

    def is_connected(self):
      return False

    def recv(self, *args, **kwargs):
      return None

    @staticmethod
    def available_streams(*args, **kwargs):
      return set()

  visionipc.VisionIpcClient, visionipc.VisionStreamType, visionipc.VisionBuf = VisionIpcClient, VisionStreamType, object
  msgq = sys.modules.get("msgq") or types.ModuleType("msgq")
  msgq.visionipc = visionipc
  sys.modules["msgq"], sys.modules["msgq.visionipc"] = msgq, visionipc

  import cereal
  from cereal import log

  events: dict[str, tuple] = {}

  def message(name):
    if name not in events:
      event = log.Event.new_message()
      try:
        builder = event.init(name)
      except Exception:
        try:
          builder = event.init(name, 1)  # list-typed services, e.g. pandaStates
        except Exception:
          builder = None
      events[name] = (event, builder)
    return events[name][1]

  class SubMaster:
    def __init__(self, services, *args, **kwargs):
      self.services = list(services)
      self.frame = 1000
      self.valid, self.alive, self.freq_ok = _AlwaysDict(True), _AlwaysDict(True), _AlwaysDict(True)
      self.updated, self.seen = _AlwaysDict(True), _AlwaysDict(True)
      self.recv_frame = _AlwaysDict(self.frame)  # every message is fresh, like live data
      self.recv_time = _AlwaysDict(time.monotonic())
      self.logMonoTime = _AlwaysDict(0)

    def update(self, timeout=0):
      self.frame += 1
      self.recv_frame.clear()
      self.recv_frame._value = self.frame
      self.recv_time.clear()
      self.recv_time._value = time.monotonic()

    def __getitem__(self, name):
      return message(name)

    def all_checks(self, *args):
      return True

    all_alive = all_valid = all_freq_ok = all_checks

  class PubMaster:
    def __init__(self, *args, **kwargs):
      pass

    def send(self, *args, **kwargs):
      pass

  def new_message(service=None, size=None, **kwargs):
    event = log.Event.new_message(**kwargs)
    if service is not None:
      event.init(service) if size is None else event.init(service, size)
    return event

  messaging = types.ModuleType("cereal.messaging")
  messaging.SubMaster, messaging.PubMaster, messaging.new_message = SubMaster, PubMaster, new_message
  sys.modules["cereal.messaging"] = messaging
  cereal.messaging = messaging

  try:
    import openpilot.common.transformations.transformations
  except ImportError:
    sys.modules["openpilot.common.transformations.transformations"] = _transformations_fallback()

  try:
    import openpilot.selfdrive.pandad  # noqa: F401
  except ImportError:  # compiled CAN helpers aren't built; the UI only imports the package
    pandad = types.ModuleType("openpilot.selfdrive.pandad")
    pandad.__path__ = [str(ROOT / "selfdrive/pandad")]
    pandad.can_list_to_can_capnp = lambda *args, **kwargs: b""
    pandad.can_capnp_to_list = lambda *args, **kwargs: []
    sys.modules["openpilot.selfdrive.pandad"] = pandad

  return message


def _transformations_fallback():
  """numpy equivalents of the compiled rotation helpers; geodetic ones are unused by the HUD."""
  import numpy as np
  module = types.ModuleType("openpilot.common.transformations.transformations")

  def euler2rot(e):
    r, p, y = e
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return (np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]) @ np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]]) @
            np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]]))

  def rot2euler(m):
    m = np.asarray(m)
    return np.array([np.arctan2(m[2, 1], m[2, 2]), -np.arcsin(np.clip(m[2, 0], -1, 1)), np.arctan2(m[1, 0], m[0, 0])])

  def euler2quat(e):
    r, p, y = np.asarray(e) / 2
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    return np.array([cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy])

  def quat2rot(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])

  class LocalCoord:
    def __init__(self, *args, **kwargs):
      pass

    @classmethod
    def from_geodetic(cls, *args, **kwargs):
      return cls()

    @classmethod
    def from_ecef(cls, *args, **kwargs):
      return cls()

  module.euler2rot_single, module.rot2euler_single = euler2rot, rot2euler
  module.euler2quat_single, module.quat2rot_single = euler2quat, quat2rot
  module.quat2euler_single = lambda q: rot2euler(quat2rot(q))
  module.rot2quat_single = lambda m: euler2quat(rot2euler(m))
  module.ecef_euler_from_ned_single = module.ned_euler_from_ecef_single = lambda *args: np.zeros(3)
  module.ecef2geodetic_single = module.geodetic2ecef_single = lambda *args: np.zeros(3)
  module.LocalCoord = LocalCoord
  return module


def set_driving_scene(message, args):
  car = message("carState")
  car.vEgo = car.vEgoCluster = args.speed * MPH
  car.cruiseState.enabled = car.cruiseState.available = True
  car.cruiseState.speed = car.cruiseState.speedCluster = args.set_speed * MPH
  car.vCruise = car.vCruiseCluster = args.set_speed * 1.609344
  car.gearShifter = "drive"
  car.leftBlinker = args.hazards or not args.right
  car.rightBlinker = args.hazards or args.right
  car.leftBlindspot = car.rightBlindspot = args.blindspot
  selfdrive = message("selfdriveState")
  selfdrive.enabled = selfdrive.active = True
  selfdrive.state = "enabled"
  selfdrive.alertSize = args.alert
  if args.alert != "none":
    selfdrive.alertStatus = "normal"
    selfdrive.alertText1 = "Steer Left to Start Lane Change Once Safe" if args.alert == "small" else "Take Control"
    selfdrive.alertText2 = "" if args.alert == "small" else "Lane Change Blocked"
    selfdrive.alertType = "preLaneChangeLeft/warning" if args.alert == "small" else "laneChangeBlocked/warning"
  device = message("deviceState")
  device.started = True
  device.deviceType = "tizi"  # comma 3X
  message("roadCameraState").sensor = message("wideRoadCameraState").sensor = "ox03c10"
  panda = message("pandaStates")[0]
  panda.ignitionLine = True
  panda.pandaType = "tres"
  message("carParams").openpilotLongitudinalControl = True


# ── rendering ────────────────────────────────────────────────────────────────

def parse_args(argv=None):
  parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  parser.add_argument("--pack", default="sequential", help="signal pack slug (default: sequential)")
  side = parser.add_mutually_exclusive_group()
  side.add_argument("--right", action="store_true", help="right turn signal (default: left)")
  side.add_argument("--hazards", action="store_true", help="both turn signals")
  parser.add_argument("--blindspot", action="store_true", help="vehicle in the blind spot (warning image)")
  parser.add_argument("--speed", type=float, default=62, help="current speed in mph (default: 62)")
  parser.add_argument("--set-speed", type=float, default=65, help="cruise set speed in mph (default: 65)")
  parser.add_argument("--speed-at-bottom", action="store_true", help="preview-only bottom speed layout (does not change a device setting)")
  parser.add_argument("--alert", choices=("none", "small", "mid"), default="none", help="show a bottom alert")
  parser.add_argument("--frames", type=int, help="frames to capture (default: one full animation cycle)")
  parser.add_argument("--out", type=Path, default=Path("selfdrive/ui/tandem/tools/out/onroad"), help="folder for PNG frames")
  parser.add_argument("--gif", type=Path, help="also write an animated GIF here (needs Pillow)")
  parser.add_argument("--gif-scale", type=float, default=0.5, help="GIF size relative to 2160x1080 (default: 0.5)")
  return parser.parse_args(argv)


def init_preview_window(title: str) -> None:
  """Initialize real UI fonts with clipping in capture-target device pixels."""
  import pyray as rl
  from openpilot.system.ui.lib.application import gui_app
  gui_app.init_window(title)
  # Desktop auto scaling applies to the window, not our 2160x1080 texture.
  rl.begin_scissor_mode = rl._orig_begin_scissor_mode


def export_preview_frame(target, path: Path) -> None:
  """Save the opaque, device-sized screen without render-texture alpha artifacts."""
  import pyray as rl
  capture = rl.load_image_from_texture(target.texture)
  try:
    rl.image_flip_vertical(capture)
    rl.image_format(capture, rl.PixelFormat.PIXELFORMAT_UNCOMPRESSED_R8G8B8)
    rl.export_image(capture, str(path))
  finally:
    rl.unload_image(capture)


def render(args) -> list[Path]:
  directory = signals_dir(args.pack)
  if not directory.is_dir():
    raise SystemExit(f"Unknown signal pack '{args.pack}': {directory} not found")
  frame_count, frame_ms, _ = pack_timing(directory)
  captures = args.frames or frame_count

  os.environ["BIG"] = "1"  # comma 3X layout
  os.environ.setdefault("OPENPILOT_PREFIX", f"_onroad_preview_{os.getpid()}")  # isolated params store
  message = install_stubs()
  set_driving_scene(message, args)

  from openpilot.common.params import Params
  params = Params()
  for key, value in {"IsMetric": False, "CustomThemes": True, "SignalAnimation": args.pack,
                     "HolidayThemes": False, "RandomThemes": False}.items():
    (params.put_bool if isinstance(value, bool) else params.put)(key, value)

  import pyray as rl
  from openpilot.system.ui.lib.application import gui_app
  from openpilot.selfdrive.ui.ui_state import ui_state
  init_preview_window("Tandem animation preview")
  from openpilot.selfdrive.ui.tandem.onroad import turn_signals
  from openpilot.selfdrive.ui.tandem.onroad.view import EssentialsOnroadView
  from openpilot.selfdrive.ui.tandem.onroad.layers import BAR_HEIGHT, BAR_MARGIN, draw_speed
  from openpilot.selfdrive.ui.tandem.onroad import extras

  class AnimationPreview(EssentialsOnroadView):
    def _render_turn_signals(self):
      c = self._content_rect
      rl.begin_scissor_mode(int(c.x), int(c.y), int(c.width), int(c.height))
      try:
        self._turn_signals.render(c, ui_state, enabled=self.alert_renderer.will_render()[0] is None,
                                  bottom_margin=BAR_HEIGHT + BAR_MARGIN + extras.SIGNAL_GAP)
      finally:
        rl.end_scissor_mode()

    def _draw_current_speed(self, rect):
      offset = max(0, rect.height - BAR_HEIGHT - 380) if args.speed_at_bottom else 0
      draw_speed(rect, self._hud_renderer.speed, "mph", offset, not args.right or args.hazards, args.right or args.hazards, clock[0])

  clock = [1000.0]
  turn_signals.time = types.SimpleNamespace(monotonic=lambda: clock[0])
  view = AnimationPreview()
  target = rl.load_render_texture(WIDTH, HEIGHT)

  def draw():
    ui_state.update()
    ui_state.started = True
    ui_state.starpilot_toggles.update({"signal_icons": args.pack, "random_themes": False, "simple_mode": False,
                                       "speed_at_bottom": args.speed_at_bottom})
    rl.begin_texture_mode(target)
    rl.clear_background(rl.BLACK)
    view.render(rl.Rectangle(0, 0, WIDTH, HEIGHT))
    rl.end_texture_mode()

  for _ in range(60):  # settle filters, layout and alert easing with the blinker already on
    draw()

  args.out.mkdir(parents=True, exist_ok=True)
  written = []
  for index in range(captures):
    clock[0] = 1000.0 + (index + 0.25) * frame_ms / 1000  # a quarter into animation frame `index`
    draw()
    path = args.out / f"frame_{index:03d}.png"
    export_preview_frame(target, path)
    written.append(path)

  if args.gif:
    write_gif(written, args.gif, frame_ms, args.gif_scale)
  rl.set_trace_log_level(rl.TraceLogLevel.LOG_ERROR)
  view.close()
  rl.unload_render_texture(target)
  gui_app.close()
  return written


def write_gif(frames: list[Path], destination: Path, frame_ms: int, scale: float) -> None:
  try:
    from PIL import Image
  except ImportError as error:
    raise SystemExit("--gif needs Pillow: pip install pillow") from error
  size = (round(WIDTH * scale), round(HEIGHT * scale))
  images = [Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
            .quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for path in frames]
  destination.parent.mkdir(parents=True, exist_ok=True)
  images[0].save(destination, save_all=True, append_images=images[1:], duration=frame_ms, loop=0)


def main(argv=None):
  args = parse_args(argv)
  written = render(args)
  print(f"Wrote {len(written)} frame(s) to {args.out}" + (f" and {args.gif}" if args.gif else ""))


if __name__ == "__main__":
  main()
