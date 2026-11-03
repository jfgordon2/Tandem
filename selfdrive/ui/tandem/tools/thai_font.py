"""Compose the Thai clusters used by the catalogs into the source font before subsetting.

HarfBuzz is a build dependency only (`pip install uharfbuzz`). The resulting TrueType outlines and the private-use
mapping are committed, so atlas builds and the UI don't need HarfBuzz.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]


def _module(name: str, path: Path):
  spec = importlib.util.spec_from_file_location(name, path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def prepare(font, source: Path) -> set[int]:
  import uharfbuzz as hb
  from fontTools.pens.recordingPen import DecomposingRecordingPen
  from fontTools.pens.transformPen import TransformPen
  from fontTools.pens.ttGlyphPen import TTGlyphPen

  thai = _module("thai_clusters", PACKAGE / "thai.py")
  i18n = _module("tandem_catalog", PACKAGE / "i18n.py")
  texts = []
  for value in i18n.parse_po((PACKAGE / "translations" / "tandem_th.po").read_text(encoding="utf-8")).values():
    texts.extend(value if isinstance(value, list) else [value])
  languages = json.loads((PACKAGE.parents[2] / "selfdrive/ui/translations/languages.json").read_text(encoding="utf-8"))
  texts.extend(languages)
  used = {c for text in texts for c in thai.clusters(text) if len(c) > 1 and any(thai.is_thai(ch) for ch in c)}
  mapping = json.loads(thai.MAPPING.read_text(encoding="utf-8")) if thai.MAPPING.exists() else {}
  next_cp = max(mapping.values(), default=thai.PUA_START - 1) + 1
  for cluster in sorted(used - mapping.keys()):
    if next_cp > thai.PUA_END:
      raise RuntimeError("Thai cluster glyph range is full")
    mapping[cluster] = next_cp
    next_cp += 1

  face = hb.Face(source.read_bytes())
  shaper = hb.Font(face)
  shaper.scale = (face.upem, face.upem)
  glyph_names = font.getGlyphOrder()[:]
  glyph_set = font.getGlyphSet()
  recorded = {}
  for cluster, cp in mapping.items():
    buf = hb.Buffer()
    buf.add_str(cluster)
    buf.guess_segment_properties()
    buf.language = "th"
    hb.shape(shaper, buf)
    pen = TTGlyphPen(None)
    x, y = 0, 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
      name = glyph_names[info.codepoint]
      if name not in recorded:
        recording = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(recording)
        recorded[name] = recording
      recorded[name].replay(TransformPen(pen, (1, 0, 0, 1, x + pos.x_offset, y + pos.y_offset)))
      x += pos.x_advance
      y += pos.y_advance
    name = f"tandemThai{cp:04X}"
    glyph = pen.glyph()
    font["glyf"][name] = glyph
    glyph.recalcBounds(font["glyf"])
    font["hmtx"].metrics[name] = (round(x), glyph.xMin)
    if name not in font.getGlyphOrder():
      font.setGlyphOrder([*font.getGlyphOrder(), name])
    for table in font["cmap"].tables:
      if table.isUnicode() and hasattr(table, "cmap"):
        table.cmap[cp] = name
  thai.MAPPING.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  print(f"Thai: {len(mapping)} composed clusters")
  return set(mapping.values())
