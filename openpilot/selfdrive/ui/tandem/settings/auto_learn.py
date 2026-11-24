"""Tuner › Steering's Auto Learn line (design/tuner-autolearn.html): what StarPilot's steering learner is doing, and when it
last changed the tune, in plain words.

StarPilot decides what's true: its learner (FLM) writes a report while it runs, and keeps the changes it saved; Galaxy's
Tuner reads both through starpilot/galaxy/flm_training_results.py, and so does this. The read parses the car's saved
parameters, so it runs on a worker thread every few seconds, only while the line is on screen.
"""
from __future__ import annotations

import datetime
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from openpilot.selfdrive.ui.tandem.i18n import N_, t_, translate
from openpilot.selfdrive.ui.tandem.dates import short_date

REFRESH_S = 5.0
KEY = "ForceAutoTuneOff"   # StarPilot's Auto Learn row (starpilot/lateral/controller_selection.LEARNING_OFF_KEY)
WAITING = ("waiting_for_vehicle_offroad", "waiting_for_controls_to_disengage", "waiting_for_vehicle_to_switch_off",
           "waiting_for_ignition_off", "waiting_for_panda_controls_to_disarm")
NEEDS_MORE = ("more_independent_eligible_tracking_required", "recorded_tracking_suggestion_not_yet_qualified_for_automatic_application")


def activity(snapshot: dict) -> str:
  """What the learner is doing now, from its report.

  Args:
    snapshot: StarPilot's learner snapshot (FlmTrainingResults.snapshot()): current, preference and savedHistory.
  """
  preference = snapshot.get("preference") or {}
  if preference.get("valid") and preference.get("enabled") is False:
    return N_("Off: your steering tune stays as it is")
  current = snapshot.get("current")
  if not current or not current.get("fresh"):
    return N_("Not running right now")
  reason, status = str(current.get("reason", "")), str(current.get("status", ""))
  if reason in WAITING or reason.startswith("waiting_for_"):
    return N_("Waiting for the car to turn off")
  if reason in NEEDS_MORE:
    return N_("Needs more driving before it suggests a change")
  if status == "collecting" or reason == "recording_for_offroad_analysis":
    return N_("Learning from this drive")
  progress = (current.get("details") or {}).get("Parked analysis progress")
  if isinstance(progress, list) and len(progress) == 3 and all(isinstance(n, int) for n in progress[1:]) and progress[2] > 0:
    return t_("Checking your last drive ({} of {})", progress[1], progress[2])
  if status == "fitting":
    return N_("Checking your last drive")
  return N_("Not running right now")


def last_change(snapshot: dict) -> str:
  """When the learner last saved a change, as RAM dates drives ("Nov 23"), or that it hasn't.

  Args:
    snapshot: StarPilot's learner snapshot.
  """
  profiles = (snapshot.get("savedHistory") or {}).get("profiles") or []
  times = [p["completedAt"] for p in profiles if isinstance(p, dict) and isinstance(p.get("completedAt"), int)]
  if not times:
    return N_("No changes yet")
  return t_("Last change {}", short_date(datetime.datetime.fromtimestamp(max(times) / 1000)))


def describe(snapshot: dict) -> str:
  """The whole line: what it's doing, then its last change ("Checking your last drive (14 of 14) · Last change Nov 23").

  Args:
    snapshot: StarPilot's learner snapshot.
  """
  return f"{translate(activity(snapshot))} · {translate(last_change(snapshot))}"


def _read() -> dict:
  from openpilot.common.params import Params
  from openpilot.starpilot.galaxy.flm_training_results import FlmTrainingResults
  return FlmTrainingResults(params=Params()).snapshot()


class AutoLearnWatch:
  """Reads StarPilot's learner snapshot on a worker thread, at most every REFRESH_S, while its line is drawn.

  Args:
    read: Returns StarPilot's learner snapshot; FlmTrainingResults on the device.
    clock: Monotonic seconds.
  """

  def __init__(self, read: Callable[[], dict] = _read, clock: Callable[[], float] = time.monotonic):
    self._read, self._clock = read, clock
    self._worker: ThreadPoolExecutor | None = None
    self._pending: Future[dict] | None = None
    self._next = 0.0
    self._line = N_("Checking…")

  def text(self) -> str:
    """The line to draw now; starts a new read when the last is done and old enough."""
    if self._pending is not None and self._pending.done():
      try:
        self._line = describe(self._pending.result())
      except Exception:
        self._line = N_("Not running right now")
      self._pending = None
    if self._pending is None and self._clock() >= self._next:
      if self._worker is None:
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tandem-auto-learn")
      self._next = self._clock() + REFRESH_S
      self._pending = self._worker.submit(self._read)
    return self._line

  def close(self) -> None:
    if self._worker is not None:
      self._worker.shutdown(wait=False, cancel_futures=True)


_shared: list[AutoLearnWatch] = []


def shared() -> AutoLearnWatch:
  """The one watch Tuner's Auto Learn row uses, made the first time Tuner opens; its thread idles while it isn't drawn."""
  if not _shared:
    _shared.append(AutoLearnWatch())
  return _shared[0]
