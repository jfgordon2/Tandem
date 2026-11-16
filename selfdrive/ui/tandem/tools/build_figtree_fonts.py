#!/usr/bin/env python3
"""Regenerate the Figtree bitmap fonts with the extra characters the Essentials design uses.

Runs the upstream generator (selfdrive/assets/fonts/process.py) unchanged, adding characters to
its set for the Figtree files only, so process.py stays identical to upstream, then crops each atlas to its glyphs
(crop_font_atlases.py). Requires the pinned raylib (see pyproject.toml).
"""
import sys
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
DESIGN_CHARS = "·…−›"
FACES = ("Regular", "Medium", "SemiBold", "Bold", "ExtraBold")


def main() -> int:
  sys.path.insert(0, str(FONT_DIR))
  import process

  process.EXTRA_CHARS += DESIGN_CHARS
  codepoints, _ = process._char_sets()
  for face in FACES:
    process._process_font(FONT_DIR / f"Figtree-{face}.ttf", codepoints)
  from crop_font_atlases import crop   # the generator's square atlases are half empty
  for face in FACES:
    crop(f"Figtree-{face}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
