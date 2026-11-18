"""Connections › Network Test: the page shows what the tester measured, and spends data to suit the connection."""
import datetime

import pytest

from openpilot.selfdrive.ui.tandem import tokens as T
from openpilot.selfdrive.ui.tandem.base import resolve
from openpilot.selfdrive.ui.tandem.settings.network_test import (Connection, NetworkTestModel, Via, data_text, network_test_panel, ping_text,
                                                                 speed_text)
from openpilot.selfdrive.ui.tandem.tests.fakes import FakeNetworkTest
from openpilot.starpilot.tandem.network_test import METERED, UNMETERED, Phase, Problem, Result

MBPS = 1e6
DONE = Result(Phase.DONE, download=86.4 * MBPS, upload=11.2 * MBPS, ping=0.0243, used=148 * 2**20, budget=UNMETERED,
              finished=datetime.datetime.now().replace(hour=15, minute=42).timestamp())


def _model(shown=None, connection=None, ssid="Home Wi-Fi"):
  test = FakeNetworkTest(shown)
  now = [connection or Connection(Via.WIFI)]
  return NetworkTestModel(test, lambda: ssid, lambda: now[0]), test, now


@pytest.mark.parametrize("bits,full,short", [
  (540.26 * MBPS, "540 Mbps", "540 Mbps"), (86.44 * MBPS, "86.4 Mbps", "86 Mbps"), (4.257 * MBPS, "4.26 Mbps", "4.3 Mbps"),
  (0.35 * MBPS, "0.35 Mbps", "0.3 Mbps"),
])
def test_speeds_keep_the_digits_that_matter(bits, full, short):
  assert speed_text(bits) == full and speed_text(bits, short=True) == short


def test_ping_and_data_read_in_whole_units():
  assert ping_text(0.0243) == "24 ms" and ping_text(0.0002) == "1 ms"
  assert data_text(148 * 2**20) == "148 MB" and data_text(300_000) == "under 1 MB" and data_text(0) == "under 1 MB"


@pytest.mark.parametrize("connection,ssid,line,budget", [
  (Connection(Via.WIFI), "Home Wi-Fi", "Wi-Fi · Home Wi-Fi", UNMETERED),
  (Connection(Via.WIFI), None, "Wi-Fi", UNMETERED),
  (Connection(Via.WIFI, metered=True), "Pixel 9", "Wi-Fi · Pixel 9", METERED),      # a phone's hotspot
  (Connection(Via.CELLULAR, "LTE", metered=True), None, "Cellular · LTE", METERED),
  (Connection(Via.CELLULAR, "5G"), "Home Wi-Fi", "Cellular · 5G", METERED),         # cellular is small even when StarPilot doesn't mark it
  (Connection(Via.ETHERNET), None, "Ethernet", UNMETERED),
  (Connection(), "Home Wi-Fi", "Not connected", METERED),                           # not reported: assume the costly kind
])
def test_the_connection_sets_the_header_and_the_data_a_test_may_use(connection, ssid, line, budget):
  model, test, _ = _model(connection=connection, ssid=ssid)
  assert model.connection() == line and model.budget() is budget
  model.press()
  assert test.calls == [("start", budget)]


def test_before_a_test_the_page_offers_start_and_says_what_it_costs():
  model, _, now = _model()
  assert model.button() == "Start" and model.summary() == ""
  assert [model.value(p) for p in (Phase.DOWNLOAD, Phase.UPLOAD, Phase.PING)] == ["", "", ""]
  assert model.footnote() == "Uses Cloudflare's speed test and up to 300 MB of data."
  now[0] = Connection(Via.CELLULAR, "LTE", metered=True)
  assert model.footnote() == "Uses Cloudflare's speed test and up to 30 MB of cellular data."
  now[0] = Connection(Via.WIFI, metered=True)
  assert model.footnote() == "Uses Cloudflare's speed test and up to 30 MB of data."


def test_a_running_test_shows_its_step_and_can_be_stopped():
  model, test, now = _model(connection=Connection(Via.CELLULAR, "LTE", metered=True))
  model.press()
  assert model.button() == "Stop" and model.summary() == "Testing…"
  assert model.measuring(Phase.DOWNLOAD) and not model.measuring(Phase.UPLOAD) and model.value(Phase.DOWNLOAD) == ""
  assert model.footnote() == "Uses up to 30 MB of cellular data. Leaving this page stops the test."
  test.shown = Result(Phase.DOWNLOAD, download=23.5 * MBPS, used=4_000_000, budget=METERED)
  assert model.value(Phase.DOWNLOAD) == "23.5 Mbps"                       # the speed so far
  test.shown = Result(Phase.UPLOAD, download=24.1 * MBPS, used=9_000_000, budget=METERED)
  assert model.measuring(Phase.UPLOAD) and model.value(Phase.DOWNLOAD) == "24.1 Mbps" and model.value(Phase.UPLOAD) == ""
  now[0] = Connection(Via.WIFI)                                           # the budget it started with stands
  assert model.footnote() == "Uses up to 30 MB of data. Leaving this page stops the test."
  model.press()
  assert test.calls == [("start", METERED), "stop"] and model.button() == "Test again"
  assert model.footnote() == "Stopped early. Used 9 MB of data." and model.summary() == "24 Mbps"


