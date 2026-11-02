"""Tandem's translations: its own catalog, looked up where text is drawn.

Tandem's screens are written in English. draw.py passes every string it measures or draws through translate(), which
returns it in the language picked in Device › General › Language, from translations/tandem_<code>.po (StarPilot's
codes: de, ja, zh-CHS...). Text built at runtime is matched by its template: the catalog's "Sets {} options" translates
"Sets 12 options", keeping the 12. Anything not in the catalog (street names, Wi-Fi names, numbers) comes back as is.

The catalog is Tandem's own, beside StarPilot's app_<code>.po, so upstream merges never touch it.
tools/translations.py extracts the strings into translations/tandem.pot and merges new ones into each language.
"""
from __future__ import annotations

import re
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent / "translations"
_HOLE = re.compile(r"\{\}")
_MEASURED = re.compile(r"^(.*[^\d\s]) (\d[\d.,:]*\s?[^\s\d]{0,4})$")
_OUT_HOLE = re.compile(r"\{(\d*)\}")   # a translation may number its holes ({1} {0}) to put the values in its own order


class Catalog:
  def __init__(self, entries: dict[str, str]):
    self.exact = {k: v for k, v in entries.items() if v and "{}" not in k}
    self.folded = {k.casefold(): v for k, v in self.exact.items()}   # names the code lowercases ("Waiting: wi-fi")
    self.templates = []   # (pattern, translation) for msgids with {} holes, longest first so specific ones win
    for msgid, msgstr in sorted(entries.items(), key=lambda kv: -len(kv[0])):
      if msgstr and "{}" in msgid and _holes_fit(msgid, msgstr) and msgid.strip("{} "):
        parts = [re.escape(p) for p in _HOLE.split(msgid)]
        self.templates.append((re.compile("(.+?)".join(parts) + "$", re.S), msgstr))
    self._cache: dict[str, str] = {}

  def translate(self, text: str, depth: int = 0) -> str:
    hit = self._cache.get(text)
    if hit is not None:
      return hit
    out = self.exact.get(text)
    if out is None:
      out = text
      if any(c.isalpha() for c in text) and depth < 3:
        for pattern, msgstr in self.templates:
          m = pattern.match(text)
          if m:   # the values are translated too: "{} path" with "Standard" reads "Estándar" in Spanish
            out = _fill(msgstr, tuple(self.translate(v, depth + 1) for v in m.groups()))
            break
        else:
          out = self._pieces(text, depth)
    if len(self._cache) > 20000:   # dynamic text (times, distances) shouldn't grow it forever
      self._cache.clear()
    self._cache[text] = out
    return out


  def _pieces(self, text: str, depth: int) -> str:
    """Text the code built from catalog strings: a case change, a " · " summary, or a comma list of names."""
    if text.casefold() in self.folded:
      return self.folded[text.casefold()]
    if " · " in text:   # "Standard · Auto lane change"
      return " · ".join(self.translate(part, depth + 1) for part in text.split(" · "))
    m = _MEASURED.match(text)
    if m and m.group(1).casefold() in self.folded:   # "Drives 21.0 GB": the name, then its value as is
      return f"{self.folded[m.group(1).casefold()]} {m.group(2)}"
    parts = text.split(", ")
    if len(parts) > 1 and all(p.casefold() in self.folded for p in parts):   # "Green light, lead departure"
      return ", ".join(self.folded[p.casefold()] for p in parts)
    return text


def _holes_fit(msgid: str, msgstr: str) -> bool:
  """A translation fills every hole in order ({}), or numbers the ones it uses ({1} {0}), and may leave one out: an
  English plural "s" ("{} alert{}") has no place in Japanese."""
  holes, count = _OUT_HOLE.findall(msgstr), msgid.count("{}")
  if all(h == "" for h in holes):
    return len(holes) == count
  return all(h.isdigit() and int(h) < count for h in holes)


def _fill(msgstr: str, values: tuple[str, ...]) -> str:
  order = iter(values)
  return _OUT_HOLE.sub(lambda h: values[int(h.group(1))] if h.group(1) else next(order), msgstr)


_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
_QUOTED = re.compile(r'^(msgid|msgstr|)\s*"(.*)"$')


def _unquote(text: str) -> str:
  return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), text)


def parse_po(text: str) -> dict[str, str]:
  """msgid -> msgstr from a .po file (single forms, the kind tools/translations.py writes)."""
  entries: dict[str, str] = {}
  msgid = msgstr = None
  field = ""
  for line in text.splitlines() + [""]:
    line = line.strip()
    m = _QUOTED.match(line)
    if m and (m.group(1) or field):
      field = m.group(1) or field
      value = _unquote(m.group(2))
      if field == "msgid":
        msgid = value if m.group(1) else (msgid or "") + value
      else:
        msgstr = value if m.group(1) else (msgstr or "") + value
    elif not line or line.startswith("#"):
      if msgid and msgstr is not None:
        entries[msgid] = msgstr
      if not line.startswith("#") or msgid is not None:
        msgid = msgstr = None
        field = ""
  return entries


def load(code: str) -> Catalog:
  path = CATALOG_DIR / f"tandem_{code}.po"
  if not path.is_file():
    return Catalog({})
  return Catalog(parse_po(path.read_text(encoding="utf-8")))


def _language() -> str:
  try:
    from openpilot.system.ui.lib.multilang import multilang
    return multilang.language
  except ImportError:   # headless tools without the full stack: English
    return "en"


_loaded: dict[str, Catalog] = {}


def translate(text: str) -> str:
  code = _language()
  if code in ("en", "main_en") or not text:
    return text
  catalog = _loaded.get(code)
  if catalog is None:
    catalog = _loaded[code] = load(code.removeprefix("main_"))
  return catalog.translate(text)
