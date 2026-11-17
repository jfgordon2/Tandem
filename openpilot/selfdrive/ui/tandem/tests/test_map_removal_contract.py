"""Map removal (starpilot/tandem/map_removal.py, tile_removal.py) works inside StarPilot's map owner and tile writer, using
names they don't publish. A StarPilot merge that renames one would break Delete all downloaded maps with nothing else
failing, so this reads their source (they need the device's params and msgq builds to import) and checks each name.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

STARPILOT = Path(__file__).resolve().parents[4] / "starpilot"


def _tree(path: str) -> ast.Module:
  return ast.parse((STARPILOT / path).read_text())


def _module_names(tree: ast.Module) -> set[str]:
  names = set()
  for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
      names.add(node.name)
    elif isinstance(node, ast.Assign):
      names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
  return names


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
  return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


def _members(cls: ast.ClassDef) -> set[str]:
  """The class's methods, and every self.<name> it assigns anywhere."""
  names = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
  for node in ast.walk(cls):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
    names |= {t.attr for t in targets if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"}
  return names


def test_the_map_owner_still_has_what_snapshot_removal_uses() -> None:
  tree = _tree("maps/operation_owner.py")
  assert {"ACTIVE", "GENERATION", "OperationError", "_ensure_owned_offline_root", "request_operation"} <= _module_names(tree)
  owner = _members(_class(tree, "MapSnapshotOperationOwner"))
  assert {"_lock", "_closed", "_status", "root", "_parked", "_selected", "snapshot"} <= owner


def test_the_map_owner_still_routes_tandems_removal() -> None:
  source = (STARPILOT / "maps/operation_owner.py").read_text()
  assert "if op == 'tandem_remove':" in source and "remove_all_maps(self, request)" in source


@pytest.mark.parametrize("path,cls,names", [
  ("navigation/navtilesd.py", "TileDaemon", {"state", "store", "progress", "last_trim", "sweep_needed", "saved_full_at", "last_status",
                                             "plan", "maintain"}),
  ("navigation/google_tiles.py", "GoogleTiles", {"store", "want"}),
])
def test_the_tile_writers_still_have_what_tile_clearing_uses(path: str, cls: str, names: set[str]) -> None:
  assert names <= _members(_class(_tree(path), cls))


def test_the_tile_writer_still_asks_tandem_between_updates() -> None:
  source = (STARPILOT / "navigation/navtilesd.py").read_text()
  assert "consume_clear_tiles(daemon, google, env, params, owner.read_routing)" in source
  assert {"read_json", "write_json", "KINDS", "roads_root"} <= _module_names(_tree("navigation/offline_roads.py"))
