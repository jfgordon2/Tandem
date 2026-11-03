"""Arabic for raylib, which draws one glyph per character, left to right, with no shaping.

shape() turns a line of logical Arabic text into what to draw: each letter in its joined form (initial, medial, final
or isolated, from Unicode's Arabic Presentation Forms-B, which the Noto fallback atlas holds), lam-alef as one
ligature, and right-to-left runs reversed so they read correctly when drawn left to right. Numbers and Latin words
keep their own order. Text without Arabic comes back unchanged.

This is a small subset of the Unicode bidi algorithm: a line containing Arabic is taken as right to left.
"""
from __future__ import annotations

import functools
import re
import unicodedata

ARABIC = re.compile("[؀-ۿ]")
_RIGHT_JOINING = set("آأؤإاةدذرزوٱ")   # join only to the letter before
_NON_JOINING = set("ء")                                                                       # hamza
_LAM, _TATWEEL = "ل", "ـ"
_LAM_ALEF = {"آ": "ﻵ", "أ": "ﻷ", "إ": "ﻹ", "ا": "ﻻ"}       # isolated; final is +1
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")


def _transparent(c: str) -> bool:
  return unicodedata.category(c) == "Mn"            # harakat and other marks don't break joining


def _letter(c: str) -> bool:
  return "ء" <= c <= "ي" or c in ("ٱ", _TATWEEL)


def _joins_after(c: str) -> bool:
  """Whether c connects to the letter that follows it."""
  return _letter(c) and c not in _RIGHT_JOINING and c not in _NON_JOINING


def _joins_before(c: str) -> bool:
  return _letter(c) and c not in _NON_JOINING


@functools.cache
def _form(c: str, form: str) -> str:
  try:
    return unicodedata.lookup(f"{unicodedata.name(c)} {form} FORM")
  except KeyError:
    return c


def _neighbor(text: str, i: int, step: int) -> str:
  i += step
  while 0 <= i < len(text) and _transparent(text[i]):
    i += step
  return text[i] if 0 <= i < len(text) else ""


def join(text: str) -> str:
  """Each Arabic letter in its contextual form, in logical order."""
  out, i = [], 0
  while i < len(text):
    c = text[i]
    if not _letter(c) or c == _TATWEEL:
      out.append(c)
      i += 1
      continue
    prev, nxt = _neighbor(text, i, -1), _neighbor(text, i, 1)
    after = bool(prev) and _joins_after(prev) and _joins_before(c)
    if c == _LAM and nxt in _LAM_ALEF:              # lam-alef: one ligature, joined to the letter before or not
      out.append(chr(ord(_LAM_ALEF[nxt]) + (1 if after else 0)))
      i = text.index(nxt, i + 1) + 1
      continue
    before = bool(nxt) and _joins_after(c) and _joins_before(nxt)
    out.append(_form(c, "MEDIAL" if after and before else "FINAL" if after else "INITIAL" if before else "ISOLATED"))
    i += 1
  return "".join(out)


_SEPARATORS = " .,:/-%"
_UNITS = {"mph", "km/h", "m/s", "m/s²", "km", "mi", "m", "ft", "s", "ms", "GB", "MB", "Hz", "V", "A", "°C", "°F", "°", "%", "٪"}
_UNIT_PATTERN = "|".join(re.escape(unit) for unit in sorted(_UNITS, key=lambda s: (-len(s), s)))
_MEASUREMENT = rf"[+\-−]?\d+(?:[.,]\d+)*\s*(?:{_UNIT_PATTERN})(?!\w)"
_ATOMS = re.compile(rf"(?P<measurement>\({_MEASUREMENT}\)|\[{_MEASUREMENT}\]|{_MEASUREMENT})"
                    + r"|(?P<signed>[+\-−]\d+(?:[.,]\d+)*)|\s+|\S+")


def _kind(c: str) -> str:
  """L for a left-to-right letter, N for a digit, R for the rest (Arabic and the neutrals between)."""
  if ARABIC.match(c):
    return "N" if unicodedata.bidirectional(c) == "AN" else "R"
  if c.isdigit():
    return "N"
  return "L" if unicodedata.bidirectional(c) == "L" else "R"


def _runs(text: str) -> list[tuple[str, str]]:
  """The line as runs of one kind. A word or number keeps the spaces and separators inside it ("0.10.1", "Wi Fi"),
  not the ones after it; numbers and words stay separate runs, as the Unicode bidi algorithm orders them."""
  runs: list[tuple[str, str]] = []
  for match in _ATOMS.finditer(text):
    atom = match[0]
    latin = bool(match["measurement"] or match["signed"]) \
      or (any(c.isascii() and c.isalpha() for c in atom) and all(ord(c) < 128 or c in "°²" for c in atom))
    for c in atom:
      kind = "L" if latin else _kind(c)   # keep URLs, SSIDs and units like 12V intact
      if runs and (runs[-1][0] == kind or (runs[-1][0] != "R" and kind == "R" and c in _SEPARATORS)):
        runs[-1] = (runs[-1][0], runs[-1][1] + c)
      else:
        runs.append((kind, c))
  fixed: list[tuple[str, str]] = []
  for kind, run in runs:
    separators = _SEPARATORS.replace("%", "") if kind == "L" else _SEPARATORS
    core = run.rstrip(separators) if kind != "R" else run
    if kind != "R" and core != run:
      fixed += [(kind, core), ("R", run[len(core):])]
    else:
      fixed.append((kind, run))
  merged: list[tuple[str, str]] = []
  for i, (kind, run) in enumerate(fixed):   # spaces between two words ("Wi Fi") or two numbers belong to them
    between = kind == "R" and not run.strip(_SEPARATORS) and 0 < i < len(fixed) - 1 and fixed[i - 1][0] == fixed[i + 1][0] != "R"
    if between or (merged and merged[-1][0] == kind):
      merged[-1] = (merged[-1][0], merged[-1][1] + run)
    else:
      merged.append((kind, run))
  return merged


@functools.lru_cache(maxsize=4096)
def shape(text: str) -> str:
  """What to draw for one line: joined letters, the line in right-to-left order. Unchanged without Arabic."""
  if not ARABIC.search(text):
    return text
  return "".join(run[::-1].translate(_MIRROR) if kind == "R" else run for kind, run in reversed(_runs(join(text))))
