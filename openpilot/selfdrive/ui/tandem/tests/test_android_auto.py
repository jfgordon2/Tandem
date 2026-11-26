"""Connections › Android Auto: StarPort's switch, setup steps and Galaxy link, over StarPilot's StarPort status."""
from __future__ import annotations

from dataclasses import dataclass

from openpilot.selfdrive.ui.tandem.settings.android_auto import AndroidAuto, StarPortStatus


@dataclass
class Bluetooth:
  enabled: bool = False
  offroad: bool = True
  available: bool = True

  def status(self) -> Bluetooth:
    return self

  def set_power(self, on: bool) -> None:
    self.enabled = on


def model(status: StarPortStatus, bluetooth: Bluetooth | None = None, saved: list | None = None) -> AndroidAuto:
  m = AndroidAuto(lambda: status, lambda: "https://galaxy.firestar.link/x/#/starport", bluetooth,   # type: ignore[arg-type]
                  set_enabled=(saved if saved is not None else []).append)
  m.status = status
  return m


def test_not_set_up_until_the_app_is_added() -> None:
  m = model(StarPortStatus(supported=True))
  assert m.summary() in ("Not set up",) and not m.can_switch() and m.switch_note() == "Add the Android Auto app first"
  assert m.app_line() == "Google's app file, from your phone · Not added" and m.pair_line() == "Parked, over Bluetooth"


def test_set_up_and_projecting() -> None:
  m = model(StarPortStatus(supported=True, enabled=True, app=True, app_days=74, car_type="builtin", car="Kia EV6",
                           state="streaming", label="Projecting"))
  m.tick = lambda: None   # type: ignore[method-assign]
  assert m.summary() == "Connected" and m.headline() == "Connected · showing on your car"
  assert (m.app_line(), m.car_line(), m.pair_line()) == ("Added · good for 74 more days", "Built-in wireless", "Paired with Kia EV6")
  assert m.pair_done() and m.can_switch()


def test_a_cable_needs_no_pairing() -> None:
  m = model(StarPortStatus(supported=True, app=True, car_type="usb"))
  assert m.car_line() == "USB cable" and m.pair_done() and m.pair_line() == "No pairing needed for this connection"


def test_turning_on_turns_bluetooth_on_first_and_saves_starpilots_switch() -> None:
  bluetooth, saved = Bluetooth(), []
  m = model(StarPortStatus(supported=True, app=True), bluetooth, saved)
  assert m.needs_bluetooth() and m.bluetooth_allowed()
  m.set_enabled(True)
  assert bluetooth.enabled and saved == [True] and m.status.enabled
  m.set_enabled(False)
  assert saved == [True, False] and bluetooth.enabled   # Bluetooth stays on: other things use it


def test_off_always_works_and_unsupported_builds_say_so() -> None:
  m = model(StarPortStatus(supported=False, enabled=True))
  assert m.can_switch() and m.switch_note() == "Not available on this device"
