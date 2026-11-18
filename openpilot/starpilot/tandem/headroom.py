"""Tandem's Help steer chime, through StarPilot 7's sound daemon (selfdrive/ui/soundd.py).

The driving screen writes the HEADROOM snapshot (state.py) when its Help steer warning starts and clears it when it ends.
TandemSoundd plays StarPilot's prompt chime once for each new warning, at the driver's prompt volume, unless another
alert is sounding or showing; its own alert choice is otherwise StarPilot's. With TANDEM_ONROAD=0 the daemon is
StarPilot's own.
"""
from __future__ import annotations

import math
import os
import time
from typing import Any

from openpilot.starpilot.tandem.state import HEADROOM

FRESH_S = 1.0   # a warning older than this when read is skipped rather than chimed late


def new_warning(stamp: Any, seen: float, now: float) -> bool:
  """Whether stamp (the snapshot's value) is a warning that started after seen and within FRESH_S of now."""
  try:
    value = float(stamp)
  except (TypeError, ValueError):
    return False
  return math.isfinite(value) and value > seen and 0 <= now - value <= FRESH_S


def sound_type(base: type[Any]) -> type[Any]:
  """StarPilot's sound daemon with the Help steer chime; StarPilot's own with TANDEM_ONROAD=0."""
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return base
  from openpilot.cereal import log
  AudibleAlert = log.SelfdriveState.AudibleAlert   # soundd's own name for it

  class TandemSoundd(base):  # type: ignore[misc, valid-type]
    def __init__(self, *args: Any, **kwargs: Any) -> None:
      super().__init__(*args, **kwargs)
      self.headroom_seen = time.monotonic()   # a warning from before this start is never chimed

    def get_audible_alert(self, sm: Any) -> None:
      super().get_audible_alert(sm)
      now = time.monotonic()
      stamp = HEADROOM.read(max_age=30.0, now=now)
      if not new_warning(stamp, self.headroom_seen, now):
        return
      self.headroom_seen = float(stamp)   # consumed, played or not, so a busy moment never chimes late
      quiet = (self.current_alert == AudibleAlert.none and not self.selfdrive_timeout_alert and sm.valid["selfdriveState"]
               and str(sm["selfdriveState"].alertSize) == "none")
      if quiet:
        self.update_alert(AudibleAlert.prompt)

  return TandemSoundd
