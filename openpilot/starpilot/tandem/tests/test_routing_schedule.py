"""Offline Maps › Keep up to date: when Tandem's schedule queues a map update (starpilot/tandem/routing/schedule.py)."""
from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from openpilot.starpilot.tandem.routing import config as C, maps, schedule

IA = "us_state.IA"
DAY = schedule.DAY


def at(year: int, month: int, day: int) -> float:
  return datetime.datetime(year, month, day, 12, tzinfo=datetime.UTC).timestamp()


@pytest.fixture(autouse=True)
def routing_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
  monkeypatch.setenv("TANDEM_ROUTING_DIR", str(tmp_path))
  monkeypatch.setenv("TANDEM_ROUTING", "1")
  return tmp_path


def finished(created: float, phase: str = "ready") -> None:
  """A map job that ended: map-job.json, and the request it answered."""
  C.atomic_json(C.root() / "map-request.json", {"id": "j", "selection": IA, "created": created})
  C.atomic_json(C.root() / "map-job.json", {"id": "j", "selection": IA, "created": created, "phase": phase})


def test_off_by_default_and_saves_the_choice() -> None:
  assert schedule.every() == schedule.OFF
  schedule.set_every(schedule.MONTHLY)
  assert schedule.every() == schedule.MONTHLY
  with pytest.raises(ValueError):
    schedule.set_every("hourly")


def test_weekly_waits_a_week_after_the_last_update() -> None:
  schedule.set_every(schedule.WEEKLY)
  finished(at(2026, 11, 1))
  assert not schedule.due(at(2026, 11, 7), IA)
  assert schedule.due(at(2026, 11, 8), IA)
  assert not schedule.due(at(2026, 11, 8), "")   # no regions chosen


def test_monthly_waits_for_each_months_routing_build() -> None:
  schedule.set_every(schedule.MONTHLY)
  finished(at(2026, 11, 2))
  assert not schedule.due(at(2026, 11, 26), IA)   # this month's data isn't published yet
  assert schedule.due(at(2026, 11, 27), IA)
  finished(at(2026, 11, 28))
  assert not schedule.due(at(2026, 12, 20), IA)   # already has November's
  assert schedule.due(at(2026, 12, 28), IA)


def test_queues_only_parked_on_wifi_and_retries_a_failure_a_day_later() -> None:
  schedule.set_every(schedule.WEEKLY)
  finished(at(2026, 11, 1), phase="failed")
  now = at(2026, 11, 10)
  assert not schedule.poll(False, True, now) and not schedule.poll(True, False, now)
  assert schedule.poll(True, True, now)
  assert maps.selection() == IA and not schedule.due(now, IA)   # queued: the same job as Update maps
  finished(now, phase="failed")
  assert not schedule.due(now + DAY - 60, IA)
  assert schedule.due(now + DAY, IA)


def test_nothing_queues_while_a_job_runs_or_offline_routing_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
  schedule.set_every(schedule.WEEKLY)
  C.atomic_json(C.root() / "map-request.json", {"id": "k", "selection": IA, "created": at(2026, 11, 1)})
  assert not schedule.due(at(2026, 12, 1), IA)   # a requested job hasn't finished
  finished(at(2026, 11, 1))
  monkeypatch.setenv("TANDEM_ROUTING", "0")
  assert not schedule.due(at(2026, 12, 1), IA)
