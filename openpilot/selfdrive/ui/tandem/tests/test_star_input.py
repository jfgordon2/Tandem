"""TandemStarSession (star_input.py) against StarPilot's StarShellSession, so a merge that changes the session fails here.

The input methods Tandem inherits (the wheel, favorites, Android Auto taps and their permission checks) read the session's
attributes. This reads both classes' source: every attribute those methods read must be set by Tandem's __init__ (or
lazily by StarPilot's own methods), and every attribute both __init__s set must be set by the same code.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
UPSTREAM = ROOT / "openpilot/starpilot/ui/runtime_app.py"
TANDEM = ROOT / "openpilot/selfdrive/ui/tandem/star_input.py"
# The methods Tandem calls: ui.py's frame loop and TandemInput.poll, and the controller runtime's callbacks.
ROOTS = ("_poll_wheel", "_poll_projection_bookmark", "_poll_projection_slc", "_favorite_actions", "native_favorite_actions",
         "_favorite_authority", "_bookmark_authority", "feature_request")
# Set differently on purpose: no screens, PiP renderer, Home stats or visual preview here.
KNOWN_DIFFERENCES = {"adapter", "pip_owner", "home_stats_source", "bluetooth_source", "_visual_preview_flags", "_native_favorite_actions",
                     "_publish_bookmark", "network_layer", "settings_layer", "model_source", "_home_model", "map_source",
                     "system_power_action", "onroad_map", "onroad_jetlink"}


def _class(path: Path, name: str) -> ast.ClassDef:
  return next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == name)


def _init_assignments(cls: ast.ClassDef) -> dict[str, list[str]]:
  """Every self.<name> = <value> in __init__ (annotated or not, in nested blocks too), as each value's AST, in order."""
  init = next(f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "__init__")
  out: dict[str, list[str]] = {}
  for node in ast.walk(init):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) and node.value else []
    for target in targets:
      for t in target.elts if isinstance(target, ast.Tuple) else [target]:
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
          out.setdefault(t.attr, []).append(ast.dump(node.value))  # type: ignore[union-attr]
  return out


def _closure(cls: ast.ClassDef) -> tuple[set[str], set[str], set[str]]:
  """(methods reached from ROOTS, attributes they read, attributes they set or only probe with getattr/hasattr)."""
  methods = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
  seen: set[str] = set()
  read: set[str] = set()
  lazy: set[str] = set()
  todo = list(ROOTS)
  while todo:
    name = todo.pop()
    if name in seen or name not in methods:
      continue
    seen.add(name)
    for node in ast.walk(methods[name]):
      if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        (todo if node.attr in methods else (lazy if isinstance(node.ctx, ast.Store) else read)).append(node.attr) \
          if node.attr in methods else (lazy if isinstance(node.ctx, ast.Store) else read).add(node.attr)
      if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr", "setattr")
          and len(node.args) > 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == "self"
          and isinstance(node.args[1], ast.Constant)):
        lazy.add(str(node.args[1].value))
  return seen, read, lazy


def test_every_attribute_the_input_methods_read_is_set() -> None:
  upstream = _class(UPSTREAM, "StarShellSession")
  methods, read, lazy = _closure(upstream)
  assert set(ROOTS) <= methods, "a method Tandem calls is gone from StarShellSession"
  set_here = set(_init_assignments(_class(TANDEM, "TandemStarSession")))
  missing = sorted(read - set_here - lazy)
  assert not missing, f"StarShellSession's input methods now read {missing}; set them in TandemStarSession.__init__"


def test_shared_attributes_are_set_by_the_same_code_as_starpilots() -> None:
  upstream = _init_assignments(_class(UPSTREAM, "StarShellSession"))
  tandem = _init_assignments(_class(TANDEM, "TandemStarSession"))
  changed = sorted(name for name, value in tandem.items()
                   if name in upstream and name not in KNOWN_DIFFERENCES and upstream[name] != value)
  assert not changed, f"StarShellSession now sets {changed} differently; copy its code into TandemStarSession.__init__"
  stale = sorted(KNOWN_DIFFERENCES - set(upstream))
  assert not stale, f"StarShellSession no longer sets {stale}; drop them from KNOWN_DIFFERENCES"


def test_without_tandems_screens_ui_py_keeps_its_own_path() -> None:
  from openpilot.selfdrive.ui.tandem.screens import star_input
  assert star_input(object(), big_ui=True, environment={"STARPILOT_UI": "upstream"}) == (None, None)
  assert star_input(object(), big_ui=False, environment={}) == (None, None)


def test_a_failure_to_start_leaves_the_screens_as_before(monkeypatch) -> None:
  import sys
  from types import ModuleType, SimpleNamespace
  from openpilot.selfdrive.ui.tandem.screens import star_input
  broken = ModuleType("openpilot.selfdrive.ui.tandem.star_input")

  def fail(layout: object) -> tuple:
    raise RuntimeError("no socket")
  broken.star_input = fail  # type: ignore[attr-defined]
  logged: list = []
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.tandem.star_input", broken)
  monkeypatch.setitem(sys.modules, "openpilot.common.swaglog", SimpleNamespace(cloudlog=SimpleNamespace(exception=logged.append)))
  assert star_input(object(), big_ui=True, environment={}) == (None, None) and logged


def test_settings_are_tandems_on_a_comma_without_the_big_switch(monkeypatch) -> None:
  """On the device BIG isn't set; the big UI comes from the device type (gui_app.big_ui), as ui.py decides it."""
  import sys
  from types import ModuleType
  from openpilot.selfdrive.ui.tandem import screens
  from openpilot.system.ui.lib import application
  monkeypatch.delenv("BIG", raising=False)
  monkeypatch.setattr(application, "BIG_UI", False)
  monkeypatch.setattr(application.gui_app, "big_ui", lambda: True)   # a comma 3X
  fake = ModuleType("openpilot.selfdrive.ui.tandem.settings.essentials")
  fake.essentials_settings = lambda *args: "tandem settings"  # type: ignore[attr-defined]
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.tandem.settings.essentials", fake)
  assert screens.settings() == "tandem settings"
