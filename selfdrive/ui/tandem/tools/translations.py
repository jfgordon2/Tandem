#!/usr/bin/env python3
"""Tandem's translation catalog (i18n.py reads it).

  extract          Collects the marked text into translations/tandem.pot: every N_(), t_() and tn_() in the package
                   (with its context and plural), and the tr() / tr_noop() / trn() strings of the StarPilot screens
                   Tandem's adapters show text from (UPSTREAM), plus operational onroad and offroad alert text.
  update [codes]   Merges tandem.pot into translations/tandem_<code>.po for each code given and each that exists:
                   new strings come in untranslated, translations are kept, strings the code no longer has are dropped.
  status           How much of each language is translated.

Run update after changing Tandem's wording; tests/test_translations.py fails until then.
Codes are StarPilot's (languages.json without "main_"): de, es, fr, ja, ko, pt-BR, tr, uk, ar, th, zh-CHS, zh-CHT.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[2]
OUT = PACKAGE / "translations"
SKIP_DIRS = {"tests", "tools", "translations", "design", "assets", "__pycache__"}
MARKERS = {"N_": 1, "t_": 1, "tn_": 2}   # how many leading string arguments are catalog text
# StarPilot screens Tandem's Upstream adapters read text from: their tr(), tr_noop() and trn() strings join the catalog
UPSTREAM = ["selfdrive/ui/layouts/settings/starpilot/maps.py", "selfdrive/ui/layouts/settings/starpilot/model.py",
            "selfdrive/ui/layouts/settings/starpilot/vehicle.py", "selfdrive/ui/layouts/settings/starpilot/navigation.py",
            "selfdrive/ui/layouts/settings/software.py", "selfdrive/ui/layouts/settings/device.py",
            "selfdrive/ui/layouts/settings/developer.py", "selfdrive/ui/onroad/alert_renderer.py"]
UPSTREAM_CALLS = {"tr": 1, "tr_noop": 1, "trn": 2}
UPSTREAM_ALERTS = "selfdrive/selfdrived/alerts_offroad.json"   # the home screen's alert sentences ("%1" is filled in)
ONROAD_ALERTS = "selfdrive/selfdrived/events.py"
PLURAL_FORMS = {"ja": 1, "ko": 1, "zh-CHS": 1, "zh-CHT": 1, "th": 1, "uk": 3, "ar": 6}   # others: 2
PLURAL_EXPRESSIONS = {
  "fr": "n > 1", "pt-BR": "n > 1",
  "uk": "n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2",
  "ar": "n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5",
}


def _i18n():
  spec = importlib.util.spec_from_file_location("tandem_i18n", PACKAGE / "i18n.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


i18n = _i18n()


@dataclass
class Entry:
  msgid: str
  context: str | None = None
  plural: str | None = None
  where: list[str] = field(default_factory=list)
  drawn: bool = False   # matched against drawn text: an N_() template, or StarPilot's text formatted before Tandem draws it

  @property
  def key(self) -> str:
    return i18n.key(self.msgid, self.context)


def _text(node: ast.expr) -> str | None:
  """A string literal, or a + chain of them (long sentences are split over lines)."""
  if isinstance(node, ast.Constant) and isinstance(node.value, str):
    return node.value
  if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
    left, right = _text(node.left), _text(node.right)
    return None if left is None or right is None else left + right
  return None


def _call_name(node: ast.Call) -> str:
  return getattr(node.func, "attr", None) or getattr(node.func, "id", "")


def files() -> list[Path]:
  return sorted(p for p in PACKAGE.rglob("*.py") if not SKIP_DIRS & set(p.relative_to(PACKAGE).parts) and p.name != "i18n.py")


def _collect(found: dict[str, Entry], path: Path, label: str, calls: dict[str, int], upstream: bool) -> None:
  for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
    if not (isinstance(node, ast.Call) and _call_name(node) in calls and node.args):
      continue
    texts = [_text(a) for a in node.args[:calls[_call_name(node)]]]
    if texts[0] is None:
      if not upstream:
        raise SystemExit(f"{label}:{node.lineno}: {_call_name(node)}() needs a string literal")
      continue
    if upstream:   # StarPilot formats "{count} regions" before it's drawn
      texts = [re.sub(r"\{[^{}]*\}", "{}", x) if x else x for x in texts]
    context = next((_text(k.value) for k in node.keywords if k.arg == "context"), None)
    entry = Entry(texts[0], context, texts[1] if len(texts) > 1 else None)
    entry = found.setdefault(entry.key, entry)
    entry.where.append(f"{label}:{node.lineno}")
    entry.drawn |= upstream or _call_name(node) == "N_"


def strings() -> dict[str, Entry]:
  """Catalog key -> the marked text and where it appears."""
  found: dict[str, Entry] = {}
  for path in files():
    _collect(found, path, str(path.relative_to(PACKAGE)), MARKERS, upstream=False)
  for name in UPSTREAM:
    if (ROOT / name).is_file():
      _collect(found, ROOT / name, name, UPSTREAM_CALLS, upstream=True)
  if "{} region selected" in found:
    # DownloadView draws the controller's summary without " selected". Preserve its plural forms too.
    entry = found.setdefault("{} region", Entry("{} region", plural="{} regions", drawn=True))
    entry.where.append("settings/maps.py:DownloadView (summary without selected)")
  if (ROOT / UPSTREAM_ALERTS).is_file():
    import json
    for alert_key, alert in json.loads((ROOT / UPSTREAM_ALERTS).read_text(encoding="utf-8")).items():
      text = alert.get("text", "").replace("%1", "{}")
      if any(c.isalpha() for c in text.replace("{}", "")):
        entry = found.setdefault(text, Entry(text))
        entry.where.append(f"{UPSTREAM_ALERTS}:{alert_key}")
        entry.drawn = True
  if (ROOT / ONROAD_ALERTS).is_file():
    spec = importlib.util.spec_from_file_location("tandem_alert_strings", Path(__file__).with_name("alert_strings.py"))
    alerts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(alerts)

    def add_alert(text: str, plural: str | None, line: int) -> None:
      if any(c.isalpha() for c in text.replace("{}", "")):
        entry = found.setdefault(text, Entry(text, plural=plural))
        entry.where.append(f"{ONROAD_ALERTS}:{line}")
        entry.drawn = True

    alerts.collect(ROOT / ONROAD_ALERTS, add_alert)
  return found


# ── .po files ──

def _quote(text: str) -> str:
  return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def _header(code: str) -> str:
  forms = PLURAL_FORMS.get(code, 2)
  expression = PLURAL_EXPRESSIONS.get(code, "0" if forms == 1 else "n != 1")
  return ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
          + f'"Language: {code}\\n"\n"Plural-Forms: nplurals={forms}; plural=({expression});\\n"\n'
          + '"X-Source: Tandem (selfdrive/ui/tandem/tools/translations.py)\\n"\n')


def write(path: Path, code: str, entries: dict[str, Entry], translated: dict[str, str | list[str]], notes: dict[str, str]) -> None:
  out = [_header(code)]
  forms = PLURAL_FORMS.get(code, 2)
  for k, e in entries.items():
    block = f"#. {notes[k]}\n" if notes.get(k) else ""
    block += "".join(f"#: {w}\n" for w in e.where[:3])
    flags = ["python-brace-format"] if "{}" in e.msgid else []
    if "{}" in e.msgid and e.drawn:
      flags.append("drawn")   # i18n matches drawn text against it (t_() and tn_() fill theirs)
    if flags:
      block += f"#, {', '.join(flags)}\n"
    if e.context:
      block += f"msgctxt {_quote(e.context)}\n"
    block += f"msgid {_quote(e.msgid)}\n"
    value = translated.get(k, "")
    if e.plural is not None:
      values = value if isinstance(value, list) else []
      block += f"msgid_plural {_quote(e.plural)}\n"
      block += "".join(f"msgstr[{i}] {_quote(values[i] if i < len(values) else '')}\n" for i in range(forms))
    else:
      block += f"msgstr {_quote(value if isinstance(value, str) else '')}\n"
    out.append(block)
  path.write_text("\n".join(out), encoding="utf-8")


def read(path: Path) -> tuple[dict[str, str | list[str]], dict[str, str]]:
  """(key -> msgstr or plural forms, key -> translator note) from a Tandem .po."""
  if not path.is_file():
    return {}, {}
  text = path.read_text(encoding="utf-8")
  notes, note, context = {}, "", None
  for line in text.splitlines():
    if line.startswith("#. "):
      note = line[3:]
    elif line.startswith('msgctxt "'):
      context = i18n._unquote(line[9:-1])
    elif line.startswith('msgid "'):
      if note:
        notes[i18n.key(i18n._unquote(line[7:-1]), context)] = note
      note, context = "", None
  return i18n.parse_po(text), notes


def done(value) -> bool:
  return all(value) if isinstance(value, list) else bool(value)


def extract() -> dict[str, Entry]:
  entries = strings()
  OUT.mkdir(exist_ok=True)
  write(OUT / "tandem.pot", "", entries, {}, {})
  print(f"tandem.pot: {len(entries)} strings")
  return entries


def update(codes: list[str]) -> None:
  entries = extract()
  codes = sorted(set(codes) | {p.stem.removeprefix("tandem_") for p in OUT.glob("tandem_*.po")})
  for code in codes:
    path = OUT / f"tandem_{code}.po"
    translated, notes = read(path)
    write(path, code, entries, translated, notes)
    print(f"tandem_{code}.po: {sum(done(translated.get(k, '')) for k in entries)}/{len(entries)} translated")


def status() -> None:
  entries = strings()
  for path in sorted(OUT.glob("tandem_*.po")):
    translated, _ = read(path)
    print(f"{path.stem}: {sum(done(translated.get(k, '')) for k in entries)}/{len(entries)}")


if __name__ == "__main__":
  command, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
  if command == "extract":
    extract()
  elif command == "update":
    update(args)
  elif command == "status":
    status()
  else:
    raise SystemExit(__doc__)
