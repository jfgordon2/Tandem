"""Render the original PNG turn-signal themes with raylib."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pyray as rl

from openpilot.common.basedir import BASEDIR

ASSETS_PATH = Path(BASEDIR) / "starpilot/assets"
ACTIVE_SIGNALS_PATH = ASSETS_PATH / "active_theme/signals"
FROG_SIGNALS_PATH = ASSETS_PATH / "holiday_themes/world_frog_day/signals"
from openpilot.starpilot.tandem.signals import BUNDLED_SIGNAL_ANIMATIONS, SIGNAL_PACKS_PATH

if TYPE_CHECKING:
  from openpilot.selfdrive.ui.ui_state import UIState

BUNDLED_SIGNAL_PATHS = {
  slug: FROG_SIGNALS_PATH if slug == "frog" else SIGNAL_PACKS_PATH / slug / "signals"
  for slug, _ in BUNDLED_SIGNAL_ANIMATIONS
}
POUNCING_CAT_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["pouncing_cat"]
SHOOTING_STAR_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["shooting_star"]
SEQUENTIAL_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["sequential"]
FLOW_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["flow"]
OPEN_FLOW_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["open_flow"]
GLIDE_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["glide"]
BOUNCING_BALL_SIGNALS_PATH = BUNDLED_SIGNAL_PATHS["bouncing_ball"]
FRAME_PATTERN = re.compile(r"turn_signal(?:_(\d+))?\.png", re.IGNORECASE)
STYLE_PATTERN = re.compile(r"(traditional|static)_(\d+)", re.IGNORECASE)



def frame_number(path: Path) -> int:
  """A signal pack frame's place in the animation, from its file name (0 when it has no number)."""
  match = FRAME_PATTERN.fullmatch(path.name)
  return int(match[1] or 0) if match else 0

