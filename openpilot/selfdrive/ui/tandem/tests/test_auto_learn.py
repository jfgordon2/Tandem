"""Tuner › Steering's Auto Learn line: StarPilot's learner report and saved history in plain words."""
from __future__ import annotations

import datetime
from dataclasses import replace

from openpilot.selfdrive.ui.tandem.settings.auto_learn import AutoLearnWatch, activity, describe, last_change
from openpilot.selfdrive.ui.tandem.settings.tuner import AUTO_LEARN, Tunable, Tuner
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner, page

NOV_23 = int(datetime.datetime(2026, 11, 23, 15, 0).timestamp() * 1000)


def report(status: str = "fitting", reason: str = "checking_recorded_steering_recommendations", fresh: bool = True,
           progress: list | None = None, enabled: bool = True, saved: list | None = None) -> dict:
  """The snapshot's shape as FlmTrainingResults read it on the comma, 2026-11-24."""
  return {
    "current": {"fresh": fresh, "ageSeconds": 1.5, "enabled": None, "status": status, "reason": reason,
                "progress": {"samples": 16969, "blocks": 294, "requiredBlocks": 6}, "fit": None,
                "application": {"applied": False, "reason": "saved_configuration_is_not_current_application"},
                "details": {"Parked analysis progress": progress if progress is not None else ["checking", 14, 14]}},
    "preference": {"version": 1, "valid": True, "enabled": enabled, "parked": True, "vehicle": "X", "controller": "torque"},
    "savedHistory": {"status": "readable", "historicalOnly": True,
                     "profiles": saved if saved is not None else [{"completedAt": NOV_23, "state": "ready_for_next_drive",
                                                                     "values": [["friction_threshold_low", 0.0012]]}]},
  }


def test_the_line_says_what_the_learner_is_doing_and_when_it_last_changed() -> None:
  assert describe(report()) == "Checking your last drive (14 of 14) · Last change Nov 23"


def test_each_state_in_plain_words() -> None:
  assert activity(report(status="collecting", reason="recording_for_offroad_analysis")) == "Learning from this drive"
  assert activity(report(reason="waiting_for_ignition_off")) == "Waiting for the car to turn off"
  assert activity(report(reason="more_independent_eligible_tracking_required")) == "Needs more driving before it suggests a change"
  assert activity(report(progress=[])) == "Checking your last drive"
  assert activity(report(fresh=False)) == "Not running right now"
  assert activity({"current": None}) == "Not running right now"
  assert activity(report(enabled=False)) == "Off: your steering tune stays as it is"
  assert last_change(report(saved=[])) == "No changes yet"


def test_the_watch_reads_off_the_drawing_thread_and_keeps_its_last_line() -> None:
  now = [0.0]
  reads: list[int] = []

  def read() -> dict:
    reads.append(1)
    return report()
  watch = AutoLearnWatch(read, clock=lambda: now[0])
  assert watch.text() == "Checking…"
  watch._pending.result(timeout=5)
  assert watch.text() == "Checking your last drive (14 of 14) · Last change Nov 23"
  assert len(reads) == 1   # not again within REFRESH_S

  def broken() -> dict:
    raise OSError("unreadable")
  failing = AutoLearnWatch(broken)
  failing.text()
  assert isinstance(failing._pending.exception(timeout=5), OSError)
  assert failing.text() == "Not running right now"
  watch.close()
  failing.close()


def test_auto_learn_is_a_switch_resets_leave_alone() -> None:
  owner = Owner({"torque": {AUTO_LEARN: "Off"}, **{name: {} for name in ("lane", "profiles", "relaxed", "standard", "aggressive", "traffic")}})
  rows = owner.pages["torque"]
  rows[AUTO_LEARN] = replace(rows[AUTO_LEARN], choices=("Off", "On"), default_value="On")
  tuner = Tuner(owner.rows, lambda: "Learning from this drive")
  switch = Tunable("torque", AUTO_LEARN)
  assert switch in tuner.steering() and tuner.changes(tuner.steering()) == 0
  tuner.reset_all()
  assert page(owner, "torque")[AUTO_LEARN] == "Off"
