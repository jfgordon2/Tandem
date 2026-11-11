"""Fonts for Essentials components.

Upstream keeps its Inter and unifont faces. Tandem maps those weight identifiers to its own
Figtree and Noto files, loaded on first use, alongside ExtraBold and JetBrains Mono for Developer View.
The JetBrains Mono atlases are built with process.py's characters plus "−", "·" and "—", which Developer View shows.
"""
from __future__ import annotations

from enum import StrEnum
from importlib.resources import as_file
import os

import pyray as rl

from openpilot.system.ui.lib.application import FONT_DIR, FontWeight


class ExtraFont(StrEnum):
  """Fonts Tandem adds to upstream's: Figtree's extra-bold weight and JetBrains Mono for numbers in Developer View."""
  EXTRA_BOLD = "Figtree-ExtraBold.fnt"
  MONO = "JetBrainsMono-Medium.fnt"
  MONO_BOLD = "JetBrainsMono-Bold.fnt"


Face = FontWeight | ExtraFont

FONT_FILES: dict[Face, str] = {
  FontWeight.ROMAN: "Figtree-Regular.fnt",
  FontWeight.MEDIUM: "Figtree-Medium.fnt",
  FontWeight.BOLD: "Figtree-Bold.fnt",
  FontWeight.SEMI_BOLD: "Figtree-SemiBold.fnt",
  FontWeight.UNIFONT: "NotoSans-Fallback.fnt",
}
_loaded: dict[str, rl.Font] = {}


def lazy_upstream_fonts() -> bool:
  return all(os.getenv(switch, "1") != "0" for switch in ("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR"))


def font_file(face: Face) -> str:
  return FONT_FILES.get(face, str(face))


def font(face: Face) -> rl.Font:
  """The face's font, loaded the first time it's asked for and kept, with mipmaps so scaled text stays smooth."""
  filename = font_file(face)
  if filename not in _loaded:
    with as_file(FONT_DIR) as path:
      loaded = rl.load_font((path / filename).as_posix())
    rl.gen_texture_mipmaps(loaded.texture)
    rl.set_texture_filter(loaded.texture, rl.TextureFilter.TEXTURE_FILTER_TRILINEAR)
    _loaded[filename] = loaded
  return _loaded[filename]


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


def prepare_fallback() -> None:
  """Load Tandem's smoothed fallback without changing upstream's fonts or text shaping."""
  font(FontWeight.UNIFONT)