class TurnSignalRenderer:
  """Draws the turn signal animation beside the speed (or StarPilot's static indicators), loading the chosen pack's frames on demand."""

  def __init__(self) -> None:
    self._frames: list[rl.Texture] = []
    self._blindspot: rl.Texture | None = None
    self._stamp: tuple | None = None
    self._pack: str | None = None
    self._signal_seen = False
    self._frame_seconds = 0.125
    self._style = "traditional"
    self._animation_key: tuple | None = None
    self._started_at = 0.0

  def close(self) -> None:
    """Unloads the textures; the next render loads them again."""
    for texture in self._frames:
      rl.unload_texture(texture)
    if self._blindspot is not None:
      rl.unload_texture(self._blindspot)
    self._frames = []
    self._blindspot = None
    self._stamp = None
    self._pack = None
    self._animation_key = None

  @staticmethod
  def _load_texture(path: Path) -> rl.Texture | None:
    texture = rl.load_texture(str(path))
    if not texture.id:
      return None
    rl.set_texture_filter(texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
    return texture

  @staticmethod
  def _scan(directory: Path) -> tuple[list[Path], tuple]:
    try:
      files = sorted(p for p in directory.iterdir() if FRAME_PATTERN.fullmatch(p.name) or
                     p.name.lower() == "turn_signal_blindspot.png" or STYLE_PATTERN.fullmatch(p.name))
      entries = []
      for path in files:
        stat = path.stat()
        entries.append((path.name, stat.st_mtime_ns, stat.st_size))
      return files, (str(directory.resolve()), tuple(entries))
    except OSError:
      return [], (str(directory), None)

  def _refresh(self, pack: str, rescan: bool) -> None:
    if pack == self._pack and not rescan:
      return

    files, file_stamp = self._scan(ACTIVE_SIGNALS_PATH)
    active_directory = Path(file_stamp[0])
    bundled = BUNDLED_SIGNAL_PATHS.get(pack)
    active_is_pack = bundled is not None and (active_directory == bundled.resolve() or
                                              (active_directory.name == "signals" and active_directory.parent.name == pack))
    # Preserve edits to the theme manager's active frog pack. Bundled frogs are
    # a fallback while its link is missing or still points at the previous pack.
    if bundled is not None and (not active_is_pack or not any(FRAME_PATTERN.fullmatch(path.name) for path in files)):
      files, file_stamp = self._scan(bundled)
    stamp = (pack, file_stamp)
    self._pack = pack
    if stamp == self._stamp:
      return

    self.close()
    self._pack = pack
    self._stamp = stamp
    frame_paths = sorted((p for p in files if FRAME_PATTERN.fullmatch(p.name)), key=frame_number)
    self._style = "traditional" if len(frame_paths) > 1 else "static"
    self._frame_seconds = 0.125
    for path in files:
      if match := STYLE_PATTERN.fullmatch(path.name):
        self._style = match[1].lower()
        self._frame_seconds = max(16, int(match[2])) / 1000 if int(match[2]) else 0.125
      elif path.name.lower() == "turn_signal_blindspot.png":
        self._blindspot = self._load_texture(path)
    for path in frame_paths:
      if (texture := self._load_texture(path)) is not None:
        self._frames.append(texture)

  def render(self, rect: rl.Rectangle, state: UIState, *, enabled: bool = True, top_margin: float = 0.0, bottom_margin: float = 0.0,
             static_offset: float = 0.0) -> None:
    """Draws the turn signals for this frame.

    Args:
      rect: The road view.
      state: Upstream's UI state.
      enabled: Whether to draw at all (not while a full alert covers the road).
      top_margin: Space taken at the top.
      bottom_margin: Space taken at the bottom.
      static_offset: Moves static indicators down with the speed (Speed at Bottom).
    """
    pack = state.starpilot_toggles.get("signal_icons", "stock")
    if state.starpilot_toggles.get("random_themes", False):
      pack = "random"
    if pack in ("stock", "none", "") or state.starpilot_toggles.get("simple_mode", False):
      self.close()
      return

    sm = state.sm
    if (not enabled or not state.started or not sm.valid["carState"] or not sm.alive["carState"] or
        sm.recv_frame["carState"] < state.started_frame or rect.width <= 0 or rect.height <= top_margin + bottom_margin):
      self._animation_key = None
      self._signal_seen = False
      return

    car_state = sm["carState"]
    left, right = bool(car_state.leftBlinker), bool(car_state.rightBlinker)
    # No polling: look at the signal folder only when the pack changes or a new
    # signal starts. Textures are reloaded only if the files actually changed.
    signalling = left or right
    self._refresh(pack, rescan=signalling and not self._signal_seen)
    self._signal_seen = signalling
    now = time.monotonic()
    if not (left or right) or not self._frames:
      self._animation_key = None
      return

    animation_key = (state.started_frame, left, right)
    if animation_key != self._animation_key:
      self._animation_key = animation_key
      self._started_at = now
    frame_index = int((now - self._started_at) / self._frame_seconds) % len(self._frames)
    frame = self._frames[frame_index]

    # Scale the old 2160x1080 layout to the camera viewport (including split
    # screen and mici). PNG frames contain the frog's vertical hop already.
    available_height = rect.height - top_margin - bottom_margin
    scale = min(rect.width / 2160, rect.height / 1080, available_height / frame.height)
    width, height = frame.width * scale, frame.height * scale
    progress = frame_index / max(1, len(self._frames) - 1)
    for is_right, active, blindspot in ((False, left, car_state.leftBlindspot), (True, right, car_state.rightBlindspot)):
      if not active:
        continue
      texture = self._blindspot if blindspot and self._blindspot is not None else frame
      if self._style == "static":
        x = rect.x + rect.width * (0.625 if is_right else 0.375) - (0 if is_right else width)
        y = rect.y + top_margin + min(height / 2, max(0, available_height - height)) + static_offset
        y = min(y, rect.y + rect.height - height)
      else:
        x = rect.x + (progress if is_right else 1 - progress) * (rect.width - width)
        y = rect.y + rect.height - bottom_margin - height
      source = rl.Rectangle(0, 0, -texture.width if is_right else texture.width, texture.height)
      rl.draw_texture_pro(texture, source, rl.Rectangle(x, y, width, height), rl.Vector2(0, 0), 0, rl.WHITE)
