"""Read operational onroad alert text without importing the driving stack.

Alert constructors don't use tr(): their English is sent over messaging and translated by Tandem when drawn.
Follow their text arguments, local assignments and f-strings; leave live values (speeds, process names, etc.) as holes.
"""
from __future__ import annotations

import ast
from collections.abc import Callable
from itertools import product
from pathlib import Path

TEXT_ARGS = {"Alert": 2, "NoEntryAlert": 2, "NormalPermanentAlert": 2, "StartupAlert": 2,
             "SoftDisableAlert": 1, "UserSoftDisableAlert": 1, "ImmediateDisableAlert": 1,
             "soft_disable_alert": 1, "user_soft_disable_alert": 1}
TEXT_NAMES = {"alert_text_1", "alert_text_2"}
# Optional themed jokes and holiday greetings aren't operational driving instructions.
NOVELTY = {"accel30", "accel35", "accel40", "dejaVuCurve", "firefoxSteerSaturated", "hal9000",
           "openpilotCrashedRandomEvent", "thisIsFineSteerSaturated", "toBeContinued", "vCruise69",
           "yourFrogTriedToKillMe", "youveGotMail", "goatSteerSaturated"}


def _name(node: ast.expr) -> str:
  return getattr(node, "id", "") or getattr(node, "attr", "")


def _texts(node: ast.expr, bindings: dict[str, list[ast.expr]], seen: frozenset[str] = frozenset()) -> list[str]:
  if isinstance(node, ast.Constant) and isinstance(node.value, str):
    return [node.value]
  if isinstance(node, ast.Name) and node.id not in seen:
    values = [_texts(value, bindings, seen | {node.id}) for value in bindings.get(node.id, [])]
    return [s for texts in values for s in texts] if all(values) else []
  if isinstance(node, ast.IfExp):
    return _texts(node.body, bindings, seen) + _texts(node.orelse, bindings, seen)
  if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
    return [a + b for a, b in product(_texts(node.left, bindings, seen), _texts(node.right, bindings, seen))]
  if isinstance(node, ast.JoinedStr):
    parts = [_texts(v.value, bindings, seen) or ["{}"] if isinstance(v, ast.FormattedValue) else [v.value] for v in node.values]
    return ["".join(parts) for parts in product(*parts)]
  return []


class _Alerts(ast.NodeVisitor):
  def __init__(self, add: Callable[[str, str | None, int], None]):
    self.add = add
    self.bindings: dict[str, list[ast.expr]] = {}
    self.base = ""

  def text(self, node: ast.expr) -> None:
    texts = sorted(set(_texts(node, self.bindings)), key=lambda s: (len(s), s))
    # Upstream spells English plural suffixes inside f-strings. Store a real gettext plural, never a suffix hole.
    if len(texts) == 2 and "{}" in texts[0] \
       and any(texts[1] == texts[0][:i] + "s" + texts[0][i:] for i in range(len(texts[0]) + 1)):
      self.add(texts[0], texts[1], node.lineno)
      return
    for text in texts:
      self.add(text, None, node.lineno)

  def visit_ClassDef(self, node: ast.ClassDef) -> None:
    previous = self.base
    self.base = next((_name(b) for b in node.bases if _name(b) in TEXT_ARGS), "")
    self.generic_visit(node)
    self.base = previous

  def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
    if node.name == "holiday_alert":
      return
    previous = self.bindings
    self.bindings = {name: list(values) for name, values in previous.items()}
    for child in ast.walk(node):
      if isinstance(child, ast.Assign):
        for target in child.targets:
          if isinstance(target, ast.Name):
            self.bindings.setdefault(target.id, []).append(child.value)
    for arg, default in zip(node.args.args[len(node.args.args) - len(node.args.defaults):], node.args.defaults, strict=True):
      if arg.arg in TEXT_NAMES:
        self.text(default)
    self.generic_visit(node)
    self.bindings = previous

  def visit_Dict(self, node: ast.Dict) -> None:
    for key, value in zip(node.keys, node.values, strict=True):
      if isinstance(key, ast.Attribute) and _name(key.value) == "StarPilotEventName" and key.attr in NOVELTY:
        continue
      self.visit(value)

  def visit_Assign(self, node: ast.Assign) -> None:
    if any(isinstance(t, ast.Attribute) and t.attr in TEXT_NAMES for t in node.targets):
      self.text(node.value)
    self.generic_visit(node)

  def visit_Call(self, node: ast.Call) -> None:
    name = _name(node.func)
    if name == "__init__" and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call) \
       and _name(node.func.value.func) == "super":
      name = self.base
    if name in TEXT_ARGS:
      for arg in node.args[:TEXT_ARGS[name]]:
        self.text(arg)
      for kw in node.keywords:
        if kw.arg in TEXT_NAMES:
          self.text(kw.value)
    self.generic_visit(node)


def collect(path: Path, add: Callable[[str, str | None, int], None]) -> None:
  """Call add(msgid, plural, line) for the text sent by onroad alert constructors and callbacks."""
  _Alerts(add).visit(ast.parse(path.read_text(encoding="utf-8")))
