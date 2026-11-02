"""Ignition-on Bluetooth setup requires fresh, stationary Park and inactive driving controls."""
from types import SimpleNamespace
import time

import pytest
from cereal import car

from openpilot.starpilot.tandem.bluetooth import controller_type, stationary_park
from openpilot.starpilot.system.bluetooth.daemon import BluetoothController
from openpilot.starpilot.system.bluetooth.tests.test_bluetooth import FakeBlueZ, FakeParams, FakeRadio

NOW = 100.0
SERVICES = ("carState", "carControl")


class Messages(dict):
  def __init__(self, cs, cc):
    super().__init__(carState=cs, carControl=cc)
    self.valid = dict.fromkeys(SERVICES, True)
    self.alive = dict.fromkeys(SERVICES, True)
    self.recv_time = dict.fromkeys(SERVICES, NOW)
    self.logMonoTime = dict.fromkeys(SERVICES, int(NOW * 1e9))


@pytest.fixture
def messages():
  return Messages(car.CarState.new_message(gearShifter="park", vEgo=0.0, standstill=True), car.CarControl.new_message())


def test_live_park_readers_allow_setup_with_controls_inactive(messages):
  with car.CarState.from_bytes(messages["carState"].to_bytes()) as cs, car.CarControl.from_bytes(messages["carControl"].to_bytes()) as cc:
    assert stationary_park(Messages(cs, cc), NOW)


@pytest.mark.parametrize("gear", ["drive", "neutral", "reverse", "unknown"])
def test_every_other_gear_blocks_pairing(messages, gear):
  messages["carState"].gearShifter = gear
  assert not stationary_park(messages, NOW)


@pytest.mark.parametrize("speed", [0.1, -0.1, 1.0, float("nan"), float("inf")])
def test_nonzero_or_invalid_speed_blocks_pairing(messages, speed):
  messages["carState"].vEgo = speed
  assert not stationary_park(messages, NOW)


@pytest.mark.parametrize("field", ["enabled", "latActive", "longActive"])
def test_any_active_driving_control_blocks_pairing(messages, field):
  setattr(messages["carControl"], field, True)
  assert not stationary_park(messages, NOW)


def test_missing_standstill_blocks_pairing(messages):
  messages["carState"].standstill = False
  assert not stationary_park(messages, NOW)


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize("kind", ["invalid", "dead", "old_receive", "old_publication", "future_publication", "missing"])
def test_invalid_stale_or_missing_messages_fail_closed(messages, service, kind):
  if kind == "invalid":
    messages.valid[service] = False
  elif kind == "dead":
    messages.alive[service] = False
  elif kind == "old_receive":
    messages.recv_time[service] = NOW - 2
  elif kind == "old_publication":
    messages.logMonoTime[service] = int((NOW - 2) * 1e9)
  elif kind == "future_publication":
    messages.logMonoTime[service] = int((NOW + 2) * 1e9)
  else:
    messages.pop(service)
  assert not stationary_park(messages, NOW)


def parked_controller(monkeypatch):
  monkeypatch.setenv("TANDEM_SETTINGS", "1")
  monitor = SimpleNamespace(allowed=lambda: True)
  cls = controller_type(BluetoothController, lambda: monitor)
  bluez = FakeBlueZ()
  params = FakeParams(IsOffroad=False, BluetoothEnabled=True, BluetoothAudioAddress=bluez.device["address"])
  memory = FakeParams()
  controller = cls(params=params, bluez_factory=lambda: bluez, radio=FakeRadio(), params_memory=memory, sleep=lambda _: None)
  return controller, monitor, bluez, params, memory


def test_service_authorizes_verified_park_and_stops_scan_when_permission_is_lost(monkeypatch):
  controller, monitor, bluez, params, _ = parked_controller(monkeypatch)
  controller.handle({"command": "start_scan"})
  assert bluez.discovering and not controller.status()["offroad"] and not params.get_bool("IsOffroad")
  controller._maintain_scan({"discovering": True, "offroad": False}, time.monotonic())
  assert bluez.discovering
  monitor.allowed = lambda: False
  with pytest.raises(RuntimeError, match="offroad"):
    controller.handle({"command": "pair", "address": bluez.device["address"]})
  controller._maintain_scan({"discovering": True, "offroad": False}, time.monotonic())
  assert not bluez.discovering


def test_delayed_sound_test_rechecks_park_permission(monkeypatch):
  controller, monitor, bluez, _, memory = parked_controller(monkeypatch)
  bluez.device["connected"] = True
  controller._test_audio_worker(bluez.device["address"], time.monotonic())
  assert memory.get("TestAlert") == "engage"
  memory.remove("TestAlert")
  monitor.allowed = lambda: False
  controller._test_audio_worker(bluez.device["address"], time.monotonic())
  assert memory.get("TestAlert") is None


def test_upstream_fallback_retains_original_offroad_gate(monkeypatch):
  monkeypatch.setenv("TANDEM_SETTINGS", "0")
  assert controller_type(BluetoothController) is BluetoothController
  controller = BluetoothController(FakeParams(IsOffroad=False, BluetoothEnabled=True), radio=FakeRadio())
  with pytest.raises(RuntimeError, match="offroad"):
    controller.handle({"command": "start_scan"})
