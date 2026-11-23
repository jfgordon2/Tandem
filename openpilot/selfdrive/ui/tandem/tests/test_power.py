"""Device › Power, Uploads on Cellular and the Jetlink sidebar row, over StarPilot 7's owners."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from openpilot.selfdrive.ui.tandem.settings.power import COOLING, CUSTOM, ENABLED, HOURS, VOLTS, Power
from openpilot.selfdrive.ui.tandem.settings.storage import CELLULAR, cellular_row
from openpilot.selfdrive.ui.tandem.sidebar import Health, JetlinkWatch, jetlink_status
from openpilot.selfdrive.ui.tandem.tests.test_speed_steering_port import Owner

HOUR_CHOICES = ("1 h", "12 h", "30 h")
VOLT_CHOICES = ("11.8 V", "12.0 V", "12.5 V")


class PowerOwner(Owner):
  """StarPilot's power owner saves only a confirmed request."""

  def apply(self, page: str, request: Any) -> bool:
    if page == "parked_power" and not request.confirmation:
      self.requests.append(request)
      return False
    return super().apply(page, request)


class Drive:
  """StarPilot's DriveStateControl: a snapshot, and a change bound to its revision."""

  def __init__(self, mode: str = "auto", effective: str = "offroad", available: bool = True):
    self.status = {"mode": mode, "revision": 3, "available": available, "effective": effective, "overrideAllowed": True,
                   "reason": ""}
    self.changes: list[tuple[str, int, bool]] = []

  def snapshot(self) -> dict:
    return dict(self.status)

  def change(self, mode: str, revision: int, authorized: Any) -> None:
    if revision != self.status["revision"] or not authorized():
      raise ValueError("stale")   # StarPilot's Rejected
    self.changes.append((mode, revision, authorized()))
    self.status.update(mode=mode, revision=revision + 1)


def make(cooling: bool = True, drive: Drive | None = None, car_on: bool = False) -> tuple[Power, PowerOwner]:
  owner = PowerOwner({"parked_power": {ENABLED: "Stock", HOURS: "30 h", VOLTS: "11.8 V"},
                      "power": {COOLING: "Off"} if cooling else {}})
  owner.pages["parked_power"][HOURS] = replace(owner.pages["parked_power"][HOURS], choices=HOUR_CHOICES)
  owner.pages["parked_power"][VOLTS] = replace(owner.pages["parked_power"][VOLTS], choices=VOLT_CHOICES)
  return Power(owner.rows, drive or Drive(), lambda: True, lambda: car_on), owner


def test_parked_limits_save_only_when_confirmed() -> None:
  power, owner = make()
  assert not power.custom and not power.limits_editable()
  assert power.choices(HOURS) == list(HOUR_CHOICES)
  assert "30 h" in power.question(ENABLED, CUSTOM) and "11.8 V" in power.question(ENABLED, CUSTOM)
  assert power.save(ENABLED, CUSTOM)
  assert owner.requests[-1].confirmation
  assert power.custom and power.limits_editable()
  assert power.save(HOURS, "12 h") and power.hours() == "12 h"
  assert "12.0 V" in power.question(VOLTS, "12.0 V")


def test_unconfirmed_parked_change_is_refused() -> None:
  power, owner = make()
  assert not owner.rows("parked_power").set(ENABLED, CUSTOM)
  assert not power.custom


def test_cooling_shows_only_where_starpilot_offers_it() -> None:
  power, _ = make()
  assert power.cooling_offered() and not power.cooling
  power.set_cooling(True)
  assert power.cooling
  assert not make(cooling=False)[0].cooling_offered()


def test_drive_state_changes_through_starpilot() -> None:
  drive = Drive()
  power, _ = make(drive=drive)
  assert power.drive_state == 0 and power.drive_editable()
  assert not power.needs_offroad_confirmation(1)
  assert power.set_drive_state(2)
  assert drive.changes == [("onroad", 3, True)] and power.drive_state == 2


@pytest.mark.parametrize("car_on,effective", [(True, "offroad"), (False, "onroad")])
def test_forcing_offroad_while_driving_asks_first(car_on: bool, effective: str) -> None:
  power, _ = make(drive=Drive(effective=effective), car_on=car_on)
  assert power.needs_offroad_confirmation(1)
  assert not power.needs_offroad_confirmation(2)


def test_drive_state_unavailable() -> None:
  power, _ = make(drive=Drive(available=False))
  assert not power.drive_editable() and not power.set_drive_state(1)
  assert Power(make()[1].rows, None, lambda: True, lambda: False).drive_state == 0


def test_uploads_on_cellular_writes_starpilots_setting() -> None:
  owner = Owner({"data": {CELLULAR: "Off"}})
  data = owner.rows("data")
  row = cellular_row(data)
  assert row is not None and not data.on(CELLULAR)
  data.set_on(CELLULAR, True)
  assert data.on(CELLULAR)


def test_jetlink_row() -> None:
  assert jetlink_status(None) is None
  assert jetlink_status("connected").health == Health.GOOD
  assert jetlink_status("device").health == Health.OFF


def test_jetlink_feed_runs_only_while_watched() -> None:
  class Feed:
    def __init__(self) -> None:
      self.enabled: list[bool] = []

    def set_enabled(self, on: bool) -> None:
      self.enabled.append(on)

    def snapshot(self) -> Any:
      return type("Snap", (), {"port": "connected"})()

  feed = Feed()
  made: list[Feed] = []
  watch = JetlinkWatch(lambda: made.append(feed) or feed)
  assert watch.poll(False) is None and not made
  status = watch.poll(True)
  assert status is not None and status.health == Health.GOOD
  watch.poll(False)
  assert feed.enabled[0] is True and feed.enabled[-1] is False and len(made) == 1
