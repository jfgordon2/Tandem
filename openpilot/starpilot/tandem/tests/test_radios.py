from threading import Event
from types import SimpleNamespace

import pytest
from jeepney.low_level import HeaderFields, Message, MessageType

from openpilot.starpilot.tandem.radios import NetworkRadios, Radio, RadioControls, RadioError, RadioState
from openpilot.system.ui.lib.networkmanager import NM


class Bus:
  def __init__(self) -> None:
    self.props = {
      "RadioFlags": ("u", 3),
      "WirelessEnabled": ("b", True), "WirelessHardwareEnabled": ("b", True),
      "WwanEnabled": ("b", True), "WwanHardwareEnabled": ("b", True),
    }
    self.permissions = {f"{NM}.enable-disable-wifi": "yes", f"{NM}.enable-disable-wwan": "yes"}
    self.writes: list[tuple[str, bool]] = []
    self.close_count = 0
    self.reject_write = False

  def send_and_get_reply(self, msg: Message, timeout: float) -> SimpleNamespace:
    assert timeout == 2
    member = msg.header.fields[HeaderFields.member]
    if member == "GetAll":
      assert msg.body == (NM,)
      return self.reply((self.props,))
    if member == "GetPermissions":
      return self.reply((self.permissions,))
    assert member == "Set"
    interface, name, (kind, value) = msg.body
    assert interface == NM and kind == "b" and name in ("WirelessEnabled", "WwanEnabled")
    self.writes.append((name, value))
    if self.reject_write:
      return self.reply((), MessageType.error)
    self.props[name] = (kind, value)
    return self.reply(())

  @staticmethod
  def reply(body: tuple, kind: MessageType = MessageType.method_return) -> SimpleNamespace:
    return SimpleNamespace(body=body, header=SimpleNamespace(message_type=kind))

  def close(self) -> None:
    self.close_count += 1


def test_networkmanager_switches_are_independent_and_read_back() -> None:
  bus = Bus()
  radios = NetworkRadios(lambda: bus)
  assert radios.read() == {radio: RadioState(True, True, True) for radio in Radio}
  assert radios.set_enabled(Radio.WIFI, False) == RadioState(False, True, True)
  assert radios.read()[Radio.CELLULAR].enabled
  assert radios.set_enabled(Radio.CELLULAR, False) == RadioState(False, True, True)
  assert not radios.read()[Radio.WIFI].enabled
  assert radios.set_enabled(Radio.CELLULAR, False) == RadioState(False, True, True)
  assert bus.writes == [("WirelessEnabled", False), ("WwanEnabled", False)]
  assert bus.close_count == 6


def test_networkmanager_respects_permissions_hardware_blocks_and_missing_radios() -> None:
  bus = Bus()
  radios = NetworkRadios(lambda: bus)
  bus.props["WwanEnabled"] = ("b", False)
  bus.props["WwanHardwareEnabled"] = ("b", False)
  bus.permissions[f"{NM}.enable-disable-wifi"] = "auth"
  assert not any(state.can_toggle for state in radios.read().values())
  for radio, enable in ((Radio.WIFI, False), (Radio.CELLULAR, True)):
    with pytest.raises(RadioError):
      radios.set_enabled(radio, enable)
  assert bus.writes == []
  bus.props["RadioFlags"] = ("u", 1)
  assert Radio.CELLULAR not in radios.read()
  bus.props.pop("RadioFlags")  # older NetworkManager still exposes the radio properties
  assert Radio.CELLULAR in radios.read()


def test_networkmanager_rejected_write_keeps_the_old_state() -> None:
  bus = Bus()
  bus.reject_write = True
  radios = NetworkRadios(lambda: bus)
  with pytest.raises(RadioError, match="rejected"):
    radios.set_enabled(Radio.WIFI, False)
  assert radios.read()[Radio.WIFI].enabled
  assert bus.close_count == 2


def test_async_radio_controls_preserve_state_on_failure() -> None:
  bus = Bus()
  controller = RadioControls(NetworkRadios(lambda: bus))
  controller.refresh()
  assert controller._read_job is not None
  controller._read_job.join(timeout=2)
  assert controller.state(Radio.WIFI) == RadioState(True, True, True)
  bus.reject_write = True
  controller.set_enabled(Radio.WIFI, False)
  assert controller._write_job is not None
  controller._write_job.join(timeout=2)
  assert controller.failed == Radio.WIFI
  assert controller.state(Radio.WIFI) == RadioState(True, True, True)


def test_switch_request_during_refresh_runs_after_the_read(monkeypatch: pytest.MonkeyPatch) -> None:
  bus = Bus()
  backend = NetworkRadios(lambda: bus)
  controller = RadioControls(backend)
  controller.refresh()
  assert controller._read_job is not None
  controller._read_job.join(timeout=2)
  assert controller.state(Radio.WIFI) == RadioState(True, True, True)

  read_started, finish_read = Event(), Event()
  read = backend.read

  def slow_read() -> dict[Radio, RadioState]:
    states = read()
    read_started.set()
    if not finish_read.wait(timeout=5):
      raise TimeoutError("Test did not release the refresh")
    return states

  monkeypatch.setattr(backend, "read", slow_read)
  controller._next_read = 0.0
  controller.refresh()
  try:
    assert read_started.wait(timeout=2)
    assert not controller.writing
    controller.set_enabled(Radio.WIFI, False)
    assert controller.writing
    assert not bus.writes
  finally:
    finish_read.set()

  assert controller._write_job is not None
  controller._write_job.join(timeout=2)
  assert not controller.writing
  assert controller.state(Radio.WIFI) == RadioState(False, True, True)
  assert bus.writes == [("WirelessEnabled", False)]
