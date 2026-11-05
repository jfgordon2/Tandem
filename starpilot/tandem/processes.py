"""The names processes go by on a comma device, for RAM reports in the UI and on the command line.

No UI or driving imports, so tools can use it on the device.
"""
from __future__ import annotations

import os

GENERIC = {"daemon", "main", "service", "server"}   # module names that need their package to mean anything


def _module_name(module: str) -> str:
  """selfdrive.selfdrived.selfdrived → selfdrived; starpilot.system.bluetooth.daemon → bluetooth.daemon."""
  parts = module.split(".")
  return ".".join(parts[-2:]) if parts[-1] in GENERIC and len(parts) > 1 else parts[-1]


def process_name(name: str, cmdline: list[str]) -> str:
  """The name a process goes by. Manager titles most Python processes with their module (selfdrive.selfdrived.selfdrived);
  others run as python -m <module> (the UI) or python <script> (manager.py, comma's /usr/comma services)."""
  title = cmdline[0] if cmdline else name
  title = os.path.basename(title.split(" ", 1)[0]) or name
  if title.startswith("python"):
    args = iter(cmdline[1:])
    for arg in args:
      if arg == "-m":
        return _module_name(next(args, title))
      if arg.startswith("-"):
        continue
      return os.path.basename(arg).removesuffix(".py") or title
    return title
  return _module_name(title) if "." in title and not title.endswith(".py") else title
