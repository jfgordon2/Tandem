"""Cellular feedback must be fresh, modem-backed, and independent of Wi-Fi."""
from dataclasses import replace
import threading

import pytest

from openpilot.starpilot.tandem import cellular as C


CONNECTED = C.Observation(sim=True, modem=11, registration=1, quality=60, technology="LTE", connected=True,
                          address="10.1.2.3", bearer_apn="carrier.apn", auto_config=True, identity=("m", "b", "a"))


def observed(value, now=10):
  clock = [float(now)]
  monitor = C.Monitor(reader_factory=None, clock=lambda: clock[0])
  monitor._observation, monitor._updated = value, clock[0]
  return monitor, clock


@pytest.mark.parametrize("value,expected", [
  (CONNECTED, "connected"),
  (replace(CONNECTED, quality=0), "connected"),
  (C.Observation(sim=False, wifi=True), "no_sim"),
  (C.Observation(sim=True, modem=7, registration=2, quality=0, wifi=True), "no_signal"),
  (C.Observation(sim=True, modem=7, registration=2, wifi=True), "no_signal"),
  (C.Observation(sim=True, modem=7, registration=2, quality=50, connecting=True), "connecting"),
  (C.Observation(sim=True, modem=8, registration=1, wifi=True), "wifi"),
  (C.Observation(sim=True, modem=8, registration=1, failed=True, wifi=True), "not_connected"),
  (C.Observation(sim=True, modem=8, registration=1), "not_connected"),
  (C.Observation(wifi=True), "checking"),
  (C.Observation(sim=True, modem=1, wifi=True), "checking"),
  (C.Observation(sim=True, wifi=True), "checking"),
])
def test_status_distinguishes_signal_sim_data_and_wifi(value, expected):
  monitor, _ = observed(value)
  assert monitor.status().code == expected


def test_old_connected_status_expires_even_when_drawing_continues():
  monitor, clock = observed(CONNECTED)
  clock[0] += C.FRESH + .1
  assert monitor.status().code == "checking"
  clock[0] = 0  # future/invalid timestamps also cannot show success
  assert monitor.status().code == "checking"


def test_saving_new_apn_cannot_reuse_an_old_connected_bearer():
  monitor, clock = observed(CONNECTED)
  monitor.apn_saved("new.apn", "carrier.apn")
  assert monitor.status().code == "connecting"
  monitor._observation, monitor._updated = CONNECTED, clock[0]
  assert monitor.status().code == "connecting"
  clock[0] += C.APPLY_TIMEOUT + .1
  monitor._updated = clock[0]
  assert monitor.status().code == "not_connected"
  monitor._observation = replace(CONNECTED, bearer_apn="new.apn")
  assert monitor.status().code == "connected"


def test_automatic_apn_needs_current_applied_settings_or_a_new_data_session():
  monitor, clock = observed(replace(CONNECTED, auto_config=False))
  monitor.apn_saved("", "carrier.apn")
  monitor._observation, monitor._updated = replace(CONNECTED, auto_config=False), clock[0]
  assert monitor.status().code == "connecting"
  monitor._observation = replace(CONNECTED, auto_config=True)
  assert monitor.status().code == "connected"
  monitor._observation = replace(CONNECTED, auto_config=False, identity=("m", "new-bearer", "new-active"))
  assert monitor.status().code == "connected"


def test_missing_signal_does_not_mean_missing_sim_or_no_service():
  monitor, _ = observed(C.Observation(sim=True, modem=8, registration=1, quality=None))
  assert monitor.status().code == "not_connected"


def test_worker_stops_when_hidden_and_a_pre_save_result_cannot_win(monkeypatch):
  entered, finish = threading.Event(), threading.Event()
  reads, closed = [], []
  class Reader:
    def __init__(self, keep):
      self.keep = keep
    def read(self):
      reads.append(1)
      entered.set()
      assert finish.wait(2)
      return CONNECTED
    def close(self):
      closed.append(1)
  monitor = C.Monitor(reader_factory=Reader)
  monitor.set_active(True)
  assert entered.wait(2)
  monitor.apn_saved("other.apn", "carrier.apn")
  monitor.set_active(False)
  thread = monitor._thread
  finish.set()
  thread.join(2)
  assert not thread.is_alive() and monitor._thread is None and closed == [1]
  assert monitor._updated is None and monitor.status().code == "connecting"
  assert reads == [1]


def test_worker_can_reopen_and_reads_fail_closed():
  ready, done = threading.Event(), threading.Event()
  class Reader:
    def __init__(self, keep):
      pass
    def read(self):
      ready.set()
      raise OSError("modem unavailable")
    def close(self):
      done.set()
  monitor = C.Monitor(reader_factory=Reader)
  for _ in range(2):
    ready.clear()
    monitor.set_active(True)
    assert ready.wait(2) and done.wait(2)
    monitor.set_active(False)
    thread = monitor._thread
    if thread:
      thread.join(2)
    assert monitor.status().code == "checking" and monitor._thread is None


