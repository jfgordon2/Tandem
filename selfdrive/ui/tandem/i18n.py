"""Tandem's translations: its own catalog, in the language picked in Device › General › Language.

Tandem's screens are written in English, and the text a driver reads is marked where it's written:

  N_("Driving Style")                 text in a table or a widget's label: stays English in the code and is translated
                                      where it's drawn, so a new language applies at once without rebuilding anything
  N_("Set up", context="action")      the same, for English that means two things (a button, or a status)
  t_("Sets {} options", count)        text built at runtime: translated now, with its values in their place
  tn_("{} alert", "{} alerts", n)     a count, in each language's plural forms

draw.py passes everything it measures or draws through translate(), so N_ text (and the words inside summaries joined
with " · ") comes out translated; text it doesn't know (street names, Wi-Fi names, numbers) is drawn as is.
tools/translations.py collects the marked strings into translations/tandem.pot; translations/tandem_<code>.po hold the
languages (StarPilot's codes: de, ja, zh-CHS...). The catalog is Tandem's own, so upstream merges never touch it.

With TANDEM_PSEUDO=1 every marked string is drawn as "[Text ~~~]": text without the brackets wasn't marked, and the
extra length shows where a longer language won't fit (tools/render/scene_pseudo.py).
"""
from __future__ import annotations

import math
import os
import re
from collections.abc import Callable
from pathlib import Path
from collections.abc import Iterator

CATALOG_DIR = Path(__file__).resolve().parent / "translations"
CONTEXT = "\x04"   # gettext's separator between a context and its msgid in a catalog key
_HOLE = re.compile(r"\{\}")
_MEASURED = re.compile(r"^(.*[^\d\s]) (\d[\d.,:]*\s?[^\s\d]{0,4})$")
_OUT_HOLE = re.compile(r"\{(\d*)\}")   # a translation may number its holes ({1} {0}) to put the values in its own order
_TURKISH_UPPER = {ord("i"): 0x0130, 0x0131: ord("I")}   # Unicode casing: i → İ, ı → I


class Msg(str):
  """English text marked with a context, so draw-time lookup finds the right translation."""
  context: str | None = None

  def __new__(cls, text: str, context: str | None) -> Msg:
    msg = super().__new__(cls, text)
    msg.context = context
    return msg


def key(msgid: str, context: str | None = None) -> str:
  return f"{context}{CONTEXT}{msgid}" if context else msgid


# Plural forms, as gettext numbers them, for StarPilot's languages; anything else uses English's (one, other).
PLURALS: dict[str, Callable[[int], int]] = {
  "ja": lambda n: 0, "ko": lambda n: 0, "zh-CHS": lambda n: 0, "zh-CHT": lambda n: 0, "th": lambda n: 0,
  "fr": lambda n: 0 if n <= 1 else 1, "pt-BR": lambda n: 0 if n <= 1 else 1,
  "uk": lambda n: 0 if n % 10 == 1 and n % 100 != 11 else 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2,
  "ar": lambda n: 0 if n == 0 else 1 if n == 1 else 2 if n == 2 else 3 if 3 <= n % 100 <= 10 else 4 if n % 100 >= 11 else 5,
}


def plural_index(code: str, n: int) -> int:
  return int(PLURALS.get(code, lambda n: 0 if n == 1 else 1)(n))


