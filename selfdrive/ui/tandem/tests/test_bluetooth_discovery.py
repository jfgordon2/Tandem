"""Discovery through Tandem's adapter, with delayed status updates and the shared Park permission."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from openpilot.starpilot.system.bluetooth.protocol import BluetoothDevice, BluetoothStatus
from openpilot.system.ui.lib import bluetooth_manager
from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import UpstreamBluetooth
from openpilot.selfdrive.ui.tandem.settings.connections import WhileShown
from openpilot.selfdrive.ui.tandem.rows import Text


class Manager:
  def __init__(self):
    self.status = BluetoothStatus()
    self.calls = []

  def set_active(self, active):
    self.calls.append(("active", active))

  def set_power(self, enabled):
    self.calls.append(("power", enabled))

  def set_scanning(self, enabled):
    self.calls.append(("scan", enabled))

  def operation_for(self, address):
    return ""

  def pair(self, address):
    self.calls.append(("pair", address))

  def connect(self, address):
    self.calls.append(("connect", address))

  def forget(self, address):
    self.calls.append(("forget", address))


@pytest.fixture
def adapter(monkeypatch):
  manager = Manager()
  monkeypatch.setattr(bluetooth_manager, "BluetoothManager", lambda: manager)
  monkeypatch.setattr(UpstreamBluetooth, "_parked", staticmethod(lambda: False))
  bt = UpstreamBluetooth()
  manager.calls.clear()
  return SimpleNamespace(bt=bt, manager=manager)


def test_first_open_waits_for_status_power_and_adapter_then_renews_scan(adapter):
  bt, manager = adapter.bt, adapter.manager
  bt.set_active(True)
  bt.tick()
  assert manager.calls == [("active", True)]   # initial cached status has no offroad or radio data yet

  manager.status = BluetoothStatus(available=True, offroad=True)
  for _ in range(3):
    bt.tick()
  assert manager.calls == [("active", True), ("power", True)]
  manager.status = replace(manager.status, enabled=True)
  bt.tick()
  assert manager.calls[-1] == ("power", True)   # the radio is still starting
  manager.status = replace(manager.status, powered=True)
  for _ in range(3):
    bt.tick()
  assert manager.calls == [("active", True), ("power", True), ("scan", True)]

  manager.status = replace(manager.status, discovering=True)
  bt.tick()
  manager.status = replace(manager.status, discovering=False)   # the daemon's 20 s scan ended
  bt.tick()
  assert manager.calls[-2:] == [("scan", True), ("scan", True)]


@pytest.mark.parametrize("enabled", [False, True])
def test_open_while_driving_waits_until_parked(adapter, enabled):
  bt, manager = adapter.bt, adapter.manager
  manager.status = BluetoothStatus(available=True, enabled=enabled, powered=enabled, offroad=False)
  bt.set_active(True)
  bt.tick()
  assert manager.calls == [("active", True)]
  manager.status = replace(manager.status, offroad=True)
  bt.tick()
  assert manager.calls[-1] == (("scan", True) if enabled else ("power", True))


@pytest.mark.parametrize("discovering", [False, True])
def test_leaving_stops_a_pending_or_running_scan_and_does_not_restart_it(adapter, discovering):
  bt, manager = adapter.bt, adapter.manager
  manager.status = BluetoothStatus(available=True, enabled=True, powered=True, offroad=True)
  bt.set_active(True)
  manager.status = replace(manager.status, discovering=discovering)
  bt.tick()
  bt.set_active(False)
  assert manager.calls == [("active", True), ("scan", True), ("scan", False), ("active", False)]
  bt.tick()
  assert manager.calls[-1] == ("active", False)


def test_leaving_while_power_starts_does_not_scan_later(adapter):
  bt, manager = adapter.bt, adapter.manager
  manager.status = BluetoothStatus(available=True, offroad=True)
  bt.set_active(True)
  bt.set_active(False)
  manager.status = replace(manager.status, enabled=True, powered=True)
  bt.tick()
  assert manager.calls == [("active", True), ("power", True), ("active", False)]


def test_pairing_and_status_errors_do_not_start_another_scan(adapter):
  bt, manager = adapter.bt, adapter.manager
  manager.status = BluetoothStatus(available=True, offroad=True, enabled=True, powered=True, pairing_address="AA")
  bt.set_active(True)
  assert manager.calls == [("active", True)]
  manager.status = replace(manager.status, pairing_address="", error="adapter unavailable")
  bt.tick()
  assert manager.calls == [("active", True)]
  manager.status = replace(manager.status, error="")
  bt.tick()
  assert manager.calls[-1] == ("scan", True)


def test_bluetooth_sections_tick_the_adapter_while_shown(adapter):
  bt, manager = adapter.bt, adapter.manager
  wrapper = WhileShown(Text(""), lambda: bt.set_active(True), lambda: bt.set_active(False), bt.tick)
  wrapper.show_event()
  manager.status = BluetoothStatus(available=True, offroad=True, enabled=True, powered=True)
  wrapper._update_state()
  assert manager.calls == [("active", True), ("scan", True)]
  wrapper.hide_event()
  assert manager.calls[-2:] == [("scan", False), ("active", False)]


def test_verified_park_enables_scan_with_ignition_on_without_changing_raw_offroad_state(adapter, monkeypatch):
  bt, manager = adapter.bt, adapter.manager
  manager.status = BluetoothStatus(available=True, enabled=True, powered=True, offroad=False)
  monkeypatch.setattr(bt, "_parked", lambda: True)
  bt.set_active(True)
  assert manager.calls == [("active", True), ("scan", True)]
  assert bt.status().offroad and not manager.status.offroad
  bt.set_active(False)
  assert manager.calls[-2:] == [("scan", False), ("active", False)]


def test_pairing_uses_verified_park_permission_and_keeps_existing_connect_policy(adapter, monkeypatch):
  bt, manager = adapter.bt, adapter.manager
  device = BluetoothDevice("AA", "MyChevrolet", audio=True)
  manager.status = BluetoothStatus(available=True, enabled=True, powered=True, offroad=False, devices=(device,))
  assert not bt.select("AA") and not manager.calls
  monkeypatch.setattr(bt, "_parked", lambda: True)
  assert not bt.select("AA") and manager.calls == [("pair", "AA")]
  manager.status = replace(manager.status, devices=(replace(device, paired=True),))
  assert not bt.select("AA") and manager.calls[-1] == ("connect", "AA")
  manager.status = replace(manager.status, devices=(replace(device, paired=True, connected=True),))
  assert bt.select("AA")
  bt.forget("AA")
  assert manager.calls[-1] == ("forget", "AA")
  assert not manager.status.offroad
