"""Keep the compass's last reliable moving heading through stops and restarts."""
from __future__ import annotations

import math
from typing import Protocol, TYPE_CHECKING

from openpilot.common.gps import get_gps_location_service
from openpilot.selfdrive.ui.tandem.prefs import Text

if TYPE_CHECKING:
  from cereal.messaging import SubMaster
  from openpilot.selfdrive.ui.ui_state import UIState


DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SAVED_HEADING = Text("compass_heading")
MIN_SPEED = 1.0  # m/s, from both the car and GPS
MAX_BEARING_ERROR = 22.5  # half a compass sector
MAX_FIX_AGE = 2.5
SAVE_INTERVAL = 30.0


class _Fix(Protocol):
  hasFix: bool
  bearingDeg: float
  bearingAccuracyDeg: float
  speed: float


class DriveCompass:
  """Track a fresh GPS course while moving and persist the displayed direction."""

  def __init__(self) -> None:
    try:
      saved = (SAVED_HEADING.get() or "").strip()
    except UnicodeError:
      saved = ""
    self.direction = saved if saved in DIRECTIONS else ""
    self._saved = self.direction
    self._last_save = -math.inf
    self._last_fix = -math.inf
    self._gps: SubMaster | None = None
    self._service = ""

  def observe(self, fix: _Fix, timestamp: float, started: float, now: float, speed: float, reverse: bool) -> None:
    """Accept a fresh fix from this drive once, while the car and GPS both report motion."""
    if timestamp <= self._last_fix or timestamp < started or not 0 <= now - timestamp <= MAX_FIX_AGE:
      return
    self._last_fix = timestamp
    if not fix.hasFix or not all(math.isfinite(value) for value in (speed, fix.speed, fix.bearingDeg, fix.bearingAccuracyDeg)):
      return
    if abs(speed) < MIN_SPEED or fix.speed < MIN_SPEED or not 0 <= fix.bearingAccuracyDeg <= MAX_BEARING_ERROR:
      return
    if not -360 <= fix.bearingDeg <= 360:
      return
    bearing = fix.bearingDeg + (180 if reverse else 0)  # GPS reports course of travel
    self.direction = DIRECTIONS[int((bearing + 22.5) // 45) % len(DIRECTIONS)]
    if now - self._last_save >= SAVE_INTERVAL:
      self._save(now)

  def update(self, state: UIState, now: float, reverse: bool) -> None:
    """Read the GPS source StarPilot selected and the current drive's car speed."""
    if not state.started or not state.ui_params.get_bool("Compass"):
      return
    sm = state.sm
    if not (sm.valid["carState"] and sm.alive["carState"] and sm.recv_frame["carState"] >= state.started_frame):
      return
    if self._gps is None:
      self._service = get_gps_location_service(state.params)
      if self._service == "gpsLocationExternal":
        self._gps = sm
      else:
        from cereal.messaging import SubMaster
        self._gps = SubMaster([self._service])
    if self._gps is not sm:
      self._gps.update(0)
    if self._gps.valid[self._service]:
      timestamp = self._gps.logMonoTime[self._service] * 1e-9
      self.observe(self._gps[self._service], timestamp, state.started_time, now, float(sm["carState"].vEgo), reverse)

  def offroad(self, now: float) -> None:
    """Save any newer heading and release the private GPS subscription."""
    self._save(now)
    self._gps = None

  def _save(self, now: float) -> None:
    if self.direction and self.direction != self._saved:
      self._last_save = now
      if SAVED_HEADING.set(self.direction):
        self._saved = self.direction
