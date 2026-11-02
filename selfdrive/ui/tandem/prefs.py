"""Tandem's own on/off preferences, kept as marker files beside the params folder.

Upstream's param registry is compiled into the committed common/params_pyx.so and libcommon.a (the device runs
prebuilt), so a new key in params_keys.h is unknown on the device until those are rebuilt, and writing it crashes the UI.
A marker file needs no key: it exists only when the preference differs from its default.
"""
from __future__ import annotations

import os
from pathlib import Path


def prefs_dir() -> Path:
  if os.environ.get("TANDEM_PREFS_DIR"):
    return Path(os.environ["TANDEM_PREFS_DIR"])
  from openpilot.common.params import Params
  return Path(Params().get_param_path()).parent


class Flag:
  def __init__(self, name: str, default: bool):
    self.name, self.default = name, default

  def _marker(self) -> Path:
    return prefs_dir() / f".tandem_{self.name}_{'off' if self.default else 'on'}"

  def get(self) -> bool:
    try:
      return self.default != self._marker().exists()
    except OSError:
      return self.default

  def set(self, on: bool) -> None:
    marker = self._marker()
    try:
      if on == self.default:
        marker.unlink(missing_ok=True)
      else:
        marker.touch()
    except OSError:
      pass


MAX_FOLLOWS_LIMIT = Flag("max_follows_limit", True)   # Speed Limits › MAX follows limits (onroad/limits.py LimitFollower)
WEATHER_HEADS_UP = Flag("weather_heads_up", True)     # Weather › Weather heads-up (forecast.py)
WEATHER_CHIME = Flag("weather_chime", True)           # Alerts › Chimes › Weather heads-up: its one chime