class Catalog:
  """One language's translations: plain text, templates with {} holes, and plural forms."""

  def __init__(self, entries: dict[str, str | list[str]], code: str = "en", english_plurals: dict[str, str] | None = None,
               drawn: set[str] | None = None):
    """Makes a catalog.

    Args:
      entries: Catalog key (see key()) to its translation, or to its plural forms.
      code: The language code, e.g. "fr".
      english_plurals: Catalog key to its English plural, so text drawn in the plural form still finds its entry.
      drawn: The templates matched against text as it's drawn (StarPilot's, formatted before Tandem sees them); Tandem's
        own are filled by t_() and tn_(). None matches them all.
    """
    self.code = code
    self._english_plurals = {k: (v,) for k, v in (english_plurals or {}).items()}
    self.plurals = {k: v for k, v in entries.items() if isinstance(v, list)}
    singles = {k: v for k, v in entries.items() if isinstance(v, str) and v}
    self.exact = {k: v for k, v in singles.items() if "{}" not in k}
    self.marked = singles   # every key with a translation, templates included, for t_()
    self.folded = {k.casefold(): v for k, v in self.exact.items() if CONTEXT not in k}   # names the code lowercases
    # (pattern, translation) for msgids with {} holes, longest first so specific ones win; a plural has its forms
    self.templates: list[tuple[re.Pattern[str], str | list[str]]] = []
    for msgid, msgstr in sorted(singles.items(), key=lambda kv: -len(kv[0])):
      if "{}" in msgid and CONTEXT not in msgid and _holes_fit(msgid, msgstr) and msgid.strip("{} ") \
         and (drawn is None or msgid in drawn):
        parts = [re.escape(p) for p in _HOLE.split(msgid)]
        self.templates.append((re.compile("(.+?)".join(parts) + "$", re.S), msgstr))
    for msgid, forms in self.plurals.items():   # StarPilot's trn() text arrives formatted: "2 regions"
      if CONTEXT in msgid or "{}" not in msgid or not all(forms) or (drawn is not None and msgid not in drawn):
        continue
      for english in {msgid, *self._english_plurals.get(msgid, ())}:
        parts = [re.escape(p) for p in _HOLE.split(english)]
        self.templates.append((re.compile("(.+?)".join(parts) + "$", re.S), forms))
    self.templates.sort(key=lambda pt: -len(pt[0].pattern))
    self._cache: dict[str, str] = {}

  def translate(self, text: str, depth: int = 0) -> str:
    """Drawn text, in this language: an exact entry, a template's match, or the pieces it was built from."""
    context = getattr(text, "context", None)
    if context and key(text, context) in self.exact:
      return self.exact[key(text, context)]
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
            if isinstance(msgstr, list):   # a plural: the form for the count in its first hole
              n = int(m.group(1)) if m.group(1).isdigit() else 2
              msgstr = msgstr[min(plural_index(self.code, n), len(msgstr) - 1)]
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
    for joint in (" · ", " › "):   # "Standard · Auto lane change", "Driving › Tuner Mode"
      if joint in text:
        return joint.join(self.translate(part, depth + 1) for part in text.split(joint))
    m = _MEASURED.match(text)
    if m and m.group(1).casefold() in self.folded:   # "Drives 21.0 GB": the name, then its value as is
      return f"{self.folded[m.group(1).casefold()]} {m.group(2)}"
    parts = text.split(", ")
    if len(parts) > 1 and all(p.casefold() in self.folded for p in parts):   # "Green light, lead departure"
      return ", ".join(self.folded[p.casefold()] for p in parts)
    return text

  def template(self, msgid: str, values: tuple, context: str | None = None) -> str:
    """t_(): the marked template in this language, its holes filled with the values (themselves translated)."""
    msgstr = self.marked.get(key(msgid, context)) or self.marked.get(msgid)
    if msgstr is None or (values and not _holes_fit(msgid, msgstr)):
      msgstr = msgid
    return _fill(msgstr, tuple(self.translate(str(v)) for v in values)) if values else msgstr

  def plural(self, singular: str, plural: str, n: int, values: tuple, context: str | None = None) -> str:
    """tn_(): the form this language uses for n."""
    forms = self.plurals.get(key(singular, context))
    if forms and all(forms):
      msgstr = forms[min(plural_index(self.code, n), len(forms) - 1)]
    else:
      msgstr = singular if n == 1 else plural
    return _fill(msgstr, tuple(str(v) for v in values))


def _holes_fit(msgid: str, msgstr: str) -> bool:
  """A translation fills every hole in order ({}), or numbers the ones it uses ({1} {0}), and may leave one out."""
  holes, count = _OUT_HOLE.findall(msgstr), msgid.count("{}")
  if all(h == "" for h in holes):
    return len(holes) == count
  return all(h.isdigit() and int(h) < count for h in holes)


def _fill(msgstr: str, values: tuple[str, ...]) -> str:
  order = iter(values)
  return _OUT_HOLE.sub(lambda h: values[int(h.group(1))] if h.group(1) else next(order, ""), msgstr)


# ── .po files ──

_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
_QUOTED = re.compile(r'^(msgctxt|msgid|msgid_plural|msgstr|msgstr\[\d+\]|)\s*"(.*)"$')


def _unquote(text: str) -> str:
  return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), text)


def english_plurals(text: str) -> dict[str, str]:
  """Catalog key -> its English plural (msgid_plural), for the plural entries in a .po file."""
  return {key(fields["msgid"], fields.get("msgctxt")): fields["msgid_plural"]
          for fields, _ in _po_entries(text) if fields.get("msgid") and "msgid_plural" in fields}


def drawn_templates(text: str) -> set[str]:
  """Catalog keys flagged "drawn" in a .po file (tools/translations.py marks StarPilot's formatted strings)."""
  return {key(fields["msgid"], fields.get("msgctxt"))
          for fields, flags in _po_entries(text) if fields.get("msgid") and "drawn" in flags}


