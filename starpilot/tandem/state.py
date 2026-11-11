"""Small atomic snapshots for Tandem processes, outside upstream's compiled param registry."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any


def state_dir() -> Path:
  configured = os.getenv("TANDEM_STATE_DIR")
  if configured:
    return Path(configured)
  from openpilot.system.hardware.hw import Paths
  prefix = os.getenv("OPENPILOT_PREFIX", "")
  return Path(Paths.shm_path()) / ("tandem-" + prefix.encode().hex() if prefix else "tandem")


class Snapshot:
  """A small JSON value shared between Tandem's processes through an atomically written file, stamped with the monotonic time."""

  def __init__(self, name: str):
    self.name = name

  def write(self, value: Any, now: float | None = None) -> bool:
    """Saves value, stamped with now. False if it couldn't be written."""
    folder = state_dir()
    temporary = None
    try:
      folder.mkdir(parents=True, exist_ok=True)
      with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as stream:
        temporary = Path(stream.name)
        # The streaming encoder in json.dump() can leave cycles when GC is disabled.
        stream.write(json.dumps({"time": time.monotonic() if now is None else now, "value": value}, allow_nan=False))
      temporary.replace(folder / self.name)
      return True
    except (OSError, TypeError, ValueError):
      return False
    finally:
      if temporary is not None:
        try:
          temporary.unlink(missing_ok=True)
        except OSError:
          pass

  def read(self, max_age: float, now: float | None = None) -> Any:
    """The saved value, or None when it's missing, unreadable or older than max_age seconds."""
    try:
      record = json.loads((state_dir() / self.name).read_text())
      stamp = float(record["time"])
      age = (time.monotonic() if now is None else now) - stamp
      if math.isfinite(stamp) and 0 <= age <= max_age:
        return record["value"]
    except (OSError, ValueError, TypeError, KeyError):
      pass
    return None


HEADROOM = Snapshot("headroom.json")
