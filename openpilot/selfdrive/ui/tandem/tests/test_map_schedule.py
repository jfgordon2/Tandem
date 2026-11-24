"""Offline Maps › Keep up to date on the device: the card's choice, and the once-a-minute check in ui.py's frame loop."""
from __future__ import annotations

from openpilot.selfdrive.ui.tandem.map_schedule import MapScheduleWatch, on_wifi
from openpilot.selfdrive.ui.tandem.settings.maps import Maps
from openpilot.selfdrive.ui.tandem.tests.fakes import sample_maps


def test_the_card_reads_and_saves_tandems_schedule() -> None:
  saved = ["monthly"]
  maps = Maps(sample_maps(), schedule=(lambda: saved[0], saved.append))
  assert maps.schedule == 2
  maps.set_schedule(1)
  assert saved[-1] == "weekly"
  assert Maps(sample_maps(), schedule=(lambda: "hourly", saved.append)).schedule == 0   # unknown reads as Off


def test_checks_once_a_minute_and_only_parked_on_wifi() -> None:
  calls: list[tuple[bool, bool]] = []
  now = [0.0]
  watch = MapScheduleWatch(lambda parked, wifi: calls.append((parked, wifi)), clock=lambda: now[0])
  watch.poll(False, True)
  watch.poll(True, False)
  assert not calls
  watch.poll(True, True)
  watch._pending.result(timeout=5)
  watch.poll(True, True)   # within the minute
  now[0] = 61.0
  watch.poll(True, True)
  watch._pending.result(timeout=5)
  watch.close()
  assert calls == [(True, True), (True, True)]


def test_a_failing_check_never_reaches_the_frame() -> None:
  def broken(parked: bool, wifi: bool) -> None:
    raise OSError("unreadable")
  watch = MapScheduleWatch(broken)
  watch.poll(True, True)
  watch._pending.result(timeout=5)   # swallowed on the worker
  watch.close()


def test_wifi_is_read_from_a_real_capnp_enum(tmp_path) -> None:
  import capnp
  schema = tmp_path / "device.capnp"
  schema.write_text("@0xd4a4f0a1c0ffee02;\nstruct DeviceState { networkType @0 :Net;\n  enum Net { none @0; wifi @1; cell4G @2; } }\n")
  message = capnp.load(str(schema)).DeviceState.new_message()
  sm = type("SM", (), {"valid": {"deviceState": True}, "__getitem__": lambda self, key: message})()
  message.networkType = "wifi"
  assert on_wifi(sm)
  message.networkType = "cell4G"
  assert not on_wifi(sm)
  sm.valid["deviceState"] = False
  message.networkType = "wifi"
  assert not on_wifi(sm)