def _po_entries(text: str) -> Iterator[tuple[dict[str, str], set[str]]]:
  """Read complete PO entries, including continued lines and their flags, without leaking a previous entry's context."""
  fields: dict[str, str] = {}
  flags: set[str] = set()
  last = ""
  for line in text.splitlines() + [""]:
    line = line.strip()
    m = _QUOTED.match(line)
    complete = "msgstr" in fields or any(f.startswith("msgstr[") for f in fields)
    if fields and (not line or (complete and (line.startswith("#") or (m and m.group(1) in ("msgctxt", "msgid"))))):
      yield fields, flags
      fields, flags, last = {}, set(), ""
    if line.startswith("#,"):
      flags.update(f.strip() for f in line[2:].split(","))
    if m and (m.group(1) or last):
      field = m.group(1) or last
      fields[field] = (fields.get(field, "") if not m.group(1) else "") + _unquote(m.group(2))
      last = field
    elif not line:
      fields, flags, last = {}, set(), ""


def parse_po(text: str) -> dict[str, str | list[str]]:
  """Catalog key (see key()) -> msgstr, or the list of plural forms, from a .po file."""
  entries: dict[str, str | list[str]] = {}
  for fields, _ in _po_entries(text):
    if fields.get("msgid"):
      k = key(fields["msgid"], fields.get("msgctxt"))
      if "msgid_plural" in fields:
        forms = sorted((int(f[7:-1]), v) for f, v in fields.items() if f.startswith("msgstr["))
        entries[k] = [v for _, v in forms]
      elif "msgstr" in fields:
        entries[k] = fields["msgstr"]
  return entries


def pseudo(text: str) -> str:
  """The pseudo-language form: bracketed, holes kept, about 30% longer, as German and French often are."""
  return f"[{text} {'~' * max(1, math.ceil(len(text) * 0.3))}]"


def load(code: str) -> Catalog:
  """The catalog for a language code: its .po file, empty when there's none, or the pseudo-language for layout checks."""
  if code == "pseudo":
    entries = parse_po((CATALOG_DIR / "tandem.pot").read_text(encoding="utf-8"))
    out: dict[str, str | list[str]] = {}
    for k, v in entries.items():
      msgid = k.split(CONTEXT)[-1]
      out[k] = [pseudo(msgid), pseudo(msgid)] if isinstance(v, list) else pseudo(msgid)
    pot = (CATALOG_DIR / "tandem.pot").read_text(encoding="utf-8")
    return Catalog(out, code, english_plurals(pot), drawn_templates(pot))
  path = CATALOG_DIR / f"tandem_{code}.po"
  if not path.is_file():
    return Catalog({}, code)
  text = path.read_text(encoding="utf-8")
  return Catalog(parse_po(text), code, english_plurals(text), drawn_templates(text))


def _language() -> str:
  if os.environ.get("TANDEM_PSEUDO") == "1":
    return "pseudo"
  try:
    from openpilot.system.ui.lib.multilang import multilang
    return multilang.language
  except ImportError:   # headless tools without the full stack: English
    return "en"


_loaded: dict[str, Catalog] = {}


def _catalog() -> Catalog | None:
  code = _language().removeprefix("main_")
  if code == "en":
    return None
  catalog = _loaded.get(code)
  if catalog is None:
    catalog = _loaded[code] = load(code)
  return catalog


# ── Marking ──

def N_(text: str, context: str | None = None) -> str:
  """Marks English for the catalog; it's translated where it's drawn. With a context, it keeps it until then."""
  return Msg(text, context) if context else text


def t_(text: str, *values: object, context: str | None = None) -> str:
  """Marked text built now: its translation, with values in its {} holes."""
  catalog = _catalog()
  if catalog is None:
    return _fill(text, tuple(str(v) for v in values)) if values else text
  return catalog.template(text, values, context)


def tn_(singular: str, plural: str, n: int, *values: object, context: str | None = None) -> str:
  """A count: "{} alert" / "{} alerts" in the forms of the driver's language. values default to (n,)."""
  values = values or (n,)
  catalog = _catalog()
  if catalog is None:
    return _fill(singular if n == 1 else plural, tuple(str(v) for v in values))
  return catalog.plural(singular, plural, n, values, context)


def translate(text: str) -> str:
  """draw.py's lookup for everything it draws."""
  if not text:
    return text
  catalog = _catalog()
  return text if catalog is None else catalog.translate(text)


def uppercase(text: str) -> str:
  """Capital captions in the selected language: Turkish i and ı have different uppercase forms."""
  if _language().removeprefix("main_") == "tr":
    text = text.translate(_TURKISH_UPPER)
  return text.upper()
