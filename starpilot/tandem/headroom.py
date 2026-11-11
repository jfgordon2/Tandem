"""Tandem's Help steer chime; the shared sound daemon keeps its normal alert selection."""
from __future__ import annotations

import math
import os
import time
from typing import Any, TYPE_CHECKING

from openpilot.starpilot.tandem.state import HEADROOM

if TYPE_CHECKING:
  from cereal.messaging import SubMaster

# Local-only sound keys are negative, separate from upstream enums and its positive custom offsets.
STEERING_HEADROOM_ALERT = -1001


def initialize(sound: Any) -> None:
  sound.headroom_state = HEADROOM
  sound.headroom_warning_seen = time.monotonic()
  sound.headroom_warning_since = 0.0


def update_sound(self: Any, sm: SubMaster) -> None:
  """Plays the Help steer chime once for each new warning the UI writes, unless another alert is sounding."""
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return
  from openpilot.selfdrive.ui.soundd import AudibleAlert, custom, log
  if self.current_alert == STEERING_HEADROOM_ALERT:
    self.current_alert_type = "steerSaturated/warning"
    loaded = self.loaded_sounds.get(STEERING_HEADROOM_ALERT)
    if loaded is None or self.current_sound_frame >= len(loaded):
      self.current_alert = AudibleAlert.none
      self.current_sound_frame = 0
  try:
    warning = float(self.headroom_state.read(max_age=30.0) or 0.0)
  except (TypeError, ValueError):
    return
  self.headroom_warning_since = warning if math.isfinite(warning) else 0.0
  if not math.isfinite(warning) or warning <= self.headroom_warning_seen:
    return
  self.headroom_warning_seen = warning
  # Consume busy/expired requests rather than playing a warning after its curve.
  if (0 <= time.monotonic() - warning <= 1.0 and self.current_alert == AudibleAlert.none
      and not self.selfdrive_timeout_alert and sm.valid["selfdriveState"] and sm.alive["selfdriveState"]
      and sm["selfdriveState"].alertSize == log.SelfdriveState.AlertSize.none
      and sm["starpilotSelfdriveState"].alertSize == custom.StarPilotSelfdriveState.AlertSize.none):
    self.current_alert_type = "steerSaturated/warning"
    self.update_alert(STEERING_HEADROOM_ALERT)

def warning_active(self: Any) -> bool:
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return False
  # The UI clears the snapshot when its warning ends; the age cap prevents stale warning suppression.
  return bool(self.headroom_warning_since > 0 and 0 <= time.monotonic() - self.headroom_warning_since <= 30.0)



def sound_type(base: type[Any]) -> type[Any]:
  """StarPilot's sound daemon with the Help steer chime, which also quiets its turn steering-limit alerts while Help steer shows."""
  if os.getenv("TANDEM_ONROAD", "1") == "0":
    return base
  from openpilot.selfdrive.ui import soundd

  class TandemSoundd(base):
    _sound_list = base._sound_list | {STEERING_HEADROOM_ALERT: ("prompt.wav", 1, soundd.MAX_VOLUME)}
    update_headroom_sound = update_sound
    headroom_warning_active = warning_active

    def __init__(self, *args: Any, **kwargs: Any) -> None:
      initialize(self)
      super().__init__(*args, **kwargs)

    def _filter_alert(self, alert: Any, alert_type: str) -> Any:
      if warning_active(self) and soundd.is_turn_steering_limit_alert(alert_type):
        return soundd.AudibleAlert.none
      return super()._filter_alert(alert, alert_type)

    def _update_extra_sounds(self, sm: SubMaster) -> None:
      super()._update_extra_sounds(sm)
      update_sound(self, sm)

    def update_volume_map(self) -> None:
      super().update_volume_map()
      self.volume_map[STEERING_HEADROOM_ALERT] = self.volume_settings["PromptVolume"] / 100.0

  return TandemSoundd
