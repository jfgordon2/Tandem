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


class Choice:
  """A preference with a few values, kept as a small file holding the chosen one; None until the driver picks."""

  def __init__(self, name: str, values: tuple[str, ...]):
    self.name, self.values = name, values

  def _file(self) -> Path:
    return prefs_dir() / f".tandem_{self.name}"

  def get(self) -> str | None:
    try:
      value = self._file().read_text().strip()
    except OSError:
      return None
    return value if value in self.values else None

  def set(self, value: str) -> None:
    if value in self.values:
      try:
        self._file().write_text(value)
      except OSError:
        pass


BACKUP_DIR = ".tandem_prefs"          # inside a settings backup, beside the copied params
NOT_BACKED_UP = {".tandem_forecast.json"}   # a cache, not a setting


def pref_files(folder: Path | None = None) -> list[Path]:
  """Tandem's settings files (marker files and choices) beside the params folder."""
  folder = folder or prefs_dir()
  try:
    return sorted(p for p in folder.glob(".tandem_*") if p.is_file() and p.name not in NOT_BACKED_UP)
  except OSError:
    return []


def save_prefs(backup: Path, folder: Path | None = None) -> None:
  """Copy Tandem's settings into a backup, so it holds them along with the params."""
  import shutil
  target = backup / BACKUP_DIR
  target.mkdir(parents=True, exist_ok=True)
  for path in pref_files(folder):
    shutil.copy2(path, target / path.name)


def restore_prefs(backup: Path, folder: Path | None = None) -> bool:
  """Make Tandem's settings what the backup saved: a file there is restored, one it lacks goes back to its default.
  A backup made before Tandem saved its settings leaves the current ones alone (returns False)."""
  import shutil
  source = backup / BACKUP_DIR
  if not source.is_dir():
    return False
  folder = folder or prefs_dir()
  for path in pref_files(folder):
    path.unlink(missing_ok=True)
  for path in source.glob(".tandem_*"):
    if path.is_file() and path.name not in NOT_BACKED_UP:
      shutil.copy2(path, folder / path.name)
  return True


MAX_FOLLOWS_LIMIT = Flag("max_follows_limit", True)   # Speed Limits › MAX follows limits (onroad/limits.py LimitFollower)
WEATHER_HEADS_UP = Flag("weather_heads_up", True)     # Weather › Weather heads-up (forecast.py)
LEAD_TAG = Flag("lead_tag", True)                     # Display › Driving Screen › Lead Car Tag (onroad/view.py)
WEATHER_CHIME = Flag("weather_chime", True)           # Alerts › Chimes › Weather heads-up: its one chime
TEMPERATURE = Choice("temperature", ("F", "C"))       # General › Temperature; until picked, it follows Units (km/h: °C)


def celsius(metric: bool) -> bool:
  """Temperatures in °C: the driver's choice, or Units until they've made one."""
  chosen = TEMPERATURE.get()
  return metric if chosen is None else chosen == "C"