def test_a_finished_test_shows_its_numbers_and_what_it_used():
  model, test, _ = _model(DONE)
  assert [model.value(p) for p in (Phase.DOWNLOAD, Phase.UPLOAD, Phase.PING)] == ["86.4 Mbps", "11.2 Mbps", "24 ms"]
  assert model.summary() == "86 Mbps" and model.button() == "Test again"
  assert model.footnote() == "Tested Today 3:42 PM with Cloudflare's speed test. Used 148 MB of data."
  model.press()
  assert test.calls == [("start", UNMETERED)] and model.value(Phase.UPLOAD) == ""    # a new test starts clean


@pytest.mark.parametrize("problem,says", [
  (Problem.UNREACHABLE, "Couldn't reach the speed test. Check the connection and try again."),
  (Problem.DROPPED, "The connection dropped during the test. Try again."),
  (Problem.REFUSED, "The speed test turned the request down. Try again later."),
])
def test_a_failed_test_says_what_went_wrong_and_keeps_what_it_measured(problem, says):
  model, _, _ = _model(Result(Phase.FAILED, download=5 * MBPS, used=2_000_000, budget=METERED, finished=1.0, problem=problem))
  assert model.footnote() == says and model.button() == "Test again"
  assert model.value(Phase.DOWNLOAD) == "5.00 Mbps" and model.value(Phase.UPLOAD) == ""


def test_the_panel_marks_the_step_being_measured():
  model, test, _ = _model()
  panel = network_test_panel(model)
  download, upload, ping = panel.items
  assert [row._title for row in panel.items] == ["Download", "Upload", "Ping"]
  assert resolve(panel._subtitle) == "Wi-Fi · Home Wi-Fi" and resolve(panel._header_control._label) == "Start"
  assert resolve(download._subtitle) == "Maps, models and updates coming in" and resolve(download._subtitle_color) == T.TEXT_TERTIARY
  panel._header_control._click_callback()
  test.shown = Result(Phase.DOWNLOAD, download=23.5 * MBPS, budget=UNMETERED)
  assert resolve(download._subtitle) == "Measuring…" and resolve(download._subtitle_color) == T.ACCENT_TEXT
  assert resolve(download._control._text) == "23.5 Mbps" and resolve(download._control._color) == T.ACCENT_TEXT
  assert resolve(upload._subtitle) == "Drive video and logs going out" and resolve(upload._control._text) == ""
  test.shown = DONE
  assert resolve(download._subtitle_color) == T.TEXT_TERTIARY and resolve(download._control._color) == T.TEXT
  assert resolve(ping._control._text) == "24 ms" and resolve(panel._header_control._label) == "Test again"


def test_leaving_the_section_or_settings_stops_the_test():
  from openpilot.selfdrive.ui.tandem.settings import connections
  from openpilot.selfdrive.ui.tandem.settings.network_tab import Network
  from openpilot.selfdrive.ui.tandem.settings.store import SettingsStore
  from openpilot.selfdrive.ui.tandem.settings.window import SettingsWindow, Tab
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeCache, FakeWifi
  test = FakeNetworkTest()
  network = Network(FakeWifi(), SettingsStore(FakeCache(), lambda: None), cellular=FakeWifi().cellular_status)
  model = NetworkTestModel(test, lambda: network.wifi.connected_ssid, lambda: Connection(Via.WIFI, "Home Wi-Fi", False))
  window = SettingsWindow({Tab.CONNECTIONS: lambda: page}, initial=Tab.CONNECTIONS)
  from openpilot.selfdrive.ui.tandem.settings.bluetooth_tab import WheelButtons
  from openpilot.selfdrive.ui.tandem.tests.fakes import FakeBluetooth, FakeWheel
  page = connections.connections_page(network, lambda: None, window, model, WheelButtons(FakeWheel()), FakeBluetooth())
  window.show_event()
  assert test.calls == [] and resolve(page._sections[connections.TEST].value) == ""
  page.select(connections.TEST)
  page.current._panel._header_control._click_callback()
  assert test.calls == [("start", UNMETERED)] and resolve(page._sections[connections.TEST].value) == "Testing…"
  page.select(connections.CELLULAR)
  assert test.calls[-1] == "stop" and not test.result().running
  page.select(connections.TEST)
  page.current._panel._header_control._click_callback()
  window.hide_event()
  assert test.calls[-2:] == [("start", UNMETERED), "stop"]


def test_settings_open_the_shared_tester_and_read_the_devices_connection(monkeypatch):
  import sys
  import types
  from openpilot.selfdrive.ui.tandem.settings import network_test as page
  from openpilot.selfdrive.ui.tandem.settings.connections import shared_network_test as _shared_network_test
  from openpilot.starpilot.tandem import network_test as engine
  assert _shared_network_test() is engine.shared() and not engine.shared().result().running

  state = types.SimpleNamespace(networkType="cell4G", networkMetered=True)
  sm = types.SimpleNamespace(valid={"deviceState": True}, __getitem__=None)
  ui_state = types.SimpleNamespace(sm=type("SM", (), {"valid": sm.valid, "__getitem__": lambda self, name: state})())
  monkeypatch.setitem(sys.modules, "openpilot.selfdrive.ui.ui_state", types.SimpleNamespace(ui_state=ui_state))
  assert page.device_connection() == Connection(Via.CELLULAR, "LTE", True)
  state.networkType, state.networkMetered = "wifi", False
  assert page.device_connection() == Connection(Via.WIFI)
  state.networkType = "ethernet"
  assert page.device_connection() == Connection(Via.ETHERNET)
  state.networkType = "none"
  assert page.device_connection() == Connection()
  ui_state.sm.valid["deviceState"] = False
  state.networkType = "wifi"
  assert page.device_connection() == Connection()      # nothing reported yet
