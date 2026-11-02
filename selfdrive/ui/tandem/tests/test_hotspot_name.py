"""A name edit must preserve the password, survive a new manager, and leave Wi-Fi alone when the hotspot is off."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from openpilot.starpilot.tandem import wifi
from openpilot.selfdrive.ui.tandem.settings.network_tab import Network, cellular_panel
from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeWifi
from openpilot.selfdrive.ui.tandem.tests.test_settings import FakeCache


def profile(ssid="weedle-c488", identifier="Hotspot", mode="ap"):
  return {"connection": {"id": ("s", identifier), "uuid": ("s", "same-uuid"), "autoconnect": ("b", False)},
          "802-11-wireless": {"ssid": ("ay", ssid.encode()), "mode": ("s", mode)},
          "802-11-wireless-security": {"key-mgmt": ("s", "wpa-psk"), "psk": ("s", "unchanged-password")},
          "ipv4": {"method": ("s", "shared"), "never-default": ("b", True)}}


class Router:
  def __init__(self):
    self.profiles = {"/hotspot": profile(), "/home": profile("Home Wi-Fi", "Home", "infrastructure")}
    self.fail = None
    self.updates = []

  def send_and_get_reply(self, message):
    method, path = message.header.fields[3], message.header.fields[1]
    error = method == self.fail
    body = []
    if method == "ListConnections":
      body = [list(self.profiles)]
    elif method == "GetSettings":
      settings = deepcopy(self.profiles[path])
      settings["802-11-wireless-security"].pop("psk")   # NetworkManager never returns secrets in GetSettings
      body = [settings]
    elif method == "GetSecrets":
      body = [{"802-11-wireless-security": deepcopy(self.profiles[path]["802-11-wireless-security"])}]
    elif method == "Update" and not error:
      self.profiles[path] = deepcopy(message.body[0])
      self.updates.append(path)
    return SimpleNamespace(header=SimpleNamespace(message_type=wifi.upstream.MessageType.error if error else
                                                 wifi.upstream.MessageType.method_return), body=body)


def manager(router):
  obj = wifi.WifiManager.__new__(wifi.WifiManager)
  obj._router_main = router
  obj._exit = True   # this fixture has no monitor/scanner to stop
  obj._backend_unavailable = obj._nmcli_networking = obj._fake_networking = False
  obj.tethering_name_busy = obj.tethering_name_failed = False
  obj._tethering_ssid = "weedle-c488"
  obj._networks = []
  obj._wifi_state = wifi.upstream.WifiState("Home Wi-Fi", wifi.upstream.ConnectStatus.CONNECTED)
  obj._init_connections()
  obj.activations = []

  def activate(ssid, block=False):
    obj.activations.append((ssid, block))
    obj._wifi_state = wifi.upstream.WifiState(ssid, wifi.upstream.ConnectStatus.CONNECTED)

  obj.activate_connection = activate
  return obj


@pytest.fixture
def jobs(monkeypatch):
  queued = []
  monkeypatch.setattr(wifi, "threading", SimpleNamespace(Thread=lambda target, **kw: SimpleNamespace(start=lambda: queued.append(target))))
  return queued


def test_rename_persists_in_the_same_profile_without_changing_password_or_wifi(jobs):
  router = Router()
  before = deepcopy(router.profiles["/hotspot"])
  obj = manager(router)
  obj.set_tethering_ssid("Our car")
  assert obj.tethering_name_busy and not obj.tethering_name_ready
  assert obj.tethering_ssid == "weedle-c488"   # don't claim a change before NetworkManager saves it
  jobs.pop()()
  saved = router.profiles["/hotspot"]
  assert saved["802-11-wireless"]["ssid"] == ("ay", b"Our car")
  assert saved["connection"]["id"] == ("s", wifi.HOTSPOT_PROFILE)
  before["802-11-wireless"]["ssid"] = saved["802-11-wireless"]["ssid"]
  before["connection"]["id"] = saved["connection"]["id"]
  assert saved == before
  assert obj.connected_ssid == "Home Wi-Fi" and not obj.activations
  assert not obj.tethering_name_busy and not obj.tethering_name_failed
  assert obj.is_connection_saved("Our car") and not obj.is_connection_saved("weedle-c488")
  restarted = manager(router)
  assert restarted.tethering_ssid == "Our car" and restarted.tethering_name_ready


def test_active_hotspot_reactivates_with_the_saved_name(jobs):
  obj = manager(Router())
  obj._wifi_state = wifi.upstream.WifiState(obj.tethering_ssid, wifi.upstream.ConnectStatus.CONNECTED)
  obj._networks = [wifi.upstream.Network(obj.tethering_ssid, 100, wifi.upstream.SecurityType.WPA2, True)]
  obj.set_tethering_ssid("Car audio")
  jobs.pop()()
  assert obj.activations == [("Car audio", True)] and obj.is_tethering_active()
  assert obj._networks[0].ssid == "Car audio" and obj._networks[0].is_tethering


@pytest.mark.parametrize("method", ["GetSecrets", "Update"])
def test_failed_save_leaves_name_password_and_connection_untouched(jobs, method):
  router = Router()
  before = deepcopy(router.profiles)
  obj = manager(router)
  router.fail = method
  obj.set_tethering_ssid("Our car")
  jobs.pop()()
  assert router.profiles == before and not router.updates
  assert obj.tethering_ssid == "weedle-c488" and obj.tethering_name_failed and obj.tethering_name_ready
  assert obj.connected_ssid == "Home Wi-Fi" and not obj.activations
  router.fail = None
  obj.set_tethering_ssid("Our car")
  jobs.pop()()
  assert not obj.tethering_name_failed and obj.tethering_ssid == "Our car"


def test_only_owned_access_point_profiles_override_the_default():
  router = Router()
  router.profiles["/home"]["connection"]["id"] = ("s", wifi.HOTSPOT_PROFILE)
  assert manager(router).tethering_ssid == "weedle-c488"


@pytest.mark.parametrize("name", ["", "   ", "x" * 33, "車" * 11, "car\nname", "car\0name", "car\x7fname"])
def test_invalid_names_are_rejected_before_any_network_change(jobs, name):
  obj = manager(Router())
  with pytest.raises(ValueError):
    obj.set_tethering_ssid(name)
  assert not jobs and obj.tethering_ssid == "weedle-c488"


@pytest.mark.parametrize("name", ["x" * 32, "車" * 10, "Our car", " car "])
def test_names_obey_the_utf8_byte_limit_without_dropping_meaningful_spaces(name):
  assert wifi.name_problem(name) is None


def test_busy_unavailable_unchanged_and_duplicate_names_do_not_start_an_update(jobs):
  obj = manager(Router())
  obj.set_tethering_ssid("weedle-c488")
  obj.set_tethering_ssid("Home Wi-Fi")
  assert not jobs and obj.tethering_name_failed
  obj.set_tethering_ssid("Our car")
  obj.set_tethering_ssid("Another car")
  assert len(jobs) == 1
  jobs.pop()()
  assert obj.tethering_ssid == "Our car"
  obj._backend_unavailable = True
  obj.set_tethering_ssid("Another car")
  assert not jobs


def test_name_row_opens_prefilled_keyboard_retries_invalid_input_and_saves():
  source, asked = FakeWifi(), []
  model = Network(source, SettingsStore(FakeCache(), lambda: None), ask=lambda *a, **kw: asked.append((a, kw)))
  panel = cellular_panel(model, lambda: None)
  row = panel.items[1]
  assert row._title == "Hotspot name" and model.hotspot_name_detail() == source.tethering_ssid
  row._control._click_callback()
  args, kwargs = asked[-1]
  assert args[:3] == ("Hotspot name", "Connected devices will need to reconnect.", "weedle-c488")
  assert args[4:7] == (1, False, "Save") and kwargs == {"max_length": 32}
  assert source.tethering_ssid == "weedle-c488"   # opening or cancelling never writes
  args[3]("車" * 11)
  assert asked[-1][0][1] == "Name is too long. Use a shorter name." and source.tethering_ssid == "weedle-c488"
  asked[-1][0][3]("Home Wi-Fi")
  assert asked[-1][0][1] == "A saved network already uses this name"
  asked[-1][0][3]("Our car")
  assert model.hotspot_name_detail() == "Our car"


def test_failed_name_save_is_visible_alongside_the_actual_name():
  source = FakeWifi()
  model = Network(source, SettingsStore(FakeCache(), lambda: None))
  source.tethering_name_failed = True
  assert model.hotspot_name_detail() == "weedle-c488 · Couldn't save"
