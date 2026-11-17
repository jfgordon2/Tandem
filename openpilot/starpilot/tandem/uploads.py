"""The release Off, Parked and Always policy for the automatic uploader."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Protocol

PREFERENCE = "uploads"
MODES = ("off", "parked", "always")


class ParamsPath(Protocol):
  """The native Params path without importing any UI code into the manager."""

  def get_param_path(self) -> str: ...


def upload_mode(params: ParamsPath) -> str | None:
  """Read the small settings marker. A missing setting follows native behavior."""
  try:
    override = os.environ.get("TANDEM_PREFS_DIR")
    folder = Path(override) if override else Path(params.get_param_path()).parent
    fd = os.open(folder / f".tandem_{PREFERENCE}", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
      if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        return None
      raw = stream.read(17)
    value = raw.decode("ascii").strip() if len(raw) <= 16 else ""
  except FileNotFoundError:
    return "always"
  except (OSError, RuntimeError, ValueError):
    return None
  return value if value in MODES else None


def allow_uploads(started: bool, params: ParamsPath, _vehicle: object) -> bool:
  """Run the automatic uploader per the release setting, retaining native network rules."""
  if os.environ.get("TANDEM_SETTINGS") == "0" or os.environ.get("STARPILOT_UI") == "upstream":
    return True
  mode = upload_mode(params)
  return mode == "always" or (mode == "parked" and not started)
