"""The compass (onroad/compass.py): a reliable moving heading, kept through stops and restarts."""
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from openpilot.selfdrive.ui.tandem.onroad.compass import DriveCompass, SAVED_HEADING
from openpilot.selfdrive.ui.tandem.prefs import COMPASS, pref_files


def fix(bearing: float, speed: float = 3.0, accuracy: float = 5.0, valid: bool = True) -> SimpleNamespace:
  return SimpleNamespace(hasFix=valid, bearingDeg=bearing, bearingAccuracyDeg=accuracy, speed=speed)


def test_compass_restores_west_when_the_car_is_started_parked() -> None:
  compass = DriveCompass()
  assert compass.direction == ""
  compass.observe(fix(270), 11.0, 10.0, 11.0, speed=3.0, reverse=False)
  compass.offroad(12.0)

  restarted = DriveCompass()
  restarted.observe(fix(0), 21.0, 20.0, 21.0, speed=0.0, reverse=False)
  assert restarted.direction == "W"
  restarted.observe(fix(0), 22.0, 20.0, 22.0, speed=3.0, reverse=False)
  assert restarted.direction == "N"


@pytest.mark.parametrize(("sample", "timestamp", "now"), [
  (fix(0, speed=0.0), 11.0, 11.0),
  (fix(0, valid=False), 11.0, 11.0),
  (fix(0, accuracy=90.0), 11.0, 11.0),
  (fix(float("nan")), 11.0, 11.0),
  (fix(0), 9.0, 11.0),   # previous drive
  (fix(0), 11.0, 14.0),  # stale fix from this drive
])
def test_unreliable_fixes_leave_the_saved_direction(sample: SimpleNamespace, timestamp: float, now: float) -> None:
  assert SAVED_HEADING.set("W")
  compass = DriveCompass()
  compass.observe(sample, timestamp, 10.0, now, speed=3.0, reverse=False)
  assert compass.direction == "W"
  assert SAVED_HEADING.get() == "W"


def test_compass_saves_latest_direction_offroad_and_faces_opposite_reverse_course() -> None:
  compass = DriveCompass()
  compass.observe(fix(180), 11.0, 10.0, 11.0, speed=3.0, reverse=False)
  compass.observe(fix(90), 12.0, 10.0, 12.0, speed=-3.0, reverse=True)
  assert compass.direction == "W"
  assert SAVED_HEADING.get() == "S"  # the disk write is rate-limited while moving
  compass.offroad(13.0)
  assert DriveCompass().direction == "W"


def test_compass_retries_a_failed_save_at_ignition_off(monkeypatch: pytest.MonkeyPatch) -> None:
  compass = DriveCompass()
  with monkeypatch.context() as disk:
    disk.setattr(SAVED_HEADING, "set", lambda _heading: False)
    compass.observe(fix(270), 11.0, 10.0, 11.0, speed=3.0, reverse=False)
    assert DriveCompass().direction == ""
  compass.offroad(12.0)
  assert DriveCompass().direction == "W"


def test_compass_cache_is_not_a_setting_and_corruption_is_ignored(tandem_prefs: Path) -> None:
  cache = tandem_prefs / ".tandem_compass_heading"
  cache.write_bytes(b"\xff")
  assert DriveCompass().direction == ""
  assert cache not in pref_files(tandem_prefs)


class Samples:
  """openpilot's UI subscriber, with both GPS services and the car."""

  def __init__(self, values: dict[str, SimpleNamespace]) -> None:
    self.values = values
    self.valid = dict.fromkeys(values, True)
    self.alive = self.valid
    self.recv_frame = dict.fromkeys(values, 2)
    self.logMonoTime = dict.fromkeys(values, 11_000_000_000)

  def __getitem__(self, service: str) -> SimpleNamespace:
    return self.values[service]


def ui(external: bool) -> SimpleNamespace:
  sm = Samples({"gpsLocation": fix(270), "gpsLocationExternal": fix(90), "carState": SimpleNamespace(vEgo=3.0)})
  return SimpleNamespace(started=True, started_frame=1, started_time=10.0, sm=sm,
                         params=SimpleNamespace(get_bool=lambda key: external and key == "UbloxAvailable"))


@pytest.fixture(autouse=True)
def gps_helper(monkeypatch: pytest.MonkeyPatch) -> None:
  """openpilot's common.gps without its native Params library: the u-blox source when it's available."""
  gps = ModuleType("openpilot.common.gps")
  gps.get_gps_location_service = lambda params: "gpsLocationExternal" if params.get_bool("UbloxAvailable") else "gpsLocation"  # type: ignore[attr-defined]
  monkeypatch.setitem(sys.modules, "openpilot.common.gps", gps)


@pytest.mark.parametrize("external", [False, True])
def test_compass_reads_starpilots_selected_gps(external: bool) -> None:
  compass = DriveCompass()
  compass.update(ui(external), now=11.0, reverse=False)
  assert compass.direction == ("E" if external else "W") and compass.heading() == compass.direction


def test_compass_off_reads_nothing_and_shows_nothing() -> None:
  COMPASS.set(False)
  compass = DriveCompass()
  compass.update(ui(False), now=11.0, reverse=False)
  assert compass.direction == "" and compass.heading() == ""
  COMPASS.set(True)
  compass.update(ui(False), now=11.0, reverse=False)
  assert compass.heading() == "W"
