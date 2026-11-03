"""Fonts for Essentials components.

FontWeight (system/ui/lib/application.py) covers the shared Figtree weights, which load at startup.
The design's extra faces live here instead, so upstream's enum only differs by file names, and they
load on first use: ExtraBold for titles and big numbers, JetBrains Mono (Medium and Bold) for Developer View.
The JetBrains Mono atlases are built with process.py's characters plus "−", "·" and "—", which Developer View shows.
"""
from __future__ import annotations

from enum import StrEnum
from importlib.resources import as_file

import pyray as rl

from openpilot.system.ui.lib.application import FONT_DIR, FontWeight, gui_app


class ExtraFont(StrEnum):
  EXTRA_BOLD = "Figtree-ExtraBold.fnt"
  MONO = "JetBrainsMono-Medium.fnt"
  MONO_BOLD = "JetBrainsMono-Bold.fnt"


Face = FontWeight | ExtraFont

_loaded: dict[ExtraFont, rl.Font] = {}


def font(face: Face) -> rl.Font:
  if not isinstance(face, ExtraFont):
    return gui_app.font(face)
  if face not in _loaded:
    with as_file(FONT_DIR) as path:
      loaded = rl.load_font((path / face).as_posix())
    rl.gen_texture_mipmaps(loaded.texture)
    rl.set_texture_filter(loaded.texture, rl.TextureFilter.TEXTURE_FILTER_TRILINEAR)
    _loaded[face] = loaded
  return _loaded[face]


_covered: dict[tuple[str, str], bool] = {}


def covers(face: Face, text: str) -> bool:
  """Whether face's atlas has a glyph for every character of text (raylib draws "?" for the rest)."""
  key = (str(face), text)
  if key not in _covered:
    loaded = font(face)
    _covered[key] = all(loaded.glyphs[rl.get_glyph_index(loaded, ord(c))].value == ord(c) for c in text)
  return _covered[key]


def face_for(text: str, preferred: Face, fallback: Face = FontWeight.UNIFONT) -> Face:
  """preferred when it can draw text, else fallback: a language's own name in Figtree when it can, unifont when not."""
  return preferred if covers(preferred, text) else fallback


_prepared: list[bool] = []


def prepare_fallback() -> None:
  """Once, after gui_app loads its fonts: smooth scaling for the Noto fallback (upstream loads it unfiltered, as it did
  pixel unifont), and Arabic/Thai shaping for every line drawn (no-ops for text without those scripts)."""
  if _prepared:
    return
  _prepared.append(True)
  from openpilot.system.ui.lib import application
  from openpilot.selfdrive.ui.tandem.arabic import shape as arabic_shape
  from openpilot.selfdrive.ui.tandem.thai import shape as thai_shape
  for shape in (arabic_shape, thai_shape):
    if shape not in application.TEXT_SHAPERS:
      application.TEXT_SHAPERS.append(shape)
  try:
    fallback = gui_app.font(FontWeight.UNIFONT)
  except KeyError:      # fonts not loaded (tests)
    return
  rl.gen_texture_mipmaps(fallback.texture)
  rl.set_texture_filter(fallback.texture, rl.TextureFilter.TEXTURE_FILTER_TRILINEAR)
