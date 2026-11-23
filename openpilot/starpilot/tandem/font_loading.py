"""Defer native settings faces while keeping the driving and alert faces ready, and log when one loads after all."""
from collections.abc import Mapping
import os
import traceback
from typing import Any


def defer_inter(big_ui: bool, environment: Mapping[str, str] = os.environ) -> bool:
  """Use on-demand Inter weights only for the Tandem big layout."""
  switches = ("TANDEM_HOME", "TANDEM_SETTINGS", "TANDEM_ONROAD", "TANDEM_SIDEBAR")
  return big_ui and environment.get("STARPILOT_UI") != "upstream" and any(environment.get(name, "1") != "0" for name in switches)


def log_deferred_loads(app: Any) -> None:
  """Log each deferred face the first time something asks for it, with the code that asked: the one way to see on the
  device which screens cost the font memory deferring is meant to save (about 21.5 MiB of GPU memory a face).

  Args:
    app: openpilot's gui_app, before its window opens.
  """
  load = app._load_face

  def logged(weight: Any, codepoints: list[int]) -> None:
    if weight in getattr(app, "_deferred_faces", {}):
      from openpilot.common.swaglog import cloudlog
      caller = [f"{f.filename.rsplit('openpilot/', 1)[-1]}:{f.lineno}" for f in traceback.extract_stack()[-5:-1]]
      cloudlog.warning(f"Tandem: deferred font {weight} loaded by {' < '.join(reversed(caller))}")
    load(weight, codepoints)

  app._load_face = logged

