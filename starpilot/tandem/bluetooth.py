"""Tandem Bluetooth settings can be used with the ignition on, in a verified stationary Park.

The car's global offroad state and controller reconnect policy stay upstream's. Both UI and service
use the same fresh-message check; the service makes the authoritative decision for every request.
"""
from __future__ import annotations

import math
import os
import threading
import time
from typing import Any, TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
  from cereal.messaging import SubMaster

FRESH_S = 1.0


def stationary_park(sm: SubMaster, now: float | None = None) -> bool:
  """Whether the car is verifiably parked and stationary, from fresh carState and carControl.

  Messages must be recent by publication time too, since a just-read socket can hold an old, buffered one.

  Args:
    sm: A SubMaster with carState and carControl.
    now: The monotonic time; now by default.
  """
  now = time.monotonic() if now is None else now
  try:
    for service in ("carState", "carControl"):
      # Check publication time too: a just-read socket can contain an old, buffered message.
      if not (sm.valid.get(service, False) and sm.alive.get(service, False)
              and 0 <= now - sm.recv_time[service] <= FRESH_S
              and 0 <= now - sm.logMonoTime[service] / 1e9 <= FRESH_S):
        return False
    car, control = sm["carState"], sm["carControl"]
    speed = float(car.vEgo)
    return bool(str(car.gearShifter) == "park" and car.standstill and math.isfinite(speed) and abs(speed) < 0.1
                and not (control.enabled or control.latActive or control.longActive))
  except (AttributeError, KeyError, TypeError, ValueError):
    return False


class ParkMonitor:
  """One lazy subscriber in the Bluetooth service; no UI or driving processes are modified."""

  def __init__(self) -> None:
    self._sm: Any = None   # cereal SubMaster for carState and carControl, made on first use
    self._lock = threading.Lock()

  def allowed(self) -> bool:
    """Whether Bluetooth settings may change now: parked and stationary, by the shared fresh-message check."""
    with self._lock:
      try:
        if self._sm is None:
          import cereal.messaging as messaging
          self._sm = messaging.SubMaster(["carState", "carControl"])
          deadline = time.monotonic() + 0.25
          while time.monotonic() < deadline:
            self._sm.update(20)
            if all(self._sm.seen.values()):
              break
        else:
          self._sm.update(0)
        return stationary_park(self._sm)
      except Exception:
        return False


def controller_type(base: type[Any], monitor_factory: Callable[[], ParkMonitor] = ParkMonitor) -> type[Any]:
  """The upstream UI fallback retains its original ignition-off restriction."""
  if os.getenv("TANDEM_SETTINGS", "1") == "0":
    return base

  class ParkedBluetoothController(base):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
      super().__init__(*args, **kwargs)
      self._park_monitor = monitor_factory()

    def _settings_allowed(self, offroad: bool | None = None) -> bool:
      return bool(super()._settings_allowed(offroad) or self._park_monitor.allowed())

  return ParkedBluetoothController