def dbus_reader(*, state=11, sim="/sim/0", registration=1, include_bearer=False):
  reader = C.Reader.__new__(C.Reader)
  modem_path, bearer_path, device_path, active_path = "/modem/0", "/bearer/0", "/device/gsm", "/active/gsm"
  bearer = {"Connected": True, "Interface": "wwan0", "Properties": {"apn": "carrier.apn"}}
  objects = {modem_path: {C.MODEM: {"State": state, "Sim": sim, "Bearers": [bearer_path], "SignalQuality": (60, True),
                                 "AccessTechnologies": 1 << 14}, C.GPP: {"RegistrationState": registration}}}
  if include_bearer:
    objects[bearer_path] = {C.BEARER: bearer}
  props = {
    (C.MM, bearer_path, C.BEARER): bearer,
    (C.NM, "/org/freedesktop/NetworkManager", C.NM): {"ActiveConnections": ["/active/wifi", active_path]},
    (C.NM, "/active/wifi", C.ACTIVE): {"Type": "802-11-wireless", "State": 2, "Default": True, "Ip4Config": "/wifi-ip"},
    (C.NM, active_path, C.ACTIVE): {"Type": "gsm", "State": 2, "Devices": [device_path], "Ip4Config": "/gsm-ip"},
    (C.NM, device_path, C.DEVICE): {"DeviceType": 8, "Udi": modem_path, "State": 100, "IpInterface": "wwan0"},
    (C.NM, "/gsm-ip", C.NM + ".IP4Config"): {"AddressData": [{"address": "10.1.2.3"}]},
  }
  def request(bus, path, interface, method, *args):
    assert method in ("GetManagedObjects", "GetAppliedConnection")
    return (objects,) if method == "GetManagedObjects" else ({"gsm": {"apn": "carrier.apn", "auto-config": False}}, 1)
  reader.request = request
  reader.props = lambda bus, path, iface: props[(bus, path, iface)]
  return reader, props


@pytest.mark.parametrize("include_bearer", [False, True])
def test_reader_uses_mobile_bearer_and_address_not_the_active_wifi(include_bearer):
  reader, _ = dbus_reader(include_bearer=include_bearer)
  value = reader.read()
  assert value.connected and value.sim is True and value.wifi
  assert value.address == "10.1.2.3" and value.technology == "LTE" and value.quality == 60
  assert value.bearer_apn == value.applied_apn == "carrier.apn" and value.auto_config is False


@pytest.mark.parametrize("state,sim,expected", [(1, "/", None), (2, "/", None), (-1, "/", None), (6, "/", False), (8, "/sim/0", True)])
def test_initializing_or_failed_modem_is_not_fabricated_as_no_sim(state, sim, expected):
  reader, _ = dbus_reader(state=state, sim=sim)
  assert reader.read().sim is expected


def test_reader_requires_a_matching_mobile_interface():
  reader, props = dbus_reader()
  props[(C.NM, "/device/gsm", C.DEVICE)]["IpInterface"] = "other-interface"
  assert not reader.read().connected


def test_reader_uses_mobile_ipv6_when_ipv4_has_no_usable_address():
  reader, props = dbus_reader()
  props[(C.NM, "/gsm-ip", C.NM + ".IP4Config")]["AddressData"] = [{"address": "127.0.0.1"}, {"address": "invalid"}]
  props[(C.NM, "/active/gsm", C.ACTIVE)]["Ip6Config"] = "/gsm-ip6"
  props[(C.NM, "/gsm-ip6", C.NM + ".IP6Config")] = {"AddressData": [{"address": "fe80::1"}, {"address": "2001:db8::1234"}]}
  value = reader.read()
  assert value.connected and value.address == "2001:db8::1234"


@pytest.mark.parametrize("modem,active", [(8, 2), (11, 1)])
def test_registration_or_an_activating_connection_does_not_confirm_data(modem, active):
  reader, props = dbus_reader(state=modem)
  props[(C.NM, "/active/gsm", C.ACTIVE)]["State"] = active
  value = reader.read()
  assert not value.connected and not value.address


@pytest.mark.parametrize("bits,label", [(1 << 16, "LTE"), (1 << 17, "LTE"), ((1 << 15) | (1 << 14), "5G"), (0, "")])
def test_access_technology_masks(bits, label):
  assert C.technology(bits) == label


def test_dbus_variants_are_unwrapped_without_losing_signal_freshness():
  assert C.unwrap({"SignalQuality": ("(ub)", (61, True)), "IP": ("a{sv}", {"address": ("s", "10.1.2.3")})}) == {
    "SignalQuality": (61, True), "IP": {"address": "10.1.2.3"}}
