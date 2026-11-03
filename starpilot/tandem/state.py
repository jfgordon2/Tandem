"""Small atomic snapshots for Tandem processes, outside upstream's compiled param registry."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time


def state_dir() -> Path:
  configured = os.getenv("TANDEM_STATE_DIR")
  if configured:
    return Path(configured)
  from openpilot.system.hardware.hw import Paths
  prefix = os.getenv("OPENPILOT_PREFIX", "")
  return Path(Paths.shm_path()) / ("tandem-" + prefix.encode().hex() if prefix else "tandem")


class Snapshot:
  def __init__(self, name: str):
    self.name = name

  def write(self, value, now: float | None = None) -> bool:
    folder = state_dir()
    temporary = None
    try:
      folder.mkdir(parents=True, exist_ok=True)
      with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump({"time": time.monotonic() if now is None else now, "value": value}, stream, allow_nan=False)
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

  def read(self, max_age: float, now: float | None = None):
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
NAV_TURN = Snapshot("nav-turn.json")
