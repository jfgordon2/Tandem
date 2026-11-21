"""Turn Signal's Whimsy animations (design/signalpicker.html, signalunicorn.html): a pack's PNG frames cross the road
above the bar while a blinker is on, mirrored for right turns, with the pack's blind-spot frame while a car is there.

Release drew StarPilot 6's signal animations, chosen with its SignalAnimation param. StarPilot 7 has no signal
animations, so the choice is Tandem's own preference (prefs.TURN_SIGNAL) and the four Whimsy packs live in Tandem's
assets (assets/signal_packs). Standard is the chevrons in the speed pill (layers.draw_signal), drawn either way.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.i18n import N_
from openpilot.starpilot.ui.raylib import rl

SIGNAL_PACKS_PATH = Path(__file__).resolve().parents[1] / "assets/signal_packs"
STANDARD = "standard"
# The Whimsy packs, in the picker's order: their folder under assets/signal_packs and their name.
WHIMSY = {"frog": N_("Jumping frog"), "pouncing_cat": N_("Pouncing cat"), "bouncing_ball": N_("Bouncing ball"),
          "unicorn_rider": N_("Unicorn rider")}
PACK_PATHS = {slug: SIGNAL_PACKS_PATH / slug / "signals" for slug in WHIMSY}
FRAME_PATTERN = re.compile(r"turn_signal(?:_(\d+))?\.png", re.IGNORECASE)
STYLE_PATTERN = re.compile(r"(traditional|static)_(\d+)", re.IGNORECASE)
BLINDSPOT_FRAME = "turn_signal_blindspot.png"
DEFAULT_FRAME_S = 0.125
GAP = T.px(12)   # between an animation and the bar


def frame_number(path: Path) -> int:
  """A frame's place in the animation, from its file name (0 when it has no number)."""
  match = FRAME_PATTERN.fullmatch(path.name)
  return int(match[1] or 0) if match else 0


def pack_frames(slug: str) -> list[Path]:
  """A Whimsy pack's frames in order; empty for Standard or a missing pack."""
  directory = PACK_PATHS.get(slug)
  try:
    files = list(directory.iterdir()) if directory is not None else []
  except OSError:
    return []
  return sorted((p for p in files if FRAME_PATTERN.fullmatch(p.name)), key=frame_number)


def pack_timing(slug: str) -> tuple[float, str]:
  """(seconds per frame, "traditional" or "static") from the pack's marker file, as StarPilot's packs name it."""
  directory = PACK_PATHS.get(slug)
  try:
    names = [p.name for p in directory.iterdir()] if directory is not None else []
  except OSError:
    names = []
  for name in names:
    if match := STYLE_PATTERN.fullmatch(name):
      ms = int(match[2])
      return (max(16, ms) / 1000 if ms else DEFAULT_FRAME_S), match[1].lower()
  return DEFAULT_FRAME_S, "traditional"


class TurnSignalRenderer:
  """Draws the chosen Whimsy pack while a blinker is on, loading its frames the first time it's needed."""

  def __init__(self) -> None:
    self._frames: list[Any] = []
    self._blindspot: Any = None
    self._pack: str | None = None
    self._frame_s = DEFAULT_FRAME_S
    self._style = "traditional"
    self._animation_key: tuple[int, bool, bool] | None = None
    self._started_at = 0.0

  def close(self) -> None:
    """Unloads the textures; the next signal loads them again."""
    for texture in self._frames:
      rl.unload_texture(texture)
    if self._blindspot is not None:
      rl.unload_texture(self._blindspot)
    self._frames, self._blindspot, self._pack, self._animation_key = [], None, None, None

  @staticmethod
  def _load(path: Path) -> Any:
    texture = rl.load_texture(str(path))
    if not texture.id:
      return None
    rl.set_texture_filter(texture, rl.TextureFilter.TEXTURE_FILTER_BILINEAR)
    return texture

  def _use(self, pack: str) -> None:
    if pack == self._pack:
      return
    self.close()
    self._pack = pack
    self._frame_s, self._style = pack_timing(pack)
    self._frames = [t for t in (self._load(p) for p in pack_frames(pack)) if t is not None]
    blindspot = PACK_PATHS[pack] / BLINDSPOT_FRAME
    self._blindspot = self._load(blindspot) if blindspot.is_file() else None

  def render(self, rect: rl.Rectangle, pack: str, car: Any, drive: int, *, bottom_margin: float = 0.0) -> None:
    """Draws this frame of the animation.

    Args:
      rect: The road view, already clipped.
      pack: The chosen Turn Signal (prefs.TURN_SIGNAL); Standard draws nothing here.
      car: openpilot's carState for this drive, or None (no animation without it).
      drive: The drive's started frame, so a new drive starts the animation over.
      bottom_margin: Space kept clear at the bottom: the bar and its gap.
    """
    if pack not in WHIMSY:
      self.close()
      return
    left, right = (bool(car.leftBlinker), bool(car.rightBlinker)) if car is not None else (False, False)
    if not (left or right) or rect.width <= 0 or rect.height <= bottom_margin:
      self._animation_key = None
      return
    self._use(pack)
    if not self._frames:
      return
    now = time.monotonic()
    key = (drive, left, right)
    if key != self._animation_key:
      self._animation_key, self._started_at = key, now
    index = int((now - self._started_at) / self._frame_s) % len(self._frames)
    frame = self._frames[index]
    # The packs are drawn for a 2160 x 1080 road; scale to this one. The frames hold any hop themselves.
    available = rect.height - bottom_margin
    scale = min(rect.width / 2160, rect.height / 1080, available / frame.height)
    width, height = frame.width * scale, frame.height * scale
    progress = index / max(1, len(self._frames) - 1)
    for is_right, active, blindspot in ((False, left, bool(car.leftBlindspot)), (True, right, bool(car.rightBlindspot))):
      if not active:
        continue
      texture = self._blindspot if blindspot and self._blindspot is not None else frame
      if self._style == "static":
        x = rect.x + rect.width * (0.625 if is_right else 0.375) - (0 if is_right else width)
        y = rect.y + min(height / 2, max(0.0, available - height))
      else:   # crossing the road toward the turn: right to left for a left turn
        x = rect.x + (progress if is_right else 1 - progress) * (rect.width - width)
        y = rect.y + rect.height - bottom_margin - height
      source = rl.Rectangle(0, 0, -texture.width if is_right else texture.width, texture.height)
      rl.draw_texture_pro(texture, source, rl.Rectangle(x, y, width, height), rl.Vector2(0, 0), 0, rl.WHITE)
