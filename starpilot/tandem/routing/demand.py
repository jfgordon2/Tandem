"""Cheap manager-side demand checks; never import the broker or map installer here."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from openpilot.starpilot.tandem.routing import config as C
from openpilot.starpilot.tandem.state import Snapshot

if TYPE_CHECKING:
  from openpilot.common.params import Params

IDLE_SECONDS = 120
WAKE = Snapshot("routing-wake.json")  # shared memory, so a reboot cannot revive a stale preview
ACTIVE_MAP_PHASES = {"road", "prepare", "download", "install"}


def read_map(name: str = "map-job.json") -> dict:
  try:
    value = json.loads((C.root() / name).read_text())
    return value if isinstance(value, dict) else {}
  except (OSError, ValueError):
    return {}


def download_pending() -> bool:
  job, pending = read_map(), read_map("map-request.json")
  return bool(pending.get("id") and (job.get("id") != pending["id"] or job.get("phase") in ACTIVE_MAP_PHASES))


def needed(params: Params) -> bool:
  return bool(params.get("NavDestination")) or download_pending()


def wake() -> bool:
  return C.enabled() and WAKE.write(True)


def awake() -> bool:
  return WAKE.read(IDLE_SECONDS) is True
