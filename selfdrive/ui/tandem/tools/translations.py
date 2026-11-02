#!/usr/bin/env python3
"""Tandem's translation catalog (i18n.py reads it).

  extract          Collects the text Tandem draws into translations/tandem.pot: each string constant in the package,
                   and each f-string as a template with {} for its values ("Sets {} options").
  update [codes]   Merges tandem.pot into translations/tandem_<code>.po for each code given and each that exists:
                   new strings come in untranslated, translations are kept, strings the code no longer has are dropped.
  status           How much of each language is translated.

Run extract and update after changing Tandem's wording; tests/test_translations.py fails until then.
Codes are StarPilot's (languages.json without "main_"): de, es, fr, ja, ko, pt-BR, tr, uk, ar, th, zh-CHS, zh-CHT.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
OUT = PACKAGE / "translations"
SKIP_DIRS = {"tests", "tools", "translations", "design", "assets", "__pycache__"}
SKIP_FILES = {"arabic.py", "speech.py", "speech_native.py", "i18n.py"}   # tables and worker processes, not drawn text
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:/\\-]+$")


def _is_text(value: str) -> bool:
  """Words a driver reads, not param keys, file names, icon names or formats."""
  value = value.strip()
  if not value or not any(c.isalpha() for c in value) or value.startswith(("http", "/", "#", ".")):
    return False
  if len(value) < 2:
    return False
  if " " not in value:   # one word: a label like "Off" or "Weather", not "SteerKP", "wifi_lock" or "main_en"
    return bool(_IDENTIFIER.match(value)) and value[0].isupper() and "_" not in value \
      and not any(c.isupper() for c in value[1:]) and not value.endswith((".py", ".png", ".json", ".fnt"))
  return not value.startswith("{") or any(c.isalpha() for c in value.replace("{}", ""))


_NOT_SHOWN = {"print", "debug", "info", "warning", "error", "exception", "_log", "log", "event", "getenv", "get", "put", "put_bool",
              "get_bool", "get_int", "get_float", "get_str", "put_nonblocking", "startswith", "endswith", "split", "join", "replace",
              "environ", "setdefault", "Path", "open", "glob", "icon", "write", "remove_param"}


def _call_name(node: ast.Call) -> str:
  return getattr(node.func, "attr", None) or getattr(node.func, "id", "")


def _template(node: ast.JoinedStr) -> str | None:
  parts = []
  for piece in node.values:
    if isinstance(piece, ast.Constant):
      parts.append(str(piece.value))
    else:
      parts.append("{}")
  text = "".join(parts)
  return text if "{}" in text and any(c.isalpha() for c in text.replace("{}", "")) and _is_text(text.replace("{}", "X")) else None


def _concat(node: ast.expr) -> str | None:
  """The text of a + chain of strings and f-strings, or None when any part isn't one."""
  if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
    left, right = _concat(node.left), _concat(node.right)
    return None if left is None or right is None else left + right
  if isinstance(node, ast.Constant) and isinstance(node.value, str):
    return node.value
  if isinstance(node, ast.JoinedStr):
    return "".join(str(p.value) if isinstance(p, ast.Constant) else "{}" for p in node.values)
  return None


def files() -> list[Path]:
  return sorted(p for p in PACKAGE.rglob("*.py") if not SKIP_DIRS & set(p.relative_to(PACKAGE).parts) and p.name not in SKIP_FILES)


def strings() -> dict[str, list[str]]:
  """msgid -> where it appears ("settings/display.py:201")."""
  found: dict[str, list[str]] = {}
  for path in files():
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    in_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    annotations = [n.annotation for n in ast.walk(tree) if isinstance(n, (ast.arg, ast.AnnAssign)) and n.annotation] + \
      [n.returns for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns]
    logged = [n for n in ast.walk(tree) if isinstance(n, ast.Raise) or isinstance(n, ast.Call) and _call_name(n) in _NOT_SHOWN]
    keywords = [n.args[5] for n in ast.walk(tree) if isinstance(n, ast.Call) and _call_name(n) in ("Entry", "_place") and len(n.args) > 5] + \
      [k.value for n in ast.walk(tree) if isinstance(n, ast.Call) for k in n.keywords if k.arg == "words"]   # search words, never drawn
    exported = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in n.targets)]
    skip = docstrings | in_fstring | {id(c) for n in logged + annotations + exported + keywords for c in ast.walk(n)}
    joined = {}   # "a " + "b" (or with f-strings) is one string at runtime
    for node in ast.walk(tree):
      if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and id(node) not in skip:
        text = _concat(node)
        if text is not None:
          joined[id(node)] = text
          skip |= {id(c) for c in ast.walk(node) if c is not node}
    for node in ast.walk(tree):
      text = None
      if id(node) in joined:
        text = joined[id(node)] if _is_text(joined[id(node)].replace("{}", "X")) else None
      elif isinstance(node, ast.JoinedStr) and id(node) not in skip:
        text = _template(node)
      elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
        text = node.value if _is_text(node.value) else None
      if text:
        found.setdefault(text, []).append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
  return found


def _quote(text: str) -> str:
  return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def _header(code: str) -> str:
  return ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
          + f'"Language: {code}\\n"\n"X-Source: Tandem (selfdrive/ui/tandem/tools/translations.py)\\n"\n')


def write(path: Path, code: str, entries: dict[str, list[str]], translated: dict[str, str], notes: dict[str, str]) -> None:
  out = [_header(code)]
  for msgid, where in entries.items():
    block = ""
    if notes.get(msgid):
      block += f"#. {notes[msgid]}\n"
    block += "".join(f"#: {w}\n" for w in where[:3])
    if "{}" in msgid:
      block += "#, python-brace-format\n"
    block += f"msgid {_quote(msgid)}\nmsgstr {_quote(translated.get(msgid, ''))}\n"
    out.append(block)
  path.write_text("\n".join(out), encoding="utf-8")


def _i18n():
  import importlib.util
  spec = importlib.util.spec_from_file_location("tandem_i18n", PACKAGE / "i18n.py")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def read(path: Path) -> tuple[dict[str, str], dict[str, str]]:
  """(msgid -> msgstr, msgid -> translator note) from a Tandem .po."""
  if not path.is_file():
    return {}, {}
  text = path.read_text(encoding="utf-8")
  i18n = _i18n()
  notes, note = {}, ""
  for line in text.splitlines():
    if line.startswith("#. "):
      note = line[3:]
    elif line.startswith('msgid "'):
      if note:
        notes[i18n._unquote(line[7:-1])] = note
      note = ""
  return i18n.parse_po(text), notes


def extract() -> dict[str, list[str]]:
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
    done = sum(bool(translated.get(k)) for k in entries)
    print(f"tandem_{code}.po: {done}/{len(entries)} translated")


def status() -> None:
  entries = strings()
  for path in sorted(OUT.glob("tandem_*.po")):
    translated, _ = read(path)
    print(f"{path.stem}: {sum(bool(translated.get(k)) for k in entries)}/{len(entries)}")


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
