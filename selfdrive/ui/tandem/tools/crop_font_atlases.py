#!/usr/bin/env python3
"""Crop Tandem's font atlases to the rows their glyphs use.

Upstream's generator (selfdrive/assets/fonts/process.py) packs each face into a square power-of-two atlas, and the
200 px glyphs of these faces fill only the top half to 60% of 2048 x 2048. The empty rows still cost GPU memory once
loaded (with mipmaps, about 5 MB an atlas). Cropping keeps every glyph where it is (rows are counted from the top) and
moves raylib's 3 x 3 white patch from the old bottom-right corner to the new one. The device's GPU supports
non-power-of-two textures with mipmaps (raylib logs "full NPOT textures supported").

Runs after build_figtree_fonts.py and fallback_font.py build (the 4096 x 4096 fallback ends near row 2,800), and on
its own for the JetBrains Mono atlases. Cropping a cropped atlas is a no-op.
Usage: python selfdrive/ui/tandem/tools/crop_font_atlases.py
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
FACES = ("Figtree-Regular", "Figtree-Medium", "Figtree-SemiBold", "Figtree-Bold", "Figtree-ExtraBold",
         "JetBrainsMono-Medium", "JetBrainsMono-Bold", "NotoSans-Fallback")
PATCH = 3     # raylib's white patch for drawing shapes, in the atlas's bottom-right corner
ROWS = 64     # the cropped height is a multiple of this


def glyph_bottom(fnt: str) -> int:
  """The lowest row any glyph reaches, from the BMFont text."""
  return max(int(y) + int(h) for y, h in re.findall(r"^char id=\d+\s+x=\d+\s+y=(\d+)\s+width=\d+\s+height=(\d+)", fnt, re.M))


def cropped_height(fnt: str) -> int:
  """The glyphs' rows plus room for the white patch, rounded up to ROWS."""
  return -(-(glyph_bottom(fnt) + PATCH + 1) // ROWS) * ROWS


def crop(face: str, folder: Path = FONT_DIR) -> tuple[int, int]:
  """Crops one face's atlas and updates its .fnt.

  Args:
    face: The face's file stem, e.g. "Figtree-Bold".
    folder: Where its .png and .fnt are.

  Returns:
    The atlas height before and after.
  """
  png, fnt_path = folder / f"{face}.png", folder / f"{face}.fnt"
  fnt = fnt_path.read_text()
  image = Image.open(png)
  height = cropped_height(fnt)
  if height >= image.height:
    return image.height, image.height
  patch = image.crop((image.width - PATCH, image.height - PATCH, image.width, image.height))
  out = image.crop((0, 0, image.width, height))
  out.paste((0,) * len(image.getbands()), (image.width - PATCH, height - PATCH, image.width, height))
  out.paste(patch, (image.width - PATCH, height - PATCH))
  out.save(png, optimize=True)
  fnt_path.write_text(re.sub(r"(?m)^(common .*\bscaleH=)\d+", rf"\g<1>{height}", fnt, count=1))
  return image.height, height


def main() -> None:
  for face in FACES:
    before, after = crop(face)
    print(f"{face}: {before} -> {after} rows")


if __name__ == "__main__":
  main()
