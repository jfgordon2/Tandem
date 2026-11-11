#!/usr/bin/env python3
"""Type-check Tandem's own code with mypy, using the repository's mypy settings.

Checks every module under ``selfdrive/ui/tandem`` and ``starpilot/tandem`` except tests and tools, as on the device
(``--platform=linux``, whatever the host). Imports from StarPilot and openpilot are followed silently, so only errors in
Tandem's own files are reported. Every function must be fully annotated (``--disallow-untyped-defs``), since mypy skips
the bodies of unannotated ones.

Usage:
  python3 selfdrive/ui/tandem/tools/typecheck.py [mypy options]

Returns mypy's exit status: 0 when the owned code is clean.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OWNED = ("selfdrive/ui/tandem", "starpilot/tandem")
SKIP = {"tests", "tools", "__pycache__"}


def owned_files() -> list[str]:
  """Returns the owned modules to check, in a stable order.

  Paths go through the repository's ``openpilot`` link (``openpilot/starpilot/tandem/...``), so each module is checked
  under the same name the code imports it by. Checked as ``starpilot.tandem...``, a class imported as
  ``openpilot.starpilot.tandem...`` would count as a second, different type.
  """
  return sorted(str(Path("openpilot") / path.relative_to(ROOT)) for root in OWNED for path in (ROOT / root).rglob("*.py")
                if not SKIP & set(path.relative_to(ROOT).parts))


def main(argv: list[str]) -> int:
  """Runs mypy over the owned modules.

  Args:
    argv: Extra mypy options, passed through.

  Returns:
    mypy's exit status.
  """
  command = [sys.executable, "-m", "mypy", "--follow-imports=silent", "--platform=linux", "--disallow-untyped-defs",
             "--disallow-incomplete-defs", *argv, *owned_files()]
  return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
