"""The compass: the heading beside the street name, kept through stops and restarts.

StarPilot 7 dropped its compass, so the switch is Tandem's own (prefs.COMPASS, Display › Driving Screen). The heading
comes from a fresh GPS course while the car and GPS both report motion, from the GPS source StarPilot selects
(common.gps); openpilot's UI subscriber already carries both. The last heading is kept in a cache file, so a car started
while parked shows where it was last pointed.
"""
from __future__ import annotations

import math
from typing import Any, Protocol

from openpilot.selfdrive.ui.tandem.prefs import COMPASS, Text

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
    self._service = ""

  def heading(self) -> str:
    """The heading to show: the direction while the compass is on, else ""."""
    return self.direction if COMPASS.get() else ""

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

  def update(self, state: Any, now: float, reverse: bool) -> None:
    """Read the GPS source StarPilot selected and the current drive's car speed.

    Args:
      state: openpilot's UIState.
      now: Monotonic seconds.
      reverse: The car is in reverse, so it faces against its course.
    """
    if not state.started or not COMPASS.get():
      return
    sm = state.sm
    if not (sm.valid["carState"] and sm.alive["carState"] and sm.recv_frame["carState"] >= state.started_frame):
      return
    if not self._service:
      from openpilot.common.gps import get_gps_location_service
      self._service = get_gps_location_service(state.params)
    if sm.valid[self._service]:
      timestamp = sm.logMonoTime[self._service] * 1e-9
      self.observe(sm[self._service], timestamp, state.started_time, now, float(sm["carState"].vEgo), reverse)

  def offroad(self, now: float) -> None:
    """Save any newer heading; the GPS source is read again on the next drive."""
    self._save(now)
    self._service = ""

  def _save(self, now: float) -> None:
    if self.direction and self.direction != self._saved:
      self._last_save = now
      if SAVED_HEADING.set(self.direction):
        self._saved = self.direction
