"""Offline Maps › Keep up to date on the device: the once-a-minute check that queues a scheduled map update
(starpilot/tandem/routing/schedule.py). ui.py's frame loop polls it through star_input.TandemInput, which runs with the
screen off too, as a parked comma usually is.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any


class MapScheduleWatch:
  """Offline Maps › Keep up to date: once a minute while parked on Wi-Fi, queues the scheduled map update when it's due
  (starpilot/tandem/routing/schedule.py), on a worker thread so drawing never waits on its files."""
  REFRESH_S = 60.0

  def __init__(self, poll: Callable[[bool, bool], Any] | None = None, clock: Callable[[], float] = time.monotonic):
    self._poll = poll or _schedule_poll
    self._clock = clock
    self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-map-schedule")
    self._pending: Future[Any] | None = None
    self._next = 0.0

  def poll(self, parked: bool, wifi: bool) -> None:
    """Starts a check when the last one is done and a minute has passed; only while parked on Wi-Fi.

    Args:
      parked: The car is parked.
      wifi: The device is on Wi-Fi.
    """
    if not (parked and wifi) or (self._pending is not None and not self._pending.done()) or self._clock() < self._next:
      return
    self._next = self._clock() + self.REFRESH_S
    self._pending = self._worker.submit(self._safely, parked, wifi)

  def _safely(self, parked: bool, wifi: bool) -> None:
    try:
      self._poll(parked, wifi)
    except Exception:
      pass   # a missing or unreadable map file waits for the next minute

  def close(self) -> None:
    self._worker.shutdown(wait=False, cancel_futures=True)


def _schedule_poll(parked: bool, wifi: bool) -> bool:
  from openpilot.starpilot.tandem.routing import schedule
  return schedule.poll(parked, wifi)


def on_wifi(sm: Any) -> bool:
  """Whether openpilot's deviceState says Wi-Fi. Its networkType is a capnp enum: compare its name, never int() it."""
  if not sm.valid.get("deviceState", False):
    return False
  return str(sm["deviceState"].networkType) == "wifi"
