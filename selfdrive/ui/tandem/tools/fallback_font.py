#!/usr/bin/env python3
"""Builds NotoSans-Fallback, the font for languages Figtree can't draw (Ukrainian, Arabic, Thai, Chinese, Korean and
Japanese), from Noto Sans Medium and its per-script siblings. FontWeight.UNIFONT names it, in place of unifont.

  subset <dir>   Reads the full Noto TTFs from <dir> and writes the glyphs Tandem needs to tools/fonts/ (committed, so the
                 atlas rebuilds without them). The TTFs come from npm, e.g. `npm pack @expo-google-fonts/noto-sans-jp`,
                 in each package's 500Medium/ folder.
  build          Packs tools/fonts/ into selfdrive/assets/fonts/NotoSans-Fallback.png and .fnt.

Run both after the translations gain characters (process.py's charset grows): the build lists any it can't find.
Each character comes from the font for its script; Han characters prefer the font of the language that uses them
(Simplified Chinese, then Traditional, then Japanese). Glyphs from every font share one em size and baseline.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FONT_DIR = ROOT / "selfdrive" / "assets" / "fonts"
TRANSLATIONS = ROOT / "selfdrive" / "ui" / "translations"
SOURCES = Path(__file__).resolve().parent / "fonts"
TANDEM_CATALOGS = Path(__file__).resolve().parents[1] / "translations"
NAME = "NotoSans-Fallback"
SIZE = 64            # px per em in the atlas; text is drawn from 14 to ~60 px, so this keeps it sharp without a huge atlas
EXTRA = "…−·—" + "".join(chr(c) for c in range(0xFE70, 0xFEFD) if unicodedata.name(chr(c), ""))   # ellipsis, signs, Arabic forms

FONTS = {   # file in tools/fonts: the family it came from
  "NotoSans": "NotoSans_500Medium.ttf", "Arabic": "NotoSansArabic_500Medium.ttf", "Thai": "NotoSansThai_500Medium.ttf",
  "JP": "NotoSansJP_500Medium.ttf", "KR": "NotoSansKR_500Medium.ttf", "SC": "NotoSansSC_500Medium.ttf",
  "TC": "NotoSansTC_500Medium.ttf",
}


def _po_chars(code: str) -> set[int]:
  try:
    text = (TRANSLATIONS / f"app_{code}.po").read_text(encoding="utf-8")
  except FileNotFoundError:
    return set()
  return {ord(c) for c in "".join(re.findall(r'msgstr "(.*)"', text))}


def charset() -> tuple[set[int], dict[str, set[int]]]:
  """Every character a translation or a language's name uses, plus ASCII and EXTRA; and each language's own."""
  languages = json.loads((TRANSLATIONS / "languages.json").read_text(encoding="utf-8"))
  by_language = {code.removeprefix("main_"): _po_chars(code.removeprefix("main_")) for code in languages.values()}
  chars = set(range(32, 127)) | {ord(c) for c in EXTRA} | {ord(c) for name in languages for c in name}
  for path in TANDEM_CATALOGS.glob("tandem_*.po"):   # Tandem's own translations (i18n.py)
    code = path.stem.removeprefix("tandem_")
    used = {ord(c) for c in "".join(re.findall(r'msgstr "(.*)"', path.read_text(encoding="utf-8")))}
    by_language[code] = by_language.get(code, set()) | used
  for used in by_language.values():
    chars |= used
  return {c for c in chars if c >= 32 and not 0xFE00 <= c <= 0xFE0F and c < 0x1F000}, by_language   # emoji draw as images


def _order(cp: int, by_language: dict[str, set[int]]) -> list[str]:
  if 0x0600 <= cp <= 0x06FF or 0xFB50 <= cp <= 0xFEFF:
    return ["Arabic"]
  if 0x0E00 <= cp <= 0x0E7F:
    return ["Thai"]
  if 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
    return ["KR"]
  if 0x3040 <= cp <= 0x30FF:
    return ["JP"]
  if cp >= 0x2E80:   # Han and full-width punctuation: the language that uses it first
    first = [f for code, f in (("zh-CHS", "SC"), ("zh-CHT", "TC"), ("ja", "JP"), ("ko", "KR")) if cp in by_language.get(code, set())]
    return first + ["SC", "TC", "JP", "KR"]
  return ["NotoSans", "SC", "JP", "Arabic", "Thai"]


def assign(cmaps: dict[str, set[int]]) -> tuple[dict[str, list[int]], list[int]]:
  chars, by_language = charset()
  picked: dict[str, list[int]] = {name: [] for name in FONTS}
  missing = []
  for cp in sorted(chars):
    font = next((f for f in _order(cp, by_language) if cp in cmaps[f]), None)
    if font is None:
      missing.append(cp)
    else:
      picked[font].append(cp)
  return picked, missing


def subset(source: Path) -> None:
  from fontTools import subset as ft_subset
  from fontTools.ttLib import TTFont
  SOURCES.mkdir(exist_ok=True)
  cmaps = {name: set(TTFont(source / file).getBestCmap()) for name, file in FONTS.items()}
  picked, missing = assign(cmaps)
  for name, file in FONTS.items():
    font = TTFont(source / file)
    options = ft_subset.Options()
    options.layout_features, options.hinting, options.name_IDs = [], False, ["*"]
    sub = ft_subset.Subsetter(options)
    sub.populate(unicodes=picked[name] or [32])
    sub.subset(font)
    font.save(SOURCES / file)
    print(f"{file}: {len(picked[name])} characters")
  if missing:
    print("not in any Noto font:", " ".join(f"U+{c:04X}" for c in missing))


def build() -> None:
  import pyray as rl
  from fontTools.ttLib import TTFont
  sys.path.insert(0, str(FONT_DIR))
  from process import GLYPH_PADDING, _glyph_metrics, _write_bmfont   # upstream's .fnt writer, read only

  fonts = {name: TTFont(SOURCES / file) for name, file in FONTS.items()}
  picked, missing = assign({name: set(f.getBestCmap()) for name, f in fonts.items()})
  if missing:
    print("missing (drawn as '?'):", " ".join(f"U+{c:04X}" for c in missing))

  def metrics(font) -> tuple[float, float]:   # raylib scales so ascent - descent (hhea) is the pixel size
    em = font["head"].unitsPerEm
    return font["hhea"].ascent / em, -font["hhea"].descent / em

  ref_ascent, ref_descent = metrics(fonts["NotoSans"])
  ref_height = ref_ascent + ref_descent
  total = sum(len(cps) for cps in picked.values())
  glyphs = rl.ffi.new("GlyphInfo[]", total)
  codepoints: list[int] = []
  keep = []
  for name, cps in picked.items():
    if not cps:
      continue
    ascent, descent = metrics(fonts[name])
    size = round(SIZE * (ascent + descent) / ref_height)   # the same em size in every font
    data = (SOURCES / FONTS[name]).read_bytes()
    buf = rl.ffi.new("unsigned char[]", data)
    cp_buf = rl.ffi.new("int[]", cps)
    loaded = rl.load_font_data(rl.ffi.cast("unsigned char *", buf), len(data), size, rl.ffi.cast("int *", cp_buf), len(cps),
                               rl.FontType.FONT_DEFAULT)
    keep += [buf, cp_buf, loaded]
    shift = round((ref_ascent - ascent) * SIZE / ref_height)   # onto Noto Sans's baseline
    for i, cp in enumerate(cps):
      g = glyphs[len(codepoints)]
      g.value, g.offsetX, g.offsetY, g.advanceX, g.image = loaded[i].value, loaded[i].offsetX, loaded[i].offsetY + shift, \
        loaded[i].advanceX, loaded[i].image
      codepoints.append(cp)
  rects = rl.ffi.new("Rectangle **")
  image = rl.gen_image_font_atlas(rl.ffi.cast("GlyphInfo *", glyphs), rects, total, SIZE, GLYPH_PADDING, 0)
  if image.width == 0:
    raise RuntimeError("raylib returned an empty atlas")
  entries, line_height, base = _glyph_metrics(glyphs, rects[0], tuple(codepoints))
  if not rl.export_image(image, (FONT_DIR / f"{NAME}.png").as_posix()):
    raise RuntimeError("couldn't write the atlas")
  _write_bmfont(FONT_DIR / f"{NAME}.fnt", SIZE, NAME, f"{NAME}.png", line_height, base, (image.width, image.height), entries)
  print(f"{NAME}: {total} glyphs, {image.width}x{image.height}")


if __name__ == "__main__":
  if len(sys.argv) == 3 and sys.argv[1] == "subset":
    subset(Path(sys.argv[2]))
  elif sys.argv[1:] == ["build"]:
    build()
  else:
    raise SystemExit(__doc__)
