"""Cellular/APN pages keep live feedback visible without reusing Wi-Fi evidence."""
from dataclasses import replace

from openpilot.selfdrive.ui.tandem import controls, tokens as T
from openpilot.selfdrive.ui.tandem.settings import connections
from openpilot.selfdrive.ui.tandem.settings.network_tab import advanced_panel, cellular_panel
from openpilot.selfdrive.ui.tandem.tests.test_settings import _network, _search_window
from openpilot.starpilot.tandem.cellular import Observation


def test_apn_save_is_acknowledged_without_leaving_advanced_panel():
  network, wifi, cache, asked = _network({"GsmApn": "carrier.apn"})
  panel = advanced_panel(network)
  panel.show_event()
  assert wifi.cellular_status.active and network.cellular_label() == "Connected"
  network.edit_apn()
  assert asked[-1][0] == "APN"
  asked[-1][1]("  new.apn  ")
  assert cache.values["GsmApn"] == "new.apn"
  assert wifi.calls[-1] == ("gsm", False, "new.apn", False)
  assert network.cellular_label() == "Connecting…"
  assert network.cellular_note() == "APN saved. Waiting for a cellular data connection."
  assert network.cellular_address() == "Not connected"
  wifi.cellular_status.value = replace(wifi.cellular_status.value, connected=True, connecting=False, bearer_apn="new.apn", address="10.8.9.10")
  assert network.cellular_label() == "Connected" and network.cellular_address() == "10.8.9.10"
  panel.hide_event()
  assert not wifi.cellular_status.active


def test_mobile_ip_and_strength_never_come_from_the_wifi_manager():
  network, wifi, _, _ = _network()
  assert wifi.ipv4_address == "192.168.1.42"
  assert network.cellular_address() == "10.64.12.8"
  wifi.cellular_status.value = Observation(sim=True, modem=8, registration=1, wifi=True)
  assert network.cellular_label() == "Wi-Fi in use" and network.cellular_address() == "Not connected"
  wifi.cellular_status.value = Observation(sim=True, modem=7, registration=2, quality=0, wifi=True)
  assert network.cellular_label() == "No signal"
  assert "APN is saved" in network.cellular_note()
  wifi.cellular_status.value = None
  assert network.cellular_label() == "Checking…" and network.cellular_summary() == ""


def test_missing_mobile_address_does_not_claim_an_active_connection_is_disconnected():
  network, wifi, _, _ = _network()
  wifi.cellular_status.value = replace(wifi.cellular_status.value, address="", quality=0)
  assert network.cellular_label() == "Connected"
  assert network.cellular_meta() == "LTE · Poor signal"
  assert network.cellular_address() == "Not available"


def test_cellular_and_apn_collection_follows_page_visibility():
  from openpilot.selfdrive.ui.tandem.settings.window import Tab
  window = _search_window()
  window.show_event()
  window.select_tab(Tab.CONNECTIONS)
  page = window.top
  page.select(connections.CELLULAR)
  panel = page.current
  source = panel.model.cellular
  assert source.active
  panel._bottom._click_callback()
  assert source.active and window.depth == 2
  window.pop()
  assert source.active
  page.select(connections.WIFI)
  assert not source.active
  page.select(connections.CELLULAR)
  assert source.active
  window.hide_event()
  assert not source.active


def test_status_badge_and_explanatory_text_remain_dynamic():
  network, wifi, _, _ = _network()
  panel = cellular_panel(network, lambda: None)
  badge = panel._header_control
  assert isinstance(badge, controls.StatusBadge)
  assert badge._label() == "Connected" and badge._tone() == controls.Tone.SUCCESS
  wifi.cellular_status.value = Observation(sim=False)
  assert badge._label() == "No SIM" and badge._tone() == controls.Tone.WARNING
  assert network.cellular_note_color() == T.WARNING
