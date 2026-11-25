"""Every raylib function Tandem's screens call exists in StarPilot 7's raylib_nb binding on the device.

The Mac's raylib binding has functions raylib_nb leaves out, so a call to one passes every test here and crashes the comma
(voice typing's check_collision_point_circle did). fixtures/raylib_nb_names.txt lists raylib_nb's public names, read on
a comma; read it again after upstream changes the binding:
  python -c "from openpilot.starpilot.ui.raylib import rl; print('\\n'.join(sorted(n for n in dir(rl) if not n.startswith('_'))))"
"""
from __future__ import annotations

import re
from pathlib import Path

TANDEM = Path(__file__).resolve().parents[1]
OWN = TANDEM.parents[2] / "starpilot" / "tandem"
DEVICE = set((Path(__file__).parent / "fixtures" / "raylib_nb_names.txt").read_text().split())
CALL = re.compile(r"\brl\.([A-Za-z]\w*)")


def test_screens_call_only_what_the_device_binding_has() -> None:
  missing = {}
  for root in (TANDEM, OWN):
    for path in root.rglob("*.py"):
      parts = set(path.relative_to(root).parts)
      if parts & {"tests", "tools"}:   # tests use fakes; tools (font builds, renders) run on a Mac
        continue
      for name in set(CALL.findall(path.read_text(encoding="utf-8"))) - DEVICE:
        missing.setdefault(name, []).append(str(path.relative_to(root)))
  assert not missing, missing
