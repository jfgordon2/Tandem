"""Thai clusters for the bitmap font: keep vowels and tone marks attached to their consonant.

The font tool composes these clusters with HarfBuzz and assigns them private-use glyphs. Catalogs keep normal Thai;
only measurement and drawing use the composed glyphs. No shaping library is needed on the device.
"""
from __future__ import annotations

from typing import cast
import functools
import json
from pathlib import Path
import unicodedata

MAPPING = Path(__file__).resolve().parent / "translations" / "thai_clusters.json"
PUA_START, PUA_END = 0xE000, 0xF8FF


def is_thai(c: str) -> bool:
  return 0x0E00 <= ord(c) <= 0x0E7F


def clusters(text: str) -> list[str]:
  """Thai consonants with their leading/trailing vowels and marks; other characters stay separate."""
  out: list[str] = []
  for c in text:
    cp = ord(c)
    if out and is_thai(out[-1][-1]) and is_thai(c):
      previous_is_leading = 0x0E40 <= ord(out[-1][-1]) <= 0x0E44
      if unicodedata.category(c).startswith("M") or cp in (0x0E30, 0x0E32, 0x0E33, 0x0E45, 0x0E46) \
         or (previous_is_leading and 0x0E01 <= cp <= 0x0E2E):
        out[-1] += c
        continue
    out.append(c)
  return out


@functools.cache
def mapping() -> dict[str, int]:
  return cast("dict[str, int]", json.loads(MAPPING.read_text(encoding="utf-8")))


@functools.lru_cache(maxsize=4096)
def shape(text: str) -> str:
  if not any(is_thai(c) for c in text):
    return text
  glyphs = mapping()
  return "".join(chr(glyphs[c]) if c in glyphs else c for c in clusters(text))


def logical(text: str) -> str:
  """Readable text for reports of wrapped or shortened bitmap text."""
  reverse = {chr(cp): cluster for cluster, cp in mapping().items()}
  return "".join(reverse.get(c, c) for c in text)


def trim_last(text: str) -> str:
  """Elide a whole Thai cluster instead of leaving a vowel or tone mark behind."""
  if text and is_thai(text[-1]):
    return text[:-len(clusters(text)[-1])]
  return text[:-1]
