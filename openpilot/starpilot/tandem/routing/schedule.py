"""Keep up to date: Tandem's schedule for the map job (road data and offline routes), as release's StarPilot 6 schedule did.

StarPilot 7 has no scheduled map refresh, so Tandem keeps its own: Off, Weekly or Monthly, saved beside the map jobs
(map-schedule.json, which removing maps keeps). When an update is due and the device is parked on Wi-Fi, it queues the
same job as Update maps for the chosen regions. Monthly follows Tandem's routing data, rebuilt on the 26th of each month
(.github/workflows/tandem_routing_maps.yaml), so it waits for that month's build. A failed update is tried again a day
later, not every minute.
"""
from __future__ import annotations

import datetime
import time

from openpilot.starpilot.tandem.routing import config as C
from openpilot.starpilot.tandem.routing.demand import download_pending, read_map

OFF, WEEKLY, MONTHLY = "off", "weekly", "monthly"
CHOICES = (OFF, WEEKLY, MONTHLY)
FILE = "map-schedule.json"
DAY = 24 * 60 * 60
WEEK = 7 * DAY
BUILD_DAY = 27   # the day after the monthly build (the 26th, UTC), so it's published before Monthly asks for it
RETRY = DAY


def every() -> str:
  """The saved choice: off, weekly or monthly (off when unset or unreadable)."""
  value = read_map(FILE).get("every")
  return value if value in CHOICES else OFF


def set_every(choice: str) -> None:
  """Saves the choice.

  Args:
    choice: off, weekly or monthly.
  """
  if choice not in CHOICES:
    raise ValueError(choice)
  C.atomic_json(C.root() / FILE, {**read_map(FILE), "every": choice})


def last_update() -> float | None:
  """When the last map job that finished was requested (wall seconds), manual or scheduled; None if none finished."""
  job = read_map()
  created = job.get("created")
  return float(created) if job.get("phase") == "ready" and isinstance(created, (int, float)) else None


def _last_build(now: float) -> float:
  """The latest monthly routing build that's published by now: BUILD_DAY of this month, or of last month."""
  today = datetime.datetime.fromtimestamp(now, datetime.UTC)
  month = today.replace(day=BUILD_DAY, hour=0, minute=0, second=0, microsecond=0)
  if month > today:
    month = (month.replace(day=1) - datetime.timedelta(days=1)).replace(day=BUILD_DAY)
  return month.timestamp()


def due(now: float, selection: str) -> bool:
  """Whether the schedule should queue an update now.

  Args:
    now: Wall seconds.
    selection: The chosen regions (maps.selection()); nothing is due without any.
  """
  choice = every()
  if choice == OFF or not selection or not C.enabled() or download_pending():
    return False
  attempted = read_map(FILE).get("attempted")
  if isinstance(attempted, (int, float)) and now - attempted < RETRY:
    return False
  last = last_update()
  if last is None:
    return True
  return now - last >= WEEK if choice == WEEKLY else last < _last_build(now)


def poll(parked: bool, wifi: bool, now: float | None = None) -> bool:
  """Queues the scheduled update when it's due and the device is parked on Wi-Fi; True when it queued one.

  Args:
    parked: The car is parked (StarPilot's offroad state).
    wifi: The device is on Wi-Fi.
    now: Wall seconds; the clock by default.
  """
  if not (parked and wifi):
    return False
  from openpilot.starpilot.tandem.routing import maps
  now = time.time() if now is None else now  # noqa: TID251
  selection = maps.selection()
  if not due(now, selection):
    return False
  C.atomic_json(C.root() / FILE, {**read_map(FILE), "attempted": now})
  try:
    maps.request(selection)
  except C.RoutingError:
    return False
  return True
